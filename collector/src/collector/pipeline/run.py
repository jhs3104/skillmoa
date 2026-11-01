"""한 번의 수집 실행을 조립한다."""

import logging
import shutil
import time
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

from collector.config import Settings
from collector.pipeline import collect
from collector.pipeline.collect import CollectContext
from collector.pipeline.content import SkillContentStore
from collector.pipeline.metrics import RunMetrics
from collector.sources.github import GitHubClient, RateLimitExceededError
from collector.store import load_state, save_state, write_json

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

    @classmethod
    def production(cls, collector_root: Path) -> "Paths":
        build = collector_root / "build"
        return cls(
            state=collector_root / "state",
            build=build,
            site_data=collector_root.parent / "site/src/data/skills.json",
            samples=build / "samples",
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
        )


@dataclass(frozen=True)
class RunOptions:
    mode: Mode | None
    limit: int | None
    today: date


def run_collection(
    settings: Settings, github: GitHubClient, paths: Paths, options: RunOptions
) -> tuple[CollectContext, Mode]:
    state = load_state(paths.state)
    mode = options.mode or (Mode.DAILY if state.bootstrapped_on else Mode.BOOTSTRAP)
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
        found = collect.discover(context, full_scan=mode == Mode.WEEKLY, small=small)
        collect.register_repositories(context, found)
        collect.scan_repositories(context, target)
    except RateLimitExceededError as error:
        logger.warning("레이트 리밋으로 수집을 멈춥니다. 다음 실행에서 이어집니다: %s", error)
        metrics.stopped_by_rate_limit = True
        collect.apply_duplicates(context)

    state.bootstrapped_on = state.bootstrapped_on or options.today
    save_state(state, paths.state)
    return context, mode


def reset_small_run(paths: Paths) -> None:
    """소규모 실행은 이전 결과(특히 mock 요약)가 섞이지 않게 매번 새로 시작한다."""
    shutil.rmtree(paths.state.parent, ignore_errors=True)
    shutil.rmtree(paths.samples, ignore_errors=True)


def write_metrics(metrics: RunMetrics, paths: Paths, started_at: float) -> None:
    metrics.duration_seconds = round(time.monotonic() - started_at, 1)
    write_json(paths.build / "metrics/latest.json", metrics.model_dump(mode="json"))
    logger.info("실행 지표: %s", metrics.model_dump_json())
