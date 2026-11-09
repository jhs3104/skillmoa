import httpx
import pytest

from collector.domain.models import Repository
from collector.sources.github import (
    GitHubClient,
    RateLimitExceededError,
    parse_repository,
)
from tests.conftest import FakeClock, fixture_json, make_client


def json_response(body: object, status: int = 200, **headers: str) -> httpx.Response:
    normalized = {key.replace("_", "-"): value for key, value in headers.items()}
    return httpx.Response(status, json=body, headers=normalized)


def test_parses_recorded_repository() -> None:
    repository = parse_repository(fixture_json("repo_anthropics_skills.json"))
    assert repository.full_name == "anthropics/skills"
    assert repository.default_branch == "main"
    assert repository.license is None
    assert repository.stars > 0


def test_noassertion_license_is_treated_as_unknown() -> None:
    item = fixture_json("repo_anthropics_skills.json")
    item["license"] = {"spdx_id": "NOASSERTION"}
    assert parse_repository(item).license is None


def test_reads_recorded_tree() -> None:
    client = make_client(lambda _: json_response(fixture_json("tree_anthropics_skills.json")))
    tree = client.get_tree(parse_repository(fixture_json("repo_anthropics_skills.json")))
    assert tree is not None
    assert not tree.truncated
    assert sum(entry.path.endswith("/SKILL.md") for entry in tree.entries) == 20


def test_missing_repository_returns_none() -> None:
    client = make_client(lambda _: json_response({"message": "Not Found"}, 404))
    assert client.get_repository("no/such") is None


def test_empty_repository_tree_returns_none() -> None:
    client = make_client(lambda _: json_response({"message": "empty"}, 409))
    repository = parse_repository(fixture_json("repo_anthropics_skills.json"))
    assert client.get_tree(repository) is None


def test_search_stops_on_short_page() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return json_response(fixture_json("search_topic_claude_skills.json"))

    found = list(make_client(handler).search_repositories("topic:claude-skills", pages=3))
    assert len(found) == 5
    assert len(calls) == 1
    assert all(isinstance(item, Repository) for item in found)


def test_search_calls_are_spaced_by_the_minute_quota() -> None:
    clock = FakeClock()
    page = fixture_json("search_topic_claude_skills.json")
    client = make_client(lambda _: json_response(page), clock)
    list(client.search_repositories("a", 1))
    list(client.search_repositories("b", 1))
    assert clock.sleeps == [pytest.approx(2.0)]


def test_anonymous_search_uses_the_lower_quota() -> None:
    clock = FakeClock()
    page = fixture_json("search_topic_claude_skills.json")
    client = make_client(lambda _: json_response(page), clock, token=None)
    list(client.search_repositories("a", 1))
    list(client.search_repositories("b", 1))
    assert clock.sleeps == [pytest.approx(6.0)]


def test_exhausted_quota_waits_until_reset() -> None:
    clock = FakeClock(now=1_000.0)
    item = fixture_json("repo_anthropics_skills.json")
    client = make_client(
        lambda _: json_response(item, x_ratelimit_remaining="0", x_ratelimit_reset="1100"), clock
    )
    client.get_repository("a/b")
    client.get_repository("a/b")
    assert clock.sleeps == [pytest.approx(101.0)]


def test_primary_rate_limit_is_retried_after_reset() -> None:
    clock = FakeClock(now=1_000.0)
    item = fixture_json("repo_anthropics_skills.json")
    responses = [
        json_response({"message": "API rate limit exceeded"}, 403,
                      x_ratelimit_remaining="0", x_ratelimit_reset="1050"),
        json_response(item),
    ]
    client = make_client(lambda _: responses.pop(0), clock)
    assert client.get_repository("a/b") is not None
    assert sum(clock.sleeps) >= 51


def test_secondary_rate_limit_honors_retry_after() -> None:
    clock = FakeClock()
    item = fixture_json("repo_anthropics_skills.json")
    responses = [json_response({"message": "abuse"}, 429, retry_after="30"), json_response(item)]
    client = make_client(lambda _: responses.pop(0), clock)
    assert client.get_repository("a/b") is not None
    assert sum(clock.sleeps) >= 30


def test_server_errors_are_retried_with_tenacity() -> None:
    item = fixture_json("repo_anthropics_skills.json")
    responses = [json_response({}, 502), json_response({}, 503), json_response(item)]
    client = make_client(lambda _: responses.pop(0))
    assert client.get_repository("a/b") is not None


def test_transport_errors_are_retried() -> None:
    item = fixture_json("repo_anthropics_skills.json")
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("boom", request=request)
        return json_response(item)

    assert make_client(handler).get_repository("a/b") is not None


def test_wait_longer_than_allowed_stops_the_run() -> None:
    clock = FakeClock(now=1_000.0)
    item = fixture_json("repo_anthropics_skills.json")
    client = GitHubClient(
        None,
        max_wait_seconds=60,
        transport=httpx.MockTransport(
            lambda _: json_response(item, x_ratelimit_remaining="0", x_ratelimit_reset="9000")
        ),
        sleep=clock.sleep,
        clock=clock.time,
    )
    client.get_repository("a/b")
    with pytest.raises(RateLimitExceededError):
        client.get_repository("a/b")


def test_token_is_sent_as_bearer() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return json_response({}, 404)

    make_client(handler, token="secret").get_repository("a/b")
    assert seen == ["Bearer secret"]


def test_rate_limit_wait_past_the_run_deadline_stops_instead() -> None:
    clock = FakeClock(now=1_000.0)
    responses = [
        json_response(
            {"message": "API rate limit exceeded"},
            403,
            x_ratelimit_remaining="0",
            x_ratelimit_reset="1600",
        ),
    ]
    client = make_client(lambda _: responses.pop(0), clock)
    client.stop_waiting_after(1_300.0)
    with pytest.raises(RateLimitExceededError):
        client.get_repository("a/b")
    assert sum(clock.sleeps) < 300
