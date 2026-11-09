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
    repository_queries: tuple[str, ...]
    repository_min_stars: int
    repository_search_minutes: int
    code_search_max_size: int
    auto_full_scan: bool
    full_scan_interval_days: int
    code_search_minutes: int


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


class ClassifySettings(_Section):
    """요약문만 읽고 세부 분류를 고르는 별도 호출 (ADR-0018)."""

    model: str
    # 분류 기준(프롬프트)을 바꾸면 올린다. 요약은 그대로 두고 분류만 다시 정한다.
    taxonomy_version: str
    effort: Literal["low", "medium", "high"]
    max_calls_per_day: int
    max_calls_per_run: int
    max_output_tokens: int
    timeout_seconds: float
    validation_attempts: int
    concurrency: int = Field(ge=1, le=16)


class NewsSettings(_Section):
    """소식 페이지의 도구 업데이트 요약 (ADR-0022)."""

    model: str
    prompt_version: str
    effort: Literal["low", "medium", "high"]
    max_calls_per_day: int
    max_calls_per_run: int
    max_output_tokens: int
    # 하루치 변경 기록이 길면 앞부분만 보낸다.
    max_source_chars: int
    timeout_seconds: float
    validation_attempts: int
    # 이 기간 안의 릴리스만 요약하고, 기록은 keep_days까지 둔다.
    window_days: int
    keep_days: int


class ExcludeSettings(_Section):
    """사람이 정하는 사이트 제외 목록 (ADR-0020). 수집과 요약은 그대로 하고 내보낼 때만 뺀다."""

    # 빈 안내 페이지만 모아 둔 저장소처럼 통째로 뺄 저장소. 대소문자는 가리지 않는다.
    repositories: tuple[str, ...] = ()
    # 뺄 스킬. 키는 "owner/repo:path"다.
    skills: tuple[str, ...] = ()
    # 분류 호출이 빼자고 판단했지만 사이트에 남길 스킬.
    keep: tuple[str, ...] = ()


class RunSettings(_Section):
    max_minutes: int


class Settings(_Section):
    discovery: DiscoverySettings
    filter: FilterSettings
    ranking: RankingSettings
    github: GitHubSettings
    summary: SummarySettings
    classify: ClassifySettings
    news: NewsSettings
    run: RunSettings
    exclude: ExcludeSettings = ExcludeSettings()


def load_settings(path: Path = DEFAULT_CONFIG_PATH) -> Settings:
    with path.open("rb") as file:
        return Settings.model_validate(tomllib.load(file))
