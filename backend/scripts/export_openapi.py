"""OpenAPI 스키마를 frontend/src/api/openapi.json으로 내보낸다 (프론트 `npm run gen:api`의 입력).

    cd backend && uv run python -m scripts.export_openapi

DB에 접속하지 않는다(엔진은 지연 연결). 개발용 라우트(_dev)는 포함하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import Settings
from app.main import build_app

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


def build_openapi() -> dict[str, Any]:
    return build_app(Settings(env="test", mail_backend="memory")).openapi()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_openapi(), ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
