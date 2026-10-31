from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from collector.domain.identity import repository_key, skill_dir, skill_key, skill_slug
from collector.domain.models import CollectorState, Repository, RepositoryRecord, SkillRecord

BLOB = "a" * 40


def make_repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "github_id": 1,
        "owner": "Anthropics",
        "name": "skills",
        "stars": 10,
        "pushed_at": datetime(2026, 10, 1, tzinfo=UTC),
        "license": "MIT",
        "default_branch": "main",
    }
    return Repository.model_validate(fields | overrides)


def test_full_name_keeps_github_casing() -> None:
    assert make_repository().full_name == "Anthropics/skills"


def test_stars_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        make_repository(stars=-1)


def test_skill_hash_must_be_a_git_blob_sha() -> None:
    with pytest.raises(ValidationError):
        SkillRecord(
            repository="a/b",
            path="SKILL.md",
            skill_md_hash="not-a-sha",
            name="x",
            first_seen_at=date(2026, 1, 1),
            last_seen_at=date(2026, 1, 1),
        )


def test_state_round_trips_through_json() -> None:
    record = RepositoryRecord(
        **make_repository().model_dump(),
        first_seen_at=date(2026, 1, 1),
        sources=("curated",),
    )
    skill = SkillRecord(
        repository="Anthropics/skills",
        path="skills/pdf/SKILL.md",
        skill_md_hash=BLOB,
        name="pdf",
        first_seen_at=date(2026, 1, 1),
        last_seen_at=date(2026, 1, 2),
    )
    state = CollectorState(
        repositories={repository_key(record.full_name): record},
        skills={skill_key(record.full_name, skill.path): skill},
    )

    assert CollectorState.model_validate_json(state.model_dump_json()) == state


def test_repository_key_ignores_case() -> None:
    assert repository_key("Anthropics/Skills") == "anthropics/skills"


def test_skill_key_keeps_path_case() -> None:
    assert skill_key("A/B", "Docs/SKILL.md") == "a/b:Docs/SKILL.md"


def test_skill_dir_of_root_skill_is_empty() -> None:
    assert skill_dir("SKILL.md") == ""


def test_slug_is_readable_for_plain_paths() -> None:
    slug = skill_slug("Anthropics/skills", "skills/pdf/SKILL.md")
    assert slug == "anthropics--skills--skills--pdf"


def test_slug_stays_unique_when_cleaning_loses_information() -> None:
    first = skill_slug("A/b", "x y/SKILL.md")
    second = skill_slug("A/b", "x-y/SKILL.md")
    assert first != second
