"""git tree 항목에서 SKILL.md와 함께 배포되는 파일을 찾는다."""

from dataclasses import dataclass
from typing import Literal

from collector.domain.identity import SKILL_FILE, skill_dir

MAX_BUNDLED_FILES = 30

ScriptPresence = Literal["none", "present", "unknown"]
_SCRIPT_SUFFIXES = (
    ".py", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".js", ".mjs", ".cjs",
    ".ts", ".mts", ".rb", ".pl", ".php", ".go", ".rs", ".swift", ".java", ".kt", ".lua",
)
_SCRIPT_DIRS = ("scripts/", "bin/")


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



def script_presence(skill_path: str, files: tuple[str, ...]) -> ScriptPresence:
    """스킬 폴더에 실행할 수 있는 파일이 있는지 파일 목록으로 정한다.

    저장소 루트의 스킬은 폴더를 가를 수 없고, 목록이 상한에서 잘렸으면 뒤를 볼 수 없어 unknown이다.
    """
    if any(_is_script(file) for file in files):
        return "present"
    if not skill_dir(skill_path) or len(files) >= MAX_BUNDLED_FILES:
        return "unknown"
    return "none"


def _is_script(file: str) -> bool:
    return file.lower().endswith(_SCRIPT_SUFFIXES) or file.startswith(_SCRIPT_DIRS)
