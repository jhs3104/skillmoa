"""소규모 실행의 원문과 요약을 summary-reviewer가 대조할 수 있게 저장한다."""

from pathlib import Path

from collector.domain.identity import repository_key, skill_dir
from collector.domain.models import CollectorState
from collector.pipeline.content import SkillContentStore
from collector.store import write_json


def write_samples(
    state: CollectorState, keys: list[str], content: SkillContentStore, directory: Path
) -> None:
    for key in keys:
        skill = state.skills[key]
        repository = state.repositories[repository_key(skill.repository)]
        source = content.read(repository, skill.path, skill.skill_md_hash)
        if source is None:
            continue
        folder = directory / _sample_name(skill.repository, skill.path)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "source.md").write_text(source, encoding="utf-8")
        record = state.summaries.get(key)
        if record is not None:
            write_json(folder / "summary.json", record.model_dump(mode="json"))


def _sample_name(repository: str, path: str) -> str:
    owner, _, name = repository.partition("/")
    skill = skill_dir(path).replace("/", "_") or "root"
    return f"{owner}__{name}__{skill}"
