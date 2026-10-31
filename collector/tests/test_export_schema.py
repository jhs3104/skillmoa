import json
from pathlib import Path

from collector.export.schema import SCHEMA_PATH, SiteData, render_schema

SITE_DATA_DIR = Path(__file__).resolve().parents[2] / "site/src/data"


def test_committed_schema_matches_models() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema()


def test_committed_site_data_matches_contract() -> None:
    raw = (SITE_DATA_DIR / "skills.json").read_text(encoding="utf-8")
    SiteData.model_validate(json.loads(raw))


def test_site_data_serializes_as_camel_case() -> None:
    assert "schemaVersion" in SiteData().model_dump(by_alias=True)
