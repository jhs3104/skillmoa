"""skills.json 계약. 사이트는 이 스키마로 생성된 파일만 읽는다.

실행하면 site/src/data/skills.schema.json과 taxonomy.json을 다시 생성한다.
"""

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from collector.domain.models import (
    LEGACY_SUBCATEGORIES,
    SUBCATEGORY_PARENT,
    Category,
    Difficulty,
    Role,
    Subcategory,
)
from collector.domain.tree import ScriptPresence

SITE_SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[4] / "site/src/data/skills.schema.json"
TAXONOMY_PATH = SCHEMA_PATH.with_name("taxonomy.json")


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
    # v6 이전 요약에는 없다.
    subcategory: Subcategory | None = None
    tags: SiteTags
    runs_external_code: bool
    accesses_network: bool
    requires_external_account: bool
    # 폴더의 파일 목록에서 정한 사실이다. AI 판단과 달리 확인할 수 있다.
    script_files: ScriptPresence
    prompt_version: str


class SiteData(_CamelModel):
    schema_version: int = SITE_SCHEMA_VERSION
    bootstrapped_on: date | None = None
    repositories: tuple[SiteRepository, ...] = ()
    skills: tuple[SiteSkill, ...] = ()


def render_schema() -> str:
    schema = SiteData.model_json_schema(by_alias=True)
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_taxonomy() -> str:
    """대분류마다 세부 분류를 순서대로 담는다. 사이트는 이 파일로 필터 칩을 만든다.

    예전 세부 분류는 다시 분류되는 동안만 남는 값이라 칩으로 만들지 않는다.
    """
    taxonomy = {
        category.value: [
            subcategory.value
            for subcategory, parent in SUBCATEGORY_PARENT.items()
            if parent is category and subcategory not in LEGACY_SUBCATEGORIES
        ]
        for category in Category
    }
    return json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8")
    TAXONOMY_PATH.write_text(render_taxonomy(), encoding="utf-8")
