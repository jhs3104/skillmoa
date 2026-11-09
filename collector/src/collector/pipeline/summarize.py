"""순위 순서대로 요약한다. 한도에 닿으면 남은 스킬은 다음 실행으로 넘긴다."""

import logging
from concurrent.futures import Future

from collector.domain.filters import language_exclusion
from collector.domain.frontmatter import parse_skill_document
from collector.domain.identity import repository_key
from collector.domain.models import SkillRecord, SummaryFailure, SummaryRecord
from collector.domain.summary_rules import needs_summary
from collector.pipeline.collect import CollectContext
from collector.pipeline.concurrency import run_concurrently
from collector.summarize.base import (
    Summarizer,
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
    SummaryResult,
)

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY_SUMMARIES = 20


def summarize_skills(
    context: CollectContext,
    summarizer: Summarizer,
    keys: list[str],
    *,
    refresh_prompt: bool = False,
) -> None:
    state = context.state
    settings = context.settings.summary
    usage = state.usage
    usage.roll_over(context.today)

    pending = [
        key
        for key in keys
        if (key in state.summary_redo and state.skills[key].exclusion is None)
        or needs_summary(
            state.skills[key],
            state.summaries.get(key),
            state.summary_failures.get(key),
            settings.prompt_version,
            refresh_prompt=refresh_prompt,
        )
    ]
    calls_at_start = usage.summary_calls
    position = 0
    recorded = 0

    def next_request() -> tuple[str, SummaryRequest] | None:
        # 상한은 보낸 호출 수로 센다. 동시에 보내도 넘지 않는다.
        nonlocal position
        while position < len(pending):
            if context.out_of_time():
                context.metrics.stopped_by_time = True
                logger.warning("실행 마감, 요약 %d개는 다음 실행으로", len(pending) - position)
                return None
            if (
                usage.summary_calls >= settings.max_calls_per_day
                or usage.summary_calls - calls_at_start >= settings.max_calls_per_run
            ):
                remaining = len(pending) - position
                context.metrics.summary_skipped_by_cap = remaining
                logger.warning("호출 상한 도달, %d개는 다음 실행으로", remaining)
                return None
            key = pending[position]
            position += 1
            request = _prepare(context, key)
            if request is not None:
                usage.summary_calls += 1
                return key, request
        return None

    def checkpoint_now_and_then() -> None:
        nonlocal recorded
        recorded += 1
        if recorded % CHECKPOINT_EVERY_SUMMARIES == 0:
            context.checkpoint()

    run_concurrently(
        next_request,
        summarizer.summarize,
        lambda key, future: _record(context, summarizer, key, future),
        concurrency=settings.concurrency,
        on_recorded=checkpoint_now_and_then,
    )


def _prepare(context: CollectContext, key: str) -> SummaryRequest | None:
    """원문을 읽어 요청을 만든다. 보낼 수 없으면 None이다."""
    skill = context.state.skills[key]
    repository = context.state.repositories[repository_key(skill.repository)]
    source = context.content.read(repository, skill.path, skill.skill_md_hash)
    if source is None:
        return None
    # 규칙보다 먼저 수집된 스킬은 해시가 그대로라 필터를 다시 거치지 않는다.
    # 요약 직전에 한 번 더 본다.
    exclusion = language_exclusion(parse_skill_document(source).body)
    if exclusion is not None:
        context.state.skills[key] = skill.model_copy(update={"exclusion": exclusion})
        context.state.summary_redo.pop(key, None)
        context.metrics.excluded[exclusion] += 1
        return None
    if len(source) > context.settings.summary.max_source_chars:
        _record_failure(context, key, skill, "source too long")
        return None
    return SummaryRequest(
        skill_name=skill.name,
        repository=skill.repository,
        path=skill.path,
        source=source,
        bundled_files=skill.bundled_files,
    )


def _record(
    context: CollectContext,
    summarizer: Summarizer,
    key: str,
    future: Future[SummaryResult],
) -> bool:
    """결과를 상태에 남긴다. 요약 서비스를 쓸 수 없으면 False를 돌려 새 호출을 멈춘다."""
    state = context.state
    metrics = context.metrics
    skill = state.skills[key]
    try:
        result = future.result()
    except SummaryRejectedError as error:
        metrics.input_tokens += error.input_tokens
        metrics.output_tokens += error.output_tokens
        _record_failure(context, key, skill, error.reason)
        return True
    except SummarizerUnavailableError as error:
        if not metrics.summary_aborted:
            logger.warning("요약 서비스 오류, 이번 실행의 요약을 멈춥니다: %s", error)
        metrics.summary_aborted = True
        return False

    metrics.input_tokens += result.input_tokens
    metrics.output_tokens += result.output_tokens
    metrics.summarized += 1
    metrics.summary_unverified += result.unverified_evidence
    state.summary_failures.pop(key, None)
    state.summary_redo.pop(key, None)
    state.summaries[key] = SummaryRecord(
        skill_md_hash=skill.skill_md_hash,
        prompt_version=context.settings.summary.prompt_version,
        model=summarizer.model,
        summary=result.summary,
    )
    return True


def _record_failure(context: CollectContext, key: str, skill: SkillRecord, reason: str) -> None:
    logger.warning("요약 실패 %s: %s", key, reason)
    context.metrics.summary_failed += 1
    # 다시 만들지 못하면 기존 요약을 그대로 두고, 같은 스킬에 호출을 반복하지 않는다.
    context.state.summary_redo.pop(key, None)
    context.state.summary_failures[key] = SummaryFailure(
        skill_md_hash=skill.skill_md_hash,
        prompt_version=context.settings.summary.prompt_version,
        reason=reason,
    )
