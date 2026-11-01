"""사람이 관리하는 목록(awesome 리스트, 플러그인 marketplace.json)을 파싱한다."""

import json
import re
from typing import Any

_REPOSITORY_LINK = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+)")
_NON_REPOSITORY_OWNERS = {
    "apps",
    "features",
    "marketplace",
    "orgs",
    "settings",
    "sponsors",
    "topics",
    "users",
}


def parse_repository_links(markdown: str) -> set[str]:
    repositories: set[str] = set()
    for owner, name in _REPOSITORY_LINK.findall(markdown):
        cleaned = name.removesuffix(".git").rstrip(".")
        if owner.lower() not in _NON_REPOSITORY_OWNERS and cleaned:
            repositories.add(f"{owner}/{cleaned}")
    return repositories


def parse_marketplace(raw: str, host_repository: str) -> set[str]:
    """외부 저장소를 가리키는 플러그인과 marketplace가 있는 저장소를 함께 돌려준다."""
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    repositories = {host_repository}
    for plugin in manifest.get("plugins", []):
        source = plugin.get("source") if isinstance(plugin, dict) else None
        repository = _plugin_repository(source)
        if repository:
            repositories.add(repository)
    return repositories


def _plugin_repository(source: Any) -> str | None:
    if not isinstance(source, dict):
        return None
    if source.get("source") == "github":
        return source.get("repo")
    if source.get("source") == "url":
        links = parse_repository_links(source.get("url", ""))
        return min(links) if links else None
    return None
