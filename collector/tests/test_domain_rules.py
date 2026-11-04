from datetime import UTC, date, datetime

import pytest

from collector.domain.filters import (
    content_exclusion,
    language_exclusion,
    mark_duplicates,
    path_exclusion,
    repository_exclusion,
)
from collector.domain.frontmatter import parse_skill_document
from collector.domain.identity import git_blob_sha
from collector.domain.models import ExclusionReason, Repository, SkillRecord
from collector.domain.ranking import rank_skills, select_catalog
from collector.domain.tree import MAX_BUNDLED_FILES, TreeEntry, find_skill_files, script_presence

DAY = date(2026, 1, 1)


def skill(repository: str, path: str, sha: str = "a", **fields: object) -> SkillRecord:
    return SkillRecord(
        repository=repository,
        path=path,
        skill_md_hash=sha * 40,
        name="x",
        first_seen_at=DAY,
        last_seen_at=DAY,
        **fields,
    )


def repository(name: str, is_fork: bool = False) -> Repository:
    return Repository(
        github_id=1,
        owner="o",
        name=name,
        stars=1,
        pushed_at=datetime(2026, 1, 1, tzinfo=UTC),
        license=None,
        default_branch="main",
        is_fork=is_fork,
    )


@pytest.mark.parametrize("name", ["test", "claude-skill-test", "my-demo-skills", "agent_sandbox"])
def test_test_repositories_are_excluded(name: str) -> None:
    assert repository_exclusion(repository(name)) == ExclusionReason.TEST_REPOSITORY


@pytest.mark.parametrize(
    "name", ["skills", "test-automation-skills", "claude-code", "demo-builder"]
)
def test_real_repositories_are_kept(name: str) -> None:
    assert repository_exclusion(repository(name)) is None


def test_forks_are_excluded() -> None:
    assert repository_exclusion(repository("skills", is_fork=True)) == ExclusionReason.FORK


def test_test_paths_are_excluded_by_directory_only() -> None:
    assert path_exclusion("template/SKILL.md") == ExclusionReason.TEST_PATH
    assert path_exclusion("skills/tests/x/SKILL.md") == ExclusionReason.TEST_PATH
    assert path_exclusion("skills/test-runner/SKILL.md") is None


def test_content_filter_reports_empty_and_short() -> None:
    assert content_exclusion("  \n", 10) == ExclusionReason.EMPTY
    assert content_exclusion("short", 10) == ExclusionReason.TOO_SHORT
    assert content_exclusion("long enough body", 10) is None


def test_chinese_or_japanese_bodies_are_excluded() -> None:
    chinese = "这个技能帮助你在微信公众号上撰写长文章，并检查格式和发布流程。"
    japanese = "このスキルは議事録をまとめて、次のタスクを整理します。"
    assert language_exclusion(chinese) == ExclusionReason.FOREIGN_LANGUAGE
    assert language_exclusion(japanese) == ExclusionReason.FOREIGN_LANGUAGE
    assert content_exclusion(chinese, 10) == ExclusionReason.FOREIGN_LANGUAGE


def test_korean_english_and_code_samples_are_kept() -> None:
    assert language_exclusion("회의록을 정리하고 다음 할 일을 뽑아 주는 스킬입니다.") is None
    english = "Write release notes. Example output: `发布说明` for Chinese teams.\n"
    assert language_exclusion(english * 3) is None
    fenced = "Translate the UI strings.\n```json\n{\"title\": \"标题标题标题标题标题标题\"}\n```\n"
    assert language_exclusion(fenced) is None


FRENCH = (
    "Vous êtes un expert-comptable. Pour chaque client, vérifiez les comptes annuels "
    "et les déclarations de TVA. Les écritures sont classées dans le plan comptable, "
    "avec une attention particulière aux charges qui ne sont pas déductibles. "
)
GERMAN = (
    "Prüfe die Klausel nach dem AGB-Recht. Die Abtretung ist nicht wirksam, wenn sie "
    "den Vertragspartner unangemessen benachteiligt. Der Prüfer gibt eine Einschätzung "
    "mit Risikostufe und einer Formulierung, die auch vor Gericht hält. "
)
VIETNAMESE = (
    "Kiểm tra trang web theo quy định pháp luật Việt Nam về bảo vệ dữ liệu cá nhân, "
    "thương mại điện tử và an ninh mạng. Đánh giá mức độ rủi ro cho từng hạng mục. "
)


def test_european_and_vietnamese_bodies_are_excluded() -> None:
    for body in (FRENCH * 3, GERMAN * 3, VIETNAMESE * 3):
        assert language_exclusion(body) == ExclusionReason.FOREIGN_LANGUAGE


def test_english_with_a_few_foreign_words_is_kept() -> None:
    english = (
        "Use this skill when you need to review a contract. It reads the clauses and "
        "flags risky terms such as 'la clause pénale' or 'die Abtretung' for the lawyer. "
    )
    assert language_exclusion(english * 4) is None
    sample = "Translate the strings.\n```\nles des pour une dans avec sur pas aux\n```\n"
    assert language_exclusion(sample * 10) is None


def test_duplicates_keep_most_starred_repository() -> None:
    skills = {"a": skill("a/x", "SKILL.md"), "b": skill("b/y", "SKILL.md")}
    marked = mark_duplicates(skills, {"a/x": 1, "b/y": 9})
    assert marked["b"].exclusion is None
    assert marked["a"].exclusion == ExclusionReason.DUPLICATE


