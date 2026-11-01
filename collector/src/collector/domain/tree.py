"""git tree 항목에서 SKILL.md와 함께 배포되는 파일을 찾는다."""

from dataclasses import dataclass

from collector.domain.identity import SKILL_FILE, skill_dir

MAX_BUNDLED_FILES = 30


@dataclass(frozen=True)
class TreeEntry:
    path: str
    sha: str
    size: int


@dataclass(frozen=True)
class SkillFile:
    path: str
    sha: str
    bundled_files: tuple[str, ...]


def find_skill_files(entries: list[TreeEntry]) -> list[SkillFile]:
    paths = sorted(entry.path for entry in entries)
    found = [
        SkillFile(entry.path, entry.sha, _bundled_files(entry.path, paths))
        for entry in entries
        if entry.path.rpartition("/")[2] == SKILL_FILE
    ]
    return sorted(found, key=lambda skill: skill.path)


def _bundled_files(skill_path: str, paths: list[str]) -> tuple[str, ...]:
    directory = skill_dir(skill_path)
    if not directory:
        return ()
    prefix = f"{directory}/"
    bundled = [path.removeprefix(prefix) for path in paths if path.startswith(prefix)]
    return tuple(path for path in bundled if path != SKILL_FILE)[:MAX_BUNDLED_FILES]
