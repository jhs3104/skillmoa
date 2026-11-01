"""품질 필터. 왜 제외했는지 항상 사유로 남긴다."""

import re
from collections import defaultdict
from collections.abc import Mapping

from collector.domain.models import ExclusionReason, Repository, SkillRecord

_TOKEN_SPLIT = re.compile(r"[-_.]+")
_FILLER_TOKENS = {"agent", "agents", "claude", "code", "my", "repo", "skill", "skills"}
_TEST_TOKENS = {
    "demo",
    "demos",
    "example",
    "examples",
    "playground",
    "sample",
    "samples",
    "sandbox",
    "temp",
    "test",
    "testing",
    "tests",
    "tmp",
}
_TEST_DIRECTORIES = {
    "__tests__",
    "fixtures",
    "node_modules",
    "template",
    "templates",
    "test",
    "testdata",
    "tests",
}


def repository_exclusion(repository: Repository) -> ExclusionReason | None:
    if repository.is_fork:
        return ExclusionReason.FORK
    if _is_test_repository(repository.name):
        return ExclusionReason.TEST_REPOSITORY
    return None


def _is_test_repository(name: str) -> bool:
    """`test-automation-skills`는 남기고 `claude-skill-test`만 걸러낸다."""
    tokens = {token for token in _TOKEN_SPLIT.split(name.lower()) if token}
    meaningful = tokens - _FILLER_TOKENS
    return bool(meaningful) and meaningful <= _TEST_TOKENS


def path_exclusion(path: str) -> ExclusionReason | None:
    directories = path.lower().split("/")[:-1]
    if _TEST_DIRECTORIES.intersection(directories):
        return ExclusionReason.TEST_PATH
    return None


def content_exclusion(body: str, min_chars: int) -> ExclusionReason | None:
    if not body.strip():
        return ExclusionReason.EMPTY
    if len(body.strip()) < min_chars:
        return ExclusionReason.TOO_SHORT
    return None


def mark_duplicates(
    skills: Mapping[str, SkillRecord], stars: Mapping[str, int]
) -> dict[str, SkillRecord]:
    """같은 해시에서 스타가 가장 많은 저장소의 스킬만 남긴다.

    다른 사유로 제외된 스킬은 원본 후보가 될 수 없다. 원본이 사라지면 다시 계산되도록
    기존 DUPLICATE 표시는 매번 지우고 새로 정한다.
    """
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for key, skill in skills.items():
        if skill.exclusion in (None, ExclusionReason.DUPLICATE):
            groups[skill.skill_md_hash].append(key)

    marked = dict(skills)
    for keys in groups.values():
        winner = min(keys, key=lambda key: (-stars.get(skills[key].repository, 0), key))
        for key in keys:
            exclusion = None if key == winner else ExclusionReason.DUPLICATE
            if skills[key].exclusion != exclusion:
                marked[key] = skills[key].model_copy(update={"exclusion": exclusion})
    return marked
