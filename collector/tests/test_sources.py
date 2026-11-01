from collector.sources.code_search import discover_by_size, size_query
from collector.sources.curated import parse_marketplace, parse_repository_links
from collector.sources.github import CodeSearchPage
from tests.conftest import FIXTURES


def test_awesome_links_are_normalized_to_repositories() -> None:
    links = parse_repository_links((FIXTURES / "awesome_excerpt.md").read_text(encoding="utf-8"))
    assert links == {"anthropics/skills", "acme/agent-kit", "acme/tools"}


def test_recorded_marketplace_points_at_its_host() -> None:
    raw = (FIXTURES / "marketplace_anthropics_skills.json").read_text(encoding="utf-8")
    assert parse_marketplace(raw, "anthropics/skills") == {"anthropics/skills"}


def test_marketplace_collects_external_plugin_sources() -> None:
    raw = """{"plugins": [
        {"source": {"source": "github", "repo": "acme/plugin"}},
        {"source": {"source": "url", "url": "https://github.com/acme/other.git"}},
        {"source": "./local"}
    ]}"""
    assert parse_marketplace(raw, "host/repo") == {"host/repo", "acme/plugin", "acme/other"}


def test_broken_marketplace_is_ignored() -> None:
    assert parse_marketplace("{not json", "host/repo") == set()


def test_code_search_splits_ranges_over_the_result_cap() -> None:
    queries: list[str] = []

    def search(query: str, page: int) -> CodeSearchPage:
        queries.append(query)
        if query == size_query(0, 100):
            return CodeSearchPage(1500, [])
        return CodeSearchPage(1, [f"acme/{query[-3:]}"])

    found = discover_by_size(search, 100)
    assert size_query(0, 50) in queries
    assert size_query(51, 100) in queries
    assert len(found) == 2


def test_code_search_reads_every_page_of_a_range() -> None:
    pages: list[int] = []

    def search(query: str, page: int) -> CodeSearchPage:
        pages.append(page)
        return CodeSearchPage(250, [f"acme/page{page}"])

    assert len(discover_by_size(search, 100)) == 3
    assert pages == [1, 2, 3]
