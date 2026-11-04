"""도구 업데이트를 하루 단위로 묶는 규칙 (ADR-0022). 외부 호출 없는 순수 함수다."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta

from collector.domain.models import Tool, ToolUpdateRecord

__all__ = [
    "Tool",
    "ToolRelease",
    "ToolReleaseGroup",
    "group_releases",
    "needs_tool_summary",
    "prune_tool_updates",
    "update_key",
]


@dataclass(frozen=True)
class ToolRelease:
    tool: Tool
    version: str
    published: date
    url: str
    notes: str


@dataclass(frozen=True)
class ToolReleaseGroup:
    """한 도구가 하루에 낸 릴리스. 요약은 이 단위로 한 번 한다."""

    tool: Tool
    day: date
    versions: tuple[str, ...]
    url: str
    notes: str
    source_hash: str


def update_key(tool: Tool, day: date) -> str:
    return f"{tool.value}:{day.isoformat()}"


def group_releases(
    releases: Iterable[ToolRelease], *, today: date, window_days: int
) -> dict[tuple[Tool, date], ToolReleaseGroup]:
    """최근 window_days 안의 릴리스를 도구·날짜로 묶는다. 대표 링크는 그날 마지막 버전이다."""
    oldest = today - timedelta(days=window_days)
    buckets: defaultdict[tuple[Tool, date], list[ToolRelease]] = defaultdict(list)
    for item in releases:
        if oldest <= item.published <= today:
            buckets[item.tool, item.published].append(item)
    groups: dict[tuple[Tool, date], ToolReleaseGroup] = {}
    for (tool, day), items in sorted(buckets.items()):
        ordered = sorted(items, key=lambda item: _version_key(item.version))
        notes = "\n\n".join(f"## {item.version}\n{item.notes.strip()}" for item in ordered)
        groups[tool, day] = ToolReleaseGroup(
            tool=tool,
            day=day,
            versions=tuple(item.version for item in ordered),
            url=ordered[-1].url,
            notes=notes,
            source_hash=hashlib.sha256(notes.encode()).hexdigest(),
        )
    return groups


def needs_tool_summary(
    record: ToolUpdateRecord | None, group: ToolReleaseGroup, prompt_version: str
) -> bool:
    return (
        record is None
        or record.source_hash != group.source_hash
        or record.prompt_version != prompt_version
    )


def prune_tool_updates(
    records: Mapping[str, ToolUpdateRecord], *, today: date, keep_days: int
) -> dict[str, ToolUpdateRecord]:
    oldest = today - timedelta(days=keep_days)
    return {key: record for key, record in records.items() if record.day >= oldest}


def _version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """2.1.9가 2.1.10보다 앞에 오도록 숫자 부분은 숫자로 비교한다."""
    parts: list[tuple[int, int | str]] = []
    for part in version.replace("-", ".").split("."):
        parts.append((0, int(part)) if part.isdigit() else (1, part))
    return tuple(parts)
