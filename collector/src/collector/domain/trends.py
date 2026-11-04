"""저장소 스타 기록과 급상승 계산 (ADR-0022). 외부 호출 없는 순수 함수다."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

# 7일 급상승을 계산하고, 실행이 며칠 빠져도 기준일을 찾을 수 있도록 여유를 둔다.
STAR_HISTORY_DAYS = 35

StarHistory = dict[str, dict[date, int]]


@dataclass(frozen=True)
class RisingRepository:
    key: str
    gained: int
    stars: int


def record_stars(
    history: Mapping[str, Mapping[date, int]], stars: Mapping[str, int], today: date
) -> StarHistory:
    """오늘 스타를 남기고 보관 기간이 지난 기록을 지운다. 같은 날에는 마지막 값만 남는다."""
    oldest = today - timedelta(days=STAR_HISTORY_DAYS)
    updated: StarHistory = {}
    for key in set(history) | set(stars):
        snapshots = {day: count for day, count in history.get(key, {}).items() if day >= oldest}
        if key in stars:
            snapshots[today] = stars[key]
        if snapshots:
            updated[key] = dict(sorted(snapshots.items()))
    return updated


def rising_repositories(
    history: Mapping[str, Mapping[date, int]], *, window_days: int, limit: int
) -> list[RisingRepository]:
    """기록의 마지막 날을 기준으로 window_days 동안 스타가 가장 많이 오른 저장소를 고른다.

    실행 시각이 아니라 기록을 기준으로 해서, 같은 상태면 항상 같은 결과가 나온다.
    기준일 이전 기록이 없는 저장소는 비교하지 않는다. 새로 들어온 저장소가 전체 스타만큼
    올랐다고 잘못 보이지 않게 하기 위해서다.
    """
    if not any(history.values()):
        return []
    latest = max(day for snapshots in history.values() for day in snapshots)
    cutoff = latest - timedelta(days=window_days)
    rising: list[RisingRepository] = []
    for key, snapshots in history.items():
        if latest not in snapshots:
            continue
        before = [day for day in snapshots if day <= cutoff]
        if not before:
            continue
        gained = snapshots[latest] - snapshots[max(before)]
        if gained > 0:
            rising.append(RisingRepository(key=key, gained=gained, stars=snapshots[latest]))
    rising.sort(key=lambda item: (-item.gained, item.key))
    return rising[:limit]
