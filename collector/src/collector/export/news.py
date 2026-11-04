"""수집 상태에서 news.json을 만든다 (ADR-0022). 같은 상태면 항상 같은 파일이 나온다."""

from collector.domain.identity import repository_key
from collector.domain.models import CollectorState
from collector.domain.trends import rising_repositories
from collector.export.schema import SiteData, SiteNews, SiteRisingRepository

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
