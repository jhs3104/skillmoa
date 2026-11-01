"""SKILL.md 본문 읽기. 받은 내용은 해시로 검증하고 실행 중에만 캐시한다."""

import logging
from pathlib import Path

from collector.domain.identity import git_blob_sha
from collector.domain.models import Repository
from collector.sources.github import GitHubClient

logger = logging.getLogger(__name__)


class SkillContentStore:
    def __init__(self, github: GitHubClient, cache_directory: Path) -> None:
        self._github = github
        self._cache = cache_directory

    def read(self, repository: Repository, path: str, expected_hash: str) -> str | None:
        cached = self._cache / f"{expected_hash}.md"
        if cached.exists():
            return cached.read_text(encoding="utf-8")

        raw = self._github.fetch_raw(repository.full_name, repository.default_branch, path)
        if raw is None:
            return None
        if git_blob_sha(raw) != expected_hash:
            logger.warning("해시 불일치, 다음 실행에서 다시 스캔: %s", path)
            return None

        text = raw.decode("utf-8", errors="replace")
        self._cache.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
        return text
