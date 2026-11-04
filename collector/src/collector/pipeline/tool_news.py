"""도구 업데이트를 하루 단위로 요약해 상태에 남긴다 (ADR-0022)."""

import logging
from collections.abc import Iterable

from collector.domain.models import ToolUpdateRecord
from collector.domain.tool_news import (
    ToolRelease,
    group_releases,
    needs_tool_summary,
    prune_tool_updates,
    update_key,
)
from collector.pipeline.collect import CollectContext
from collector.summarize.base import (
    SummarizerUnavailableError,
    SummaryRejectedError,
    ToolNewsRequest,
    ToolNewsWriter,
)

logger = logging.getLogger(__name__)


def update_tool_news(
    context: CollectContext, writer: ToolNewsWriter, releases: Iterable[ToolRelease]
) -> None:
    """원문이나 프롬프트가 바뀐 묶음만, 최근 날짜부터 상한까지 요약한다."""
    state = context.state
    settings = context.settings.news
    usage = state.tool_news_usage
    usage.roll_over(context.today)
    groups = group_releases(releases, today=context.today, window_days=settings.window_days)
    pending = [
        group
        for (tool, day), group in sorted(groups.items(), key=lambda item: item[0][1], reverse=True)
        if needs_tool_summary(
            state.tool_updates.get(update_key(tool, day)), group, settings.prompt_version
        )
    ]
    calls_at_start = usage.calls
    for group in pending:
        if (
            usage.calls >= settings.max_calls_per_day
            or usage.calls - calls_at_start >= settings.max_calls_per_run
        ):
            logger.warning("업데이트 요약 상한 도달, 나머지는 다음 실행으로")
            break
        usage.calls += 1
        request = ToolNewsRequest(tool=group.tool, versions=group.versions, notes=group.notes)
        try:
            result = writer.write(request)
        except SummaryRejectedError as error:
            context.metrics.news_failed += 1
            logger.warning(
                "업데이트 요약 실패 %s %s: %s", group.tool.value, group.day, error.reason
            )
            continue
        except SummarizerUnavailableError as error:
            logger.warning("요약 서비스 오류, 업데이트 요약을 멈춥니다: %s", error)
            break
        context.metrics.news_summarized += 1
        context.metrics.input_tokens += result.input_tokens
        context.metrics.output_tokens += result.output_tokens
        state.tool_updates[update_key(group.tool, group.day)] = ToolUpdateRecord(
            tool=group.tool,
            day=group.day,
            versions=group.versions,
            url=group.url,
            source_hash=group.source_hash,
            highlights=result.highlights,
            prompt_version=settings.prompt_version,
            model=writer.model,
        )
    state.tool_updates = prune_tool_updates(
        state.tool_updates, today=context.today, keep_days=settings.keep_days
    )
