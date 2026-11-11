"""프론트 타입의 원천인 openapi.json이 최신인지 (§6: CI에서 최신 여부 검사)."""

import json
from pathlib import Path

from scripts.export_openapi import build_openapi

COMMITTED = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "openapi.json"


def test_committed_openapi_is_up_to_date():
    assert COMMITTED.exists(), "cd backend && uv run python -m scripts.export_openapi"
    assert json.loads(COMMITTED.read_text()) == build_openapi(), (
        "openapi.json이 오래됨: cd backend && uv run python -m scripts.export_openapi"
    )
