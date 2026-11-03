"""요약문으로 세부 분류를 고른다 (ADR-0018). 분류 기준이 바뀌어도 요약은 다시 만들지 않는다."""

import logging
from concurrent.futures import Future

from collector.domain.models import ClassificationRecord
from collector.domain.summary_rules import needs_classification
from collector.pipeline.collect import CollectContext
from collector.pipeline.concurrency import run_concurrently
from collector.summarize.base import (
    ClassificationRequest,
    ClassificationResult,
    Classifier,
    SummarizerUnavailableError,
    SummaryRejectedError,
)

logger = logging.getLogger(__name__)

CHECKPOINT_EVERY_CLASSIFICATIONS = 50


def classify_skills(context: CollectContext, classifier: Classifier, keys: list[str]) -> None:
    state = context.state
    settings = context.settings.classify
    usage = state.usage
    usage.roll_over(context.today)
    pending = [
        key
        for key in keys
        if needs_classification(
            state.skills[key],
            state.summaries.get(key),
            state.classifications.get(key),
            settings.taxonomy_version,
        )
    ]
    calls_at_start = usage.classify_calls
    position = 0
    recorded = 0

    def next_request() -> tuple[str, ClassificationRequest] | None:
        nonlocal position
        if position >= len(pending):
            return None
        if (
            usage.classify_calls >= settings.max_calls_per_day
            or usage.classify_calls - calls_at_start >= settings.max_calls_per_run
        ):
            remaining = len(pending) - position
            context.metrics.classify_skipped_by_cap = remaining
            logger.warning("분류 호출 상한 도달, %d개는 다음 실행으로", remaining)
            return None
        key = pending[position]
        position += 1
        usage.classify_calls += 1
        return key, _request(context, key)

    def checkpoint_now_and_then() -> None:
        nonlocal recorded
        recorded += 1
        if recorded % CHECKPOINT_EVERY_CLASSIFICATIONS == 0:
            context.checkpoint()

    run_concurrently(
        next_request,
        classifier.classify,
        lambda key, future: _record(context, classifier, key, future),
        concurrency=settings.concurrency,
        on_recorded=checkpoint_now_and_then,
    )


def _request(context: CollectContext, key: str) -> ClassificationRequest:
    skill = context.state.skills[key]
    summary = context.state.summaries[key].summary
    return ClassificationRequest(
        skill_name=skill.name,
        repository=skill.repository,
        path=skill.path,
        summary_ko=summary.summary_ko,
        use_when=summary.use_when,
        use_cases=summary.tags.use_cases,
    )


def _record(
    context: CollectContext,
    classifier: Classifier,
    key: str,
    future: Future[ClassificationResult],
) -> bool:
    """분류를 남긴다. 실패하면 요약이 고른 분류를 그대로 쓴다. 서비스 오류면 False."""
    metrics = context.metrics
    try:
        result = future.result()
    except SummaryRejectedError as error:
        metrics.input_tokens += error.input_tokens
        metrics.output_tokens += error.output_tokens
        metrics.classify_failed += 1
        logger.warning("분류 실패 %s: %s", key, error.reason)
        return True
    except SummarizerUnavailableError as error:
        logger.warning("분류 서비스 오류, 이번 실행의 분류를 멈춥니다: %s", error)
        return False

    summary_record = context.state.summaries[key]
    metrics.input_tokens += result.input_tokens
    metrics.output_tokens += result.output_tokens
    metrics.classified += 1
    if result.subcategory is not summary_record.summary.subcategory:
        metrics.classify_changed += 1
    context.state.classifications[key] = ClassificationRecord(
        subcategory=result.subcategory,
        taxonomy_version=context.settings.classify.taxonomy_version,
        skill_md_hash=summary_record.skill_md_hash,
        summary_prompt_version=summary_record.prompt_version,
        model=classifier.model,
    )
    return True
