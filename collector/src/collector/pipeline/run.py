"""한 번의 수집 실행을 조립한다."""

import logging
import shutil
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

import httpx

from collector.config import Settings
from collector.domain.models import CollectorState
from collector.domain.schedule import full_scan_due
from collector.domain.tool_news import ToolRelease
from collector.domain.trends import record_stars
from collector.export.news import build_news_data, build_tool_updates_data
from collector.export.samples import write_samples
from collector.export.site import build_site_data
from collector.pipeline import collect
from collector.pipeline.classify import classify_skills
from collector.pipeline.collect import CollectContext
from collector.pipeline.content import SkillContentStore
from collector.pipeline.metrics import RunMetrics
from collector.pipeline.summarize import summarize_skills
from collector.pipeline.tool_news import update_tool_news
from collector.sources.github import GitHubClient, RateLimitExceededError
from collector.sources.tool_releases import fetch_tool_releases
from collector.store import TOOL_NEWS_FILE, load_state, save_state, write_json
from collector.summarize.base import Classifier, Summarizer, ToolNewsWriter

logger = logging.getLogger(__name__)


class Mode(StrEnum):
    BOOTSTRAP = "bootstrap"
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass(frozen=True)
class Paths:
    state: Path
    build: Path
    site_data: Path
    samples: Path
    news_data: Path
    tool_updates_data: Path

    @classmethod
    def production(cls, collector_root: Path) -> "Paths":
        build = collector_root / "build"
        return cls(
            state=collector_root / "state",
            build=build,
            site_data=collector_root.parent / "site/src/data/skills.json",
            samples=build / "samples",
            news_data=collector_root.parent / "site/src/data/news.json",
            tool_updates_data=collector_root.parent / "site/src/data/tool-updates.json",
        )

    @classmethod
    def small(cls, collector_root: Path) -> "Paths":
        """--limit 실행은 커밋 대상 파일을 건드리지 않도록 build/ 안에서만 쓴다."""
        build = collector_root / "build"
        small = build / "small"
        return cls(
            state=small / "state",
            build=small,
            site_data=small / "skills.json",
            samples=build / "samples",
            news_data=small / "news.json",
            tool_updates_data=small / "tool-updates.json",
        )


@dataclass(frozen=True)
class RunOptions:
    mode: Mode | None
    limit: int | None
    today: date


def choose_mode(settings: Settings, state: CollectorState, options: RunOptions) -> Mode:
    """모드를 지정하지 않으면 상태로 고른다. --limit 실행은 비싼 전체 탐색을 하지 않는다."""
    if options.mode:
        return options.mode
    if state.bootstrapped_on is None:
        return Mode.BOOTSTRAP
    interval = settings.discovery.full_scan_interval_days
    if options.limit is None and full_scan_due(state.last_full_scan_on, options.today, interval):
        return Mode.WEEKLY
    return Mode.DAILY


def run_collection(
    settings: Settings, github: GitHubClient, paths: Paths, options: RunOptions
) -> tuple[CollectContext, Mode]:
    state = load_state(paths.state)
    mode = choose_mode(settings, state, options)
    metrics = RunMetrics(mode=mode)
    context = CollectContext(
        state=state,
        github=github,
        content=SkillContentStore(github, paths.build / "cache"),
        settings=settings,
        today=options.today,
        metrics=metrics,
        checkpoint=lambda: save_state(state, paths.state),
    )
    small = options.limit is not None
    target = options.limit or (settings.ranking.catalog_limit if mode == Mode.BOOTSTRAP else None)

    try:
        if mode != Mode.BOOTSTRAP:
            collect.refresh_known_repositories(context)
        full_scan = mode == Mode.WEEKLY
        found = collect.discover(context, full_scan=full_scan, small=small)
        # 모든 범위를 읽었을 때만 남긴다. 건너뛴 범위가 있으면 다음 실행이 다시 맡는다.
        if full_scan and metrics.code_search_complete:
            state.last_full_scan_on = options.today
        collect.register_repositories(context, found)
        collect.scan_repositories(context, target)
    except RateLimitExceededError as error:
        logger.warning("레이트 리밋으로 수집을 멈춥니다. 다음 실행에서 이어집니다: %s", error)
        metrics.stopped_by_rate_limit = True
        collect.apply_duplicates(context)
    finally:
        state.bootstrapped_on = state.bootstrapped_on or options.today
        state.star_history = record_stars(
            state.star_history,
            {
                key: record.stars
                for key, record in state.repositories.items()
                if record.exclusion is None
            },
            options.today,
        )
        save_state(state, paths.state)
    return context, mode


