"""저장소와 스킬의 식별자. 상태 키와 사이트 URL이 여기서 나온다."""

import hashlib
import re

SKILL_FILE = "SKILL.md"
_UNSAFE = re.compile(r"[^a-z0-9._-]+")


def repository_key(full_name: str) -> str:
    """GitHub 저장소 이름은 대소문자를 구분하지 않으므로 소문자로 통일한다."""
    return full_name.lower()


def skill_key(full_name: str, path: str) -> str:
    """경로는 대소문자를 구분하므로 원본 그대로 유지한다."""
    return f"{repository_key(full_name)}:{path}"


def skill_dir(path: str) -> str:
    """SKILL.md가 들어 있는 폴더. 저장소 루트에 있으면 빈 문자열이다."""
    return path.rpartition("/")[0]


def skill_slug(full_name: str, path: str) -> str:
    """URL에 쓰는 슬러그. 변환으로 정보가 사라지면 경로 해시를 붙여 충돌을 막는다."""
    raw = "/".join(part for part in (repository_key(full_name), skill_dir(path)) if part)
    slug = "--".join(_clean(segment) for segment in raw.split("/"))
    if slug.replace("--", "/") == raw:
        return slug
    digest = hashlib.sha256(path.encode()).hexdigest()[:8]
    return f"{slug}-{digest}"


def _clean(segment: str) -> str:
    return _UNSAFE.sub("-", segment.lower()).strip("-") or "skill"
