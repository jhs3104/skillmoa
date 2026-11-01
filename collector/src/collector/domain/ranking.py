"""저장소 단위 스타를 스킬 순위로 옮기는 규칙. 근거는 ADR-0003에 있다."""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from collector.domain.models import SkillRecord


@dataclass(frozen=True)
class RankedSkill:
    key: str
    repository: str
    rank: int
    effective_stars: float


def rank_skills(
    skills: Mapping[str, SkillRecord], stars: Mapping[str, int], decay: float
) -> list[RankedSkill]:
    """제외되지 않은 스킬을 유효 점수 순으로 정렬해 1부터 순위를 매긴다."""
    by_repository: defaultdict[str, list[str]] = defaultdict(list)
    for key, skill in skills.items():
        if skill.exclusion is None:
            by_repository[skill.repository].append(key)

    scored: list[tuple[float, str, str]] = []
    for repository, keys in by_repository.items():
        ordered = sorted(keys, key=lambda key: (skills[key].path.count("/"), skills[key].path))
        for position, key in enumerate(ordered):
            scored.append((stars.get(repository, 0) * decay**position, key, repository))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        RankedSkill(key=key, repository=repository, rank=index, effective_stars=score)
        for index, (score, key, repository) in enumerate(scored, start=1)
    ]


def select_catalog(ranked: list[RankedSkill], limit: int, per_repository_cap: int) -> list[str]:
    """순위 순서대로 저장소당 상한을 지키며 limit개를 고른다."""
    taken: Counter[str] = Counter()
    selected: list[str] = []
    for skill in ranked:
        if len(selected) == limit:
            break
        if taken[skill.repository] < per_repository_cap:
            taken[skill.repository] += 1
            selected.append(skill.key)
    return selected
