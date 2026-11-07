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
    "classifications.json": ("classifications",),
    "star_history.json": ("star_history",),
    # 도구 소식 워크플로만 고치는 파일. 스킬 수집과 커밋이 겹쳐도 충돌하지 않게 나눈다.
    "tool_updates.json": ("tool_updates", "tool_news_usage"),
    "meta.json": ("schema_version", "bootstrapped_on", "last_full_scan_on", "usage"),
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


TOOL_NEWS_FILE = "tool_updates.json"


def save_state(state: CollectorState, directory: Path, only: tuple[str, ...] | None = None) -> None:
    """only를 주면 그 파일만 쓴다. 다른 워크플로가 맡은 파일을 다시 쓰지 않기 위해서다.

    필드가 늘어난 모델로 저장하면 내용이 같아도 바이트가 달라진다. 도구 소식 워크플로가
    스킬 상태 파일을 다시 쓰면 커밋하지 않은 변경이 남아 rebase가 멈춘다.
    """
    for filename, field_names in _FILES.items():
        if only is None or filename in only:
            write_json(directory / filename, _dump(state, field_names))


def _dump(model: BaseModel, field_names: tuple[str, ...]) -> dict[str, Any]:
    return model.model_dump(mode="json", include=set(field_names))
