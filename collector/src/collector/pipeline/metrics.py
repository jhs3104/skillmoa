"""실행 지표. 커밋하지 않고 로그와 collector/build/metrics/에 남긴다."""

from collections import Counter

from pydantic import BaseModel, Field


class RunMetrics(BaseModel):
    mode: str
    discovered_repositories: int = 0
    refreshed_repositories: int = 0
    scanned_repositories: int = 0
    failed_repositories: int = 0
    truncated_trees: int = 0
    new_skills: int = 0
    updated_skills: int = 0
    removed_skills: int = 0
    excluded: Counter[str] = Field(default_factory=Counter)
    summarized: int = 0
    summary_failed: int = 0
    summary_skipped_by_cap: int = 0
    summary_aborted: bool = False
    stopped_by_rate_limit: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
