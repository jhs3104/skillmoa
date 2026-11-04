from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

from collector.config import Settings
from collector.domain.identity import git_blob_sha, repository_key, skill_key
from collector.domain.models import (
    CollectorState,
    ExclusionReason,
    Repository,
    RepositoryRecord,
    SkillRecord,
)
from collector.domain.tree import SkillFile
from collector.pipeline.collect import (
    CollectContext,
    discover,
    files_to_read,
    needs_scan,
    refresh_known_repositories,
    register_repositories,
    scan_repositories,
)
from collector.pipeline.run import Mode, Paths, RunOptions, run_collection
from collector.sources.github import GitHubClient, parse_repository
from collector.store import load_state, save_state
from tests.conftest import TODAY, FakeClock, fixture_bytes, fixture_json, make_client

SAMPLE = fixture_bytes("skill_sample.md")
SAMPLE_SHA = git_blob_sha(SAMPLE)
PUSHED = datetime(2026, 10, 1, tzinfo=UTC)
ContextFactory = Callable[..., CollectContext]


def record(name: str = "acme/kit", stars: int = 5, **fields: object) -> RepositoryRecord:
    owner, _, repo = name.partition("/")
    return RepositoryRecord(
        github_id=1,
        owner=owner,
        name=repo,
        stars=stars,
        pushed_at=PUSHED,
        license="MIT",
        default_branch="main",
        first_seen_at=date(2026, 1, 1),
        **fields,
    )


def tree_body(*paths: tuple[str, str]) -> dict[str, object]:
    entries = [
        {"path": path, "sha": sha, "type": "blob", "size": 10, "mode": "100644"}
        for path, sha in paths
    ]
    return {"tree": entries, "truncated": False}


def github_site(tree: dict[str, object], raw: bytes = SAMPLE) -> Callable:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=raw)
        return httpx.Response(200, json=tree)

    return handler


def test_scan_records_skill_from_frontmatter(make_context: ContextFactory) -> None:
    client = make_client(github_site(tree_body(("skills/a/SKILL.md", SAMPLE_SHA))))
    context = make_context(client)
    context.state.repositories["acme/kit"] = record()

    scan_repositories(context, None)

    skill = context.state.skills[skill_key("acme/kit", "skills/a/SKILL.md")]
    assert skill.name == "sample-skill"
    assert skill.license == "Apache-2.0"
    assert skill.first_seen_at == TODAY
    assert skill.exclusion is None
    assert context.metrics.new_skills == 1
    assert not needs_scan(context.state.repositories["acme/kit"])


def test_short_skill_is_kept_with_exclusion_reason(make_context: ContextFactory) -> None:
    raw = b"---\nname: tiny\n---\n\nhi\n"
    client = make_client(github_site(tree_body(("SKILL.md", git_blob_sha(raw))), raw))
    context = make_context(client)
    context.state.repositories["acme/kit"] = record()

    scan_repositories(context, None)

    assert context.state.skills["acme/kit:SKILL.md"].exclusion == ExclusionReason.TOO_SHORT
    assert context.metrics.excluded[ExclusionReason.TOO_SHORT] == 1


def test_hash_mismatch_leaves_repository_for_rescan(make_context: ContextFactory) -> None:
    client = make_client(github_site(tree_body(("SKILL.md", "0" * 40))))
    context = make_context(client)
    context.state.repositories["acme/kit"] = record()

    scan_repositories(context, None)

    assert context.state.skills == {}
    assert needs_scan(context.state.repositories["acme/kit"])


def test_unchanged_repository_is_not_scanned(make_context: ContextFactory) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected call: {request.url}")

    context = make_context(make_client(fail))
    context.state.repositories["acme/kit"] = record(scanned_pushed_at=PUSHED)

    scan_repositories(context, None)

    assert context.metrics.scanned_repositories == 0


