import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from collector.config import Settings, load_settings
from collector.domain.models import CollectorState
from collector.pipeline.collect import CollectContext
from collector.pipeline.content import SkillContentStore
from collector.pipeline.metrics import RunMetrics
from collector.sources.github import GitHubClient

FIXTURES = Path(__file__).parent / "fixtures/github"
TODAY = date(2026, 11, 1)


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeClock:
    """실제로 기다리지 않고 경과 시간만 기록한다."""

    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler, clock: FakeClock | None = None, token: str | None = "t"
) -> GitHubClient:
    clock = clock or FakeClock()
    return GitHubClient(
        token,
        max_wait_seconds=3700,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.time,
    )


@pytest.fixture
def settings() -> Settings:
    return load_settings()


@pytest.fixture
def make_context(settings: Settings, tmp_path: Path) -> Callable[..., CollectContext]:
    def build(github: GitHubClient, state: CollectorState | None = None) -> CollectContext:
        return CollectContext(
            state=state or CollectorState(),
            github=github,
            content=SkillContentStore(github, tmp_path / "cache"),
            settings=settings,
            today=TODAY,
            metrics=RunMetrics(mode="test"),
            checkpoint=lambda: None,
        )

    return build
