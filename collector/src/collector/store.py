"""수집 상태 저장. 키를 정렬해 쓰므로 같은 상태는 항상 같은 바이트가 된다."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from collector.domain.models import CollectorState

_FILES = {
    "repositories.json": ("repositories",),
    "skills.json": ("skills",),
    "summaries.json": ("summaries", "summary_failures", "summary_redo"),
    "meta.json": ("schema_version", "bootstrapped_on", "usage"),
}


def write_json(path: Path, content: Any) -> None:
    """중간에 멈춰도 이전 파일이 남도록 임시 파일을 쓴 뒤 교체한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as file:
        file.write(text)
    os.replace(file.name, path)


def load_state(directory: Path) -> CollectorState:
    fields: dict[str, Any] = {}
    for filename in _FILES:
        path = directory / filename
        if path.exists():
            fields |= json.loads(path.read_text(encoding="utf-8"))
    return CollectorState.model_validate(fields)


def save_state(state: CollectorState, directory: Path) -> None:
    for filename, field_names in _FILES.items():
        write_json(directory / filename, _dump(state, field_names))


def _dump(model: BaseModel, field_names: tuple[str, ...]) -> dict[str, Any]:
    return model.model_dump(mode="json", include=set(field_names))