def test_unchanged_hash_keeps_first_seen_and_skips_download(
    make_context: ContextFactory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host != "raw.githubusercontent.com"
        return httpx.Response(200, json=tree_body(("SKILL.md", SAMPLE_SHA)))

    context = make_context(make_client(handler))
    context.state.repositories["acme/kit"] = record()
    context.state.skills["acme/kit:SKILL.md"] = SkillRecord(
        repository="acme/kit",
        path="SKILL.md",
        skill_md_hash=SAMPLE_SHA,
        name="kept",
        first_seen_at=date(2026, 1, 1),
        last_seen_at=date(2026, 1, 1),
    )

    scan_repositories(context, None)

    skill = context.state.skills["acme/kit:SKILL.md"]
    assert skill.first_seen_at == date(2026, 1, 1)
    assert skill.last_seen_at == TODAY


def test_removed_skill_is_forgotten(make_context: ContextFactory) -> None:
    context = make_context(make_client(github_site(tree_body())))
    context.state.repositories["acme/kit"] = record()
    context.state.skills["acme/kit:SKILL.md"] = SkillRecord(
        repository="acme/kit",
        path="SKILL.md",
        skill_md_hash=SAMPLE_SHA,
        name="gone",
        first_seen_at=TODAY,
        last_seen_at=TODAY,
    )

    scan_repositories(context, None)

    assert context.state.skills == {}
    assert context.metrics.removed_skills == 1


def test_files_to_read_stop_at_twice_the_repository_cap() -> None:
    files = [SkillFile(f"skills/{index:03}/SKILL.md", "a" * 40, ()) for index in range(50)]
    assert len(files_to_read(files, per_repository_cap=10)) == 20


def test_files_to_read_prefer_shallow_paths() -> None:
    deep = SkillFile("a/b/c/SKILL.md", "a" * 40, ())
    shallow = SkillFile("z/SKILL.md", "b" * 40, ())
    assert files_to_read([deep, shallow], per_repository_cap=1)[0] is shallow


def test_scan_time_budget_defers_remaining_repositories(make_context: ContextFactory) -> None:
    client = make_client(github_site(tree_body(("SKILL.md", SAMPLE_SHA))))
    context = make_context(client)
    context.state.repositories["big/one"] = record("big/one", stars=100)
    context.state.repositories["small/two"] = record("small/two", stars=1)
    ticks = iter([0.0, 999_999.0])

    scan_repositories(context, None, clock=lambda: next(ticks))

    assert context.metrics.scanned_repositories == 1
    assert context.metrics.scan_deferred_repositories == 1
    assert context.state.repositories["small/two"].scanned_pushed_at is None


def test_scan_stops_once_target_is_filled(make_context: ContextFactory) -> None:
    client = make_client(github_site(tree_body(("SKILL.md", SAMPLE_SHA))))
    context = make_context(client)
    context.state.repositories["big/one"] = record("big/one", stars=100)
    context.state.repositories["small/two"] = record("small/two", stars=1)

    scan_repositories(context, target=1)

    assert context.metrics.scanned_repositories == 1
    assert context.state.repositories["big/one"].scanned_pushed_at == PUSHED


def test_search_results_need_no_extra_metadata_calls(
    make_context: ContextFactory, settings: Settings
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.startswith("/search"):
            return httpx.Response(200, json=fixture_json("search_topic_claude_skills.json"))
        return httpx.Response(200, json=fixture_json("repo_anthropics_skills.json"))

    context = make_context(make_client(handler))
    found = discover(context, full_scan=False, small=True)
    register_repositories(context, found)

    assert len(context.state.repositories) == 6
    assert calls.count("/repos/anthropics/skills") == 1
    assert context.state.repositories["anthropics/skills"].sources == ("seed",)


def test_same_repository_from_two_sources_is_one_record(
    make_context: ContextFactory,
) -> None:
    item = fixture_json("repo_anthropics_skills.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/search"):
            return httpx.Response(200, json={"items": [item]})
        return httpx.Response(200, json=item)

    context = make_context(make_client(handler))
    register_repositories(context, discover(context, full_scan=False, small=True))

    assert list(context.state.repositories) == ["anthropics/skills"]
    assert context.state.repositories["anthropics/skills"].sources == (
        "seed",
        "topic:claude-skills",
    )


def test_refresh_updates_stars_and_triggers_rescan(make_context: ContextFactory) -> None:
    item = fixture_json("repo_anthropics_skills.json")
    context = make_context(make_client(lambda _: httpx.Response(200, json=item)))
    context.state.repositories["anthropics/skills"] = record(
        "anthropics/skills", stars=1, scanned_pushed_at=PUSHED
    )

    refresh_known_repositories(context)

    refreshed = context.state.repositories["anthropics/skills"]
    assert refreshed.stars == item["stargazers_count"]
    assert refreshed.first_seen_at == date(2026, 1, 1)
    assert needs_scan(refreshed)


def test_deleted_repository_takes_its_skills(make_context: ContextFactory) -> None:
    context = make_context(make_client(lambda _: httpx.Response(404, json={})))
    context.state.repositories["acme/kit"] = record()
    context.state.skills["acme/kit:SKILL.md"] = SkillRecord(
        repository="acme/kit",
        path="SKILL.md",
        skill_md_hash=SAMPLE_SHA,
        name="x",
        first_seen_at=TODAY,
        last_seen_at=TODAY,
    )

    refresh_known_repositories(context)

    assert context.state.repositories == {}
    assert context.state.skills == {}


def test_renamed_repository_keeps_skill_history(make_context: ContextFactory) -> None:
    item = fixture_json("repo_anthropics_skills.json")
    context = make_context(make_client(lambda _: httpx.Response(200, json=item)))
    context.state.repositories["old/name"] = record("old/name", scanned_pushed_at=PUSHED)
    context.state.skills["old/name:SKILL.md"] = SkillRecord(
        repository="old/name",
        path="SKILL.md",
        skill_md_hash=SAMPLE_SHA,
        name="x",
        first_seen_at=date(2026, 1, 1),
        last_seen_at=date(2026, 1, 1),
    )

    refresh_known_repositories(context)

    assert list(context.state.repositories) == ["anthropics/skills"]
    moved = context.state.skills["anthropics/skills:SKILL.md"]
    assert moved.first_seen_at == date(2026, 1, 1)


def fake_github(requests: list[str]) -> Callable:
    repository = fixture_json("repo_anthropics_skills.json")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.host == "raw.githubusercontent.com":
            return httpx.Response(200, content=SAMPLE)
        if request.url.path.startswith("/search"):
            return httpx.Response(200, json={"items": []})
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json=tree_body(("skills/a/SKILL.md", SAMPLE_SHA)))
        return httpx.Response(200, json=repository)

    return handler


def run_twice_paths(tmp_path: Path) -> Paths:
    return Paths(
        tmp_path / "state",
        tmp_path,
        tmp_path / "skills.json",
        tmp_path / "samples",
        tmp_path / "news.json",
    )


def test_collection_records_todays_stars(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    options = RunOptions(mode=Mode.BOOTSTRAP, limit=None, today=TODAY)

    context, _ = run_collection(settings, make_client(fake_github([])), paths, options)

    stars = context.state.repositories["anthropics/skills"].stars
    assert load_state(paths.state).star_history["anthropics/skills"] == {TODAY: stars}


def test_second_run_is_idempotent(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    options = RunOptions(mode=Mode.BOOTSTRAP, limit=None, today=TODAY)
    requests: list[str] = []
    client = make_client(fake_github(requests))

    run_collection(settings, client, paths, options)
    first = {path.name: path.read_bytes() for path in paths.state.iterdir()}
    run_collection(settings, client, paths, options)
    second = {path.name: path.read_bytes() for path in paths.state.iterdir()}

    assert first == second
    assert sum("/git/trees/" in path for path in requests) == 1


def test_rate_limit_keeps_progress_for_resume(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    options = RunOptions(mode=Mode.BOOTSTRAP, limit=None, today=TODAY)
    healthy = fake_github([])

    def exhausted(request: httpx.Request) -> httpx.Response:
        if "/git/trees/" in request.url.path:
            headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "999999"}
            return httpx.Response(403, json={"message": "rate limit"}, headers=headers)
        return healthy(request)

    clock = FakeClock()
    limited = GitHubClient(
        "t",
        max_wait_seconds=60,
        transport=httpx.MockTransport(exhausted),
        sleep=clock.sleep,
        clock=clock.time,
    )
    context, _ = run_collection(settings, limited, paths, options)
    assert context.metrics.stopped_by_rate_limit
    assert load_state(paths.state).repositories["anthropics/skills"].scanned_pushed_at is None

    resumed, _ = run_collection(settings, make_client(healthy), paths, options)
    assert resumed.metrics.scanned_repositories == 1
    assert resumed.state.skills


def test_daily_scans_only_changed_repositories(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    requests: list[str] = []
    client = make_client(fake_github(requests))
    bootstrap = RunOptions(mode=Mode.BOOTSTRAP, limit=None, today=TODAY)
    run_collection(settings, client, paths, bootstrap)
    requests.clear()

    daily = RunOptions(mode=Mode.DAILY, limit=None, today=date(2026, 11, 2))
    context, _ = run_collection(settings, client, paths, daily)

    assert context.metrics.refreshed_repositories == 1
    assert context.metrics.scanned_repositories == 0
    assert not any("/git/trees/" in path for path in requests)
    skill = context.state.skills[skill_key("anthropics/skills", "skills/a/SKILL.md")]
    assert skill.first_seen_at == TODAY


def test_daily_discovers_new_repositories_from_topic_search(
    tmp_path: Path, settings: Settings
) -> None:
    paths = run_twice_paths(tmp_path)
    base = fake_github([])
    newcomer = fixture_json("search_topic_claude_skills.json")["items"][0]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/search/repositories"):
            return httpx.Response(200, json={"items": [newcomer]})
        return base(request)

    options = RunOptions(mode=Mode.DAILY, limit=None, today=TODAY)
    context, _ = run_collection(settings, make_client(handler), paths, options)

    assert repository_key(newcomer["full_name"]) in context.state.repositories
    assert context.metrics.scanned_repositories == 2


def test_weekly_adds_repositories_from_code_search(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    base = fake_github([])
    repository = fixture_json("repo_anthropics_skills.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search/code":
            return httpx.Response(200, json=fixture_json("code_search_small.json"))
        if request.url.path in ("/repos/acme/one", "/repos/acme/two"):
            name = request.url.path.rpartition("/")[2]
            item = repository | {
                "id": len(name),
                "name": name,
                "owner": {"login": "acme"},
            }
            return httpx.Response(200, json=item)
        return base(request)

    options = RunOptions(mode=Mode.WEEKLY, limit=None, today=TODAY)
    context, _ = run_collection(settings, make_client(handler), paths, options)

    assert context.state.repositories["acme/one"].sources == ("code_search",)
    assert "acme/two" in context.state.repositories


def test_weekly_without_token_skips_code_search(tmp_path: Path, settings: Settings) -> None:
    paths = run_twice_paths(tmp_path)
    requests: list[str] = []
    options = RunOptions(mode=Mode.WEEKLY, limit=None, today=TODAY)
    client = make_client(fake_github(requests), token=None)

    run_collection(settings, client, paths, options)

    assert "/search/code" not in requests


def test_interrupted_state_round_trips(tmp_path: Path) -> None:
    state = CollectorState(bootstrapped_on=TODAY)
    state.repositories["acme/kit"] = record()
    save_state(state, tmp_path)
    assert load_state(tmp_path) == state


def test_search_repository_parses_to_domain_model() -> None:
    item = fixture_json("search_topic_claude_skills.json")["items"][0]
    assert isinstance(parse_repository(item), Repository)
