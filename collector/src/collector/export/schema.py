"""skills.json 계약. 사이트는 이 스키마로 생성된 파일만 읽는다.

실행하면 site/src/data/skills.schema.json을 다시 생성한다.
"""

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from collector.domain.models import Category, Difficulty, Role

SITE_SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "site/src/data/skills.schema.json"


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)


class SiteRepository(_CamelModel):
    full_name: str
    stars: int
    pushed_at: date
    license: str | None
    default_branch: str


class SiteTags(_CamelModel):
    roles: tuple[Role, ...]
    use_cases: tuple[str, ...]
    difficulty: Difficulty


class SiteSkill(_CamelModel):
    slug: str
    rank: int
    name: str
    repository: str
    path: str
    license: str | None
    first_seen_at: date
    summary: str
    use_when: str
    category: Category
    tags: SiteTags
    runs_external_code: bool
    accesses_network: bool
    prompt_version: str


class SiteData(_CamelModel):
    schema_version: int = SITE_SCHEMA_VERSION
    bootstrapped_on: date | None = None
    repositories: tuple[SiteRepository, ...] = ()
    skills: tuple[SiteSkill, ...] = ()


def render_schema() -> str:
    schema = SiteData.model_json_schema(by_alias=True)
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8")
