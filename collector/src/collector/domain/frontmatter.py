"""SKILL.md의 YAML frontmatter에서 필요한 값만 읽는다.

외부 파일을 다루므로 형식이 틀려도 예외를 내지 않고 본문으로 취급한다.
"""

import re
from dataclasses import dataclass

_BLOCK = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_KEY = re.compile(r"^([A-Za-z_-]+):[ \t]*(.*)$")
_BLOCK_SCALARS = {"|", ">", "|-", ">-", "|+", ">+"}
MAX_LICENSE_CHARS = 80


@dataclass(frozen=True)
class SkillDocument:
    name: str | None
    description: str | None
    license: str | None
    body: str


def parse_skill_document(text: str) -> SkillDocument:
    match = _BLOCK.match(text)
    if match is None:
        return SkillDocument(None, None, None, text.strip())
    fields = _parse_fields(match.group(1))
    return SkillDocument(
        name=fields.get("name") or None,
        description=fields.get("description") or None,
        license=(fields.get("license") or "")[:MAX_LICENSE_CHARS] or None,
        body=text[match.end() :].strip(),
    )


def _parse_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    key: str | None = None
    for line in block.splitlines():
        matched = _KEY.match(line)
        if matched:
            key, value = matched.group(1), matched.group(2).strip()
            fields[key] = "" if value in _BLOCK_SCALARS else _unquote(value)
        elif key is not None and line[:1] in (" ", "\t"):
            fields[key] = f"{fields[key]} {line.strip()}".strip()
    return fields


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value
