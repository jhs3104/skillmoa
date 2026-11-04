"""소식 페이지 데이터를 만든다 (ADR-0022). 같은 상태면 항상 같은 파일이 나온다.

news.json(급상승)은 스킬 수집이, tool-updates.json(도구 업데이트)은 도구 소식 워크플로가
쓴다. 두 워크플로가 같은 파일을 고치지 않아야 커밋이 겹쳐도 충돌하지 않는다.
"""

from collector.domain.identity import repository_key
from collector.domain.models import CollectorState
from collector.domain.trends import rising_repositories
from collector.export.schema import (
    SiteData,
    SiteNews,
    SiteRisingRepository,
    SiteToolUpdate,
    SiteToolUpdates,
)

RISING_WINDOW_DAYS = 7
RISING_LIMIT = 10


def build_news_data(state: CollectorState, site: SiteData) -> SiteNews:
    """사이트에 실린 저장소만 급상승에 올린다. 눌렀을 때 갈 스킬이 있어야 한다."""
    on_site = {repository_key(repository.full_name): repository for repository in site.repositories}
    history = {key: snapshots for key, snapshots in state.star_history.items() if key in on_site}
    rising = rising_repositories(history, window_days=RISING_WINDOW_DAYS, limit=RISING_LIMIT)
    return SiteNews(
        rising_repositories=tuple(
            SiteRisingRepository(
                full_name=on_site[item.key].full_name,
                stars_gained=item.gained,
                stars=item.stars,
                window_days=RISING_WINDOW_DAYS,
            )
            for item in rising
        )
    )


def build_tool_updates_data(state: CollectorState) -> SiteToolUpdates:
    updates = sorted(
        (record for record in state.tool_updates.values() if record.highlights),
        key=lambda record: (-record.day.toordinal(), record.tool.value),
    )
    return SiteToolUpdates(
        updates=tuple(
            SiteToolUpdate(
                tool=record.tool,
                date=record.day,
                versions=record.versions,
                highlights=record.highlights,
                url=record.url,
            )
            for record in updates
        )
    )