def run_summaries(
    context: CollectContext,
    summarizer: Summarizer,
    paths: Paths,
    limit: int | None,
    *,
    classifier: Classifier | None = None,
    refresh_prompt: bool = False,
) -> None:
    """사이트에 실을 상한까지만 요약하고 분류한다. 상한 밖 스킬에는 비용을 쓰지 않는다."""
    state = context.state
    keys = collect.catalog_keys(context, limit or context.settings.ranking.catalog_limit)

    summarize_skills(context, summarizer, keys, refresh_prompt=refresh_prompt)
    save_state(state, paths.state)
    if classifier is not None:
        classify_skills(context, classifier, keys)
        save_state(state, paths.state)
    if limit is not None:
        write_samples(state, keys, context.content, paths.samples)


def run_tool_news(
    context: CollectContext, writer: ToolNewsWriter, releases: list[ToolRelease], paths: Paths
) -> None:
    """도구 업데이트만 요약하고 내보낸다 (ADR-0022). 스킬 수집과 다른 워크플로에서 돈다.

    상태 파일 가운데 tool_updates.json만 바뀌고, 사이트 파일은 tool-updates.json만 쓴다.
    """
    update_tool_news(context, writer, releases)
    save_state(context.state, paths.state, only=(TOOL_NEWS_FILE,))
    data = build_tool_updates_data(context.state)
    write_json(paths.tool_updates_data, data.model_dump(mode="json", by_alias=True))


def run_tool_news_only(
    settings: Settings,
    github: GitHubClient,
    feeds: httpx.Client,
    writer: ToolNewsWriter,
    paths: Paths,
    today: date,
) -> CollectContext:
    """스킬 수집 없이 도구 소식만 처리한다. 몇 분이면 끝난다."""
    state = load_state(paths.state)
    context = CollectContext(
        state=state,
        github=github,
        content=SkillContentStore(github, paths.build / "cache"),
        settings=settings,
        today=today,
        metrics=RunMetrics(mode="tool-news"),
        checkpoint=lambda: save_state(state, paths.state, only=(TOOL_NEWS_FILE,)),
    )
    run_tool_news(context, writer, fetch_tool_releases(github, feeds), paths)
    return context


def export_site(context: CollectContext, paths: Paths) -> None:
    data = build_site_data(context.state, context.settings.ranking, context.settings.exclude)
    write_json(paths.site_data, data.model_dump(mode="json", by_alias=True))
    news = build_news_data(context.state, data)
    write_json(paths.news_data, news.model_dump(mode="json", by_alias=True))


def reset_small_run(paths: Paths) -> None:
    """소규모 실행은 이전 결과(특히 mock 요약)가 섞이지 않게 매번 새로 시작한다."""
    shutil.rmtree(paths.state.parent, ignore_errors=True)
    shutil.rmtree(paths.samples, ignore_errors=True)


def write_metrics(metrics: RunMetrics, paths: Paths, started_at: float) -> None:
    metrics.duration_seconds = round(time.monotonic() - started_at, 1)
    write_json(paths.build / "metrics/latest.json", metrics.model_dump(mode="json"))
    logger.info("실행 지표: %s", metrics.model_dump_json())