def test_same_name_in_one_repository_keeps_the_shallowest_path() -> None:
    skills = {
        "deep": skill("a/x", "platform/skills/search/SKILL.md", sha="a"),
        "top": skill("a/x", "skills/search/SKILL.md", sha="b"),
    }
    marked = mark_duplicates(skills, {"a/x": 1})
    assert marked["top"].exclusion is None
    assert marked["deep"].exclusion == ExclusionReason.DUPLICATE


def test_same_name_across_repositories_is_kept() -> None:
    skills = {"a": skill("a/x", "SKILL.md", sha="a"), "b": skill("b/y", "SKILL.md", sha="b")}
    assert all(item.exclusion is None for item in mark_duplicates(skills, {}).values())


def test_duplicate_ties_are_deterministic() -> None:
    skills = {"b": skill("b/y", "SKILL.md"), "a": skill("a/x", "SKILL.md")}
    assert mark_duplicates(skills, {})["a"].exclusion is None


def test_duplicate_is_released_when_original_disappears() -> None:
    skills = {"a": skill("a/x", "SKILL.md", exclusion=ExclusionReason.DUPLICATE)}
    assert mark_duplicates(skills, {})["a"].exclusion is None


def test_filtered_skill_cannot_be_the_original() -> None:
    skills = {
        "a": skill("a/x", "SKILL.md", exclusion=ExclusionReason.TEST_PATH),
        "b": skill("b/y", "SKILL.md"),
    }
    marked = mark_duplicates(skills, {"a/x": 100, "b/y": 1})
    assert marked["b"].exclusion is None
    assert marked["a"].exclusion == ExclusionReason.TEST_PATH


def test_ranking_decays_within_a_repository() -> None:
    skills = {
        "big:1": skill("big/r", "a/SKILL.md"),
        "big:2": skill("big/r", "b/SKILL.md", sha="b"),
        "small:1": skill("small/r", "a/SKILL.md", sha="c"),
    }
    ranked = rank_skills(skills, {"big/r": 100, "small/r": 80}, decay=0.5)
    assert [item.key for item in ranked] == ["big:1", "small:1", "big:2"]
    assert [item.rank for item in ranked] == [1, 2, 3]


def test_ranking_skips_excluded_skills() -> None:
    skills = {"a": skill("a/x", "SKILL.md", exclusion=ExclusionReason.TOO_SHORT)}
    assert rank_skills(skills, {"a/x": 1}, decay=0.5) == []


def test_catalog_respects_repository_cap() -> None:
    skills = {str(i): skill("big/r", f"{i}/SKILL.md", sha=str(i)) for i in range(5)}
    skills["other"] = skill("other/r", "SKILL.md", sha="f")
    ranked = rank_skills(skills, {"big/r": 1000, "other/r": 1}, decay=1.0)
    selected = select_catalog(ranked, limit=3, per_repository_cap=2)
    assert len(selected) == 3
    assert "other" in selected


def test_frontmatter_reads_block_scalars_and_license() -> None:
    document = parse_skill_document(
        "---\nname: pdf\ndescription: >\n  first\n  second\nlicense: 'MIT'\n---\n\n# Body\n"
    )
    assert document.name == "pdf"
    assert document.description == "first second"
    assert document.license == "MIT"
    assert document.body == "# Body"


def test_text_without_frontmatter_is_all_body() -> None:
    document = parse_skill_document("# Just text\n")
    assert document.name is None
    assert document.body == "# Just text"


def test_unterminated_frontmatter_does_not_crash() -> None:
    assert parse_skill_document("---\nname: x\n").name is None


def test_git_blob_sha_matches_git() -> None:
    assert git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_bundled_files_are_relative_to_the_skill() -> None:
    entries = [
        TreeEntry("skills/pdf/SKILL.md", "a", 1),
        TreeEntry("skills/pdf/scripts/run.py", "b", 1),
        TreeEntry("skills/other/SKILL.md", "c", 1),
        TreeEntry("README.md", "d", 1),
    ]
    found = find_skill_files(entries)
    assert [item.path for item in found] == ["skills/other/SKILL.md", "skills/pdf/SKILL.md"]
    assert found[1].bundled_files == ("scripts/run.py",)


def test_only_exact_skill_file_name_matches() -> None:
    assert find_skill_files([TreeEntry("docs/MY-SKILL.md", "a", 1)]) == []



def test_instruction_only_folder_has_no_scripts() -> None:
    assert script_presence("skills/a/SKILL.md", ("references/guide.md", "LICENSE.txt")) == "none"
    assert script_presence("skills/a/SKILL.md", ()) == "none"


def test_script_files_and_folders_count_as_scripts() -> None:
    assert script_presence("skills/a/SKILL.md", ("scripts/run",)) == "present"
    assert script_presence("skills/a/SKILL.md", ("tools/Convert.PY",)) == "present"
    assert script_presence("SKILL.md", ("build.sh",)) == "present"


def test_folders_that_cannot_be_listed_are_unknown() -> None:
    assert script_presence("SKILL.md", ()) == "unknown"
    full = tuple(f"references/{index}.md" for index in range(MAX_BUNDLED_FILES))
    assert script_presence("skills/a/SKILL.md", full) == "unknown"
