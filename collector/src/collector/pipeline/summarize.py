"""순위 순서대로 요약한다. 한도에 닿으면 남은 스킬은 다음 실행으로 넘긴다."""

import logging

from collector.domain.identity import repository_key
from collector.domain.models import SkillRecord, SummaryFailure, SummaryRecord
from collector.domain.summary_rules import needs_summary
from collector.pipeline.collect import CollectContext
from collector.summarize.base import (
    Summarizer,
    SummarizerUnavailableError,
    SummaryRejectedError,
    SummaryRequest,
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
    metrics = context.metrics
    if state.usage.day != context.today:
        state.usage.day = context.today
        state.usage.summary_calls = 0

    pending = [
        key
        for key in keys
        if needs_summary(
            state.skills[key],
            state.summaries.get(key),
            state.summary_failures.get(key),
            settings.prompt_version,
            refresh_prompt=refresh_prompt,
        )
    ]
    calls_at_start = state.usage.summary_calls
    for index, key in enumerate(pending):
        used_this_run = state.usage.summary_calls - calls_at_start
        if (
            state.usage.summary_calls >= settings.max_calls_per_day
            or used_this_run >= settings.max_calls_per_run
        ):
            metrics.summary_skipped_by_cap = len(pending) - index
            logger.warning("호출 상한 도달, %d개는 다음 실행으로", len(pending) - index)
            break
        if not _summarize_one(context, summarizer, key):
            break
        if (index + 1) % CHECKPOINT_EVERY_SUMMARIES == 0:
            context.checkpoint()


def _summarize_one(context: CollectContext, summarizer: Summarizer, key: str) -> bool:
    """요약 서비스를 쓸 수 없으면 False를 돌려 이번 실행의 요약을 멈춘다."""
    state = context.state
    settings = context.settings.summary
    metrics = context.metrics
    skill = state.skills[key]
    repository = state.repositories[repository_key(skill.repository)]

    source = context.content.read(repository, skill.path, skill.skill_md_hash)
    if source is None:
        return True
    if len(source) > settings.max_source_chars:
        _record_failure(context, key, skill, "source too long")
        return True

    request = SummaryRequest(
        skill_name=skill.name,
        repository=skill.repository,
        path=skill.path,
        source=source,
        bundled_files=skill.bundled_files,
    )
    state.usage.summary_calls += 1
    try:
        result = summarizer.summarize(request)
    except SummaryRejectedError as error:
        metrics.input_tokens += error.input_tokens
        metrics.output_tokens += error.output_tokens
        _record_failure(context, key, skill, error.reason)
        return True
    except SummarizerUnavailableError as error:
        logger.warning("요약 서비스 오류, 이번 실행의 요약을 멈춥니다: %s", error)
        metrics.summary_aborted = True
        return False

    metrics.input_tokens += result.input_tokens
    metrics.output_tokens += result.output_tokens
    metrics.summarized += 1
    metrics.summary_unverified += result.unverified_evidence
    state.summary_failures.pop(key, None)
    state.summaries[key] = SummaryRecord(
        skill_md_hash=skill.skill_md_hash,
        prompt_version=settings.prompt_version,
        model=summarizer.model,
        summary=result.summary,
    )
    return True


def _record_failure(context: CollectContext, key: str, skill: SkillRecord, reason: str) -> None:
    logger.warning("요약 실패 %s: %s", key, reason)
    context.metrics.summary_failed += 1
    context.state.summary_failures[key] = SummaryFailure(
        skill_md_hash=skill.skill_md_hash,
        prompt_version=context.settings.summary.prompt_version,
        reason=reason,
    )
