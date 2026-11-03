"""config.toml 로딩. 모델 ID와 한도는 코드가 아니라 이 설정값으로 관리한다."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"
# Cloudflare 무료 플랜은 Worker 버전당 정적 파일이 2만 개다. 스킬 상세 외 파일을 위해 여유를 둔다.
MAX_CATALOG_LIMIT = 19_000


class _Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DiscoverySettings(_Section):
    seed_repositories: tuple[str, ...]
    marketplaces: tuple[str, ...]
    awesome_lists: tuple[str, ...]
    topics: tuple[str, ...]
    search_pages_per_topic: int
    code_search_max_size: int


class FilterSettings(_Section):
    min_body_chars: int


class RankingSettings(_Section):
    star_decay: float
    per_repository_cap: int
    catalog_limit: int = Field(gt=0, le=MAX_CATALOG_LIMIT)


class GitHubSettings(_Section):
    max_scan_minutes: int
    max_wait_seconds_with_token: int
    max_wait_seconds_anonymous: int


class SummarySettings(_Section):
    model: str
    prompt_version: str
    effort: Literal["low", "medium", "high"]
    max_calls_per_day: int
    max_calls_per_run: int
    max_output_tokens: int
    max_source_chars: int
    timeout_seconds: float
    validation_attempts: int
    # 동시에 보내는 요약 호출 수. 높이면 빨라지지만 API 분당 한도(429)에 먼저 닿는다.
    concurrency: int = Field(ge=1, le=16)


class Settings(_Section):
    discovery: DiscoverySettings
    filter: FilterSettings
    ranking: RankingSettings
    github: GitHubSettings
    summary: SummarySettings


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
