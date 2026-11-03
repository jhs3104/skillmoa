"""순위 순서대로 요약한다. 한도에 닿으면 남은 스킬은 다음 실행으로 넘긴다.

API 호출만 작업 스레드에서 동시에 보낸다. 원문 읽기와 상태 기록은 모두 이 스레드에서 하므로
상태에 잠금이 필요 없다.
"""

import logging
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from collector.domain.filters import language_exclusion
from collector.domain.frontmatter import parse_skill_document
from collector.domain.identity import repository_key
from collector.domain.models import SkillRecord, SummaryFailure, SummaryRecord
from collector.domain.summary_rules import needs_summary
from collector.pipeline.collect import CollectContext
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
    if state.usage.day != context.today:
        state.usage.day = context.today
        state.usage.summary_calls = 0

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
    queue = _Queue(pending, calls_at_start=state.usage.summary_calls)
    running: dict[Future[SummaryResult], str] = {}
    finished_count = 0

    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        while True:
            while len(running) < settings.concurrency:
                request = queue.next_request(context)
                if request is None:
                    break
                key, summary_request = request
                running[pool.submit(summarizer.summarize, summary_request)] = key
            if not running:
                break
            done, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in done:
                key = running.pop(future)
                if not _record(context, summarizer, key, future):
                    # 이미 보낸 호출은 끝까지 받아 기록하고, 새 호출만 멈춘다.
                    queue.stop()
                finished_count += 1
                if finished_count % CHECKPOINT_EVERY_SUMMARIES == 0:
                    context.checkpoint()


class _Queue:
    """보낼 차례의 스킬을 순위 순서로 내준다.

    상한은 보낸 호출 수로 세므로 동시에 보내도 넘지 않는다.
    """

    def __init__(self, keys: list[str], *, calls_at_start: int) -> None:
        self._keys = keys
        self._next = 0
        self._calls_at_start = calls_at_start
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def next_request(self, context: CollectContext) -> tuple[str, SummaryRequest] | None:
        usage = context.state.usage
        settings = context.settings.summary
        while not self._stopped and self._next < len(self._keys):
            used_this_run = usage.summary_calls - self._calls_at_start
            if (
                usage.summary_calls >= settings.max_calls_per_day
                or used_this_run >= settings.max_calls_per_run
            ):
                remaining = len(self._keys) - self._next
                context.metrics.summary_skipped_by_cap = remaining
                logger.warning("호출 상한 도달, %d개는 다음 실행으로", remaining)
                self._stopped = True
                break
            key = self._keys[self._next]
            self._next += 1
            request = _prepare(context, key)
            if request is not None:
                usage.summary_calls += 1
                return key, request
        return None


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
