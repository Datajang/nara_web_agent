"""낙찰 분야 태그(fields) 다시 계산 (SPEC §15.3). org_settings.field_keywords를 바꾼 뒤 실행한다.

같이 하는 일: bids에 나중에 들어온 공고의 추정가격으로 estimated_price·award_ratio를 다시 채운다.
G2B를 부르지 않는다(DB만). 같은 사전이면 몇 번 돌려도 결과가 같다. 본체는 app/awards/reclassify.py.

실행: NARA_ENV_FILE=.env uv run python -m scripts.reclassify_awards [--batch 2000]
"""

from __future__ import annotations

import argparse
import asyncio

from app.awards.reclassify import reclassify
from app.config import get_settings
from app.db.session import Database


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=2000)
    args = ap.parse_args()
    st = get_settings()
    db = Database(st.database_url, 2, 1)
    try:
        r = await reclassify(db, args.batch)
    finally:
        await db.dispose()
    print(f"scanned={r.scanned} fields_changed={r.fields_changed}", end=" ")
    print(f"prices_changed={r.prices_changed}")


if __name__ == "__main__":
    asyncio.run(main())
