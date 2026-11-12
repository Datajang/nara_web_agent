"""공고번호로 열기: DB → G2B 단건 조회 (SPEC §6.2 lookup, Q5 확인 2026-11-12)."""

from datetime import timedelta

import httpx
from sqlalchemy import func, select

from app.db.models import Bid, UsageLog
from tests.conftest import NOW, build_api, make_auth_settings
from tests.fakes.g2b import prespec_item, regular_item
from tests.helpers import member, seed

LOOKUP = "/api/v1/bids/lookup"


async def _bid_count(api) -> int:
    async with api.ctx.deps.db.session() as s:
        return int(await s.scalar(select(func.count()).select_from(Bid)) or 0)


async def test_db_hit_does_not_call_g2b(full_api, fake_g2b):
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK80000001", NOW))
    calls = fake_g2b.calls
    c = await member(full_api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R26BK80000001"})
    assert r.json() == {"bid_id": f"b{bid_id}"}
    assert fake_g2b.calls == calls


async def test_db_miss_fetches_from_g2b_stores_latest_revision_once(full_api, fake_g2b):
    old = NOW - timedelta(days=60)  # 수집 커버리지 밖의 오래된 공고
    fake_g2b.add(
        "regular",
        regular_item("R26BK80000002", old, ord="000", title="원공고"),
        regular_item("R26BK80000002", old, ord="001", title="정정공고"),
    )
    c = await member(full_api, "a@corp.example")
    first = await c.get(LOOKUP, params={"bid_no": " R26BK80000002 "})
    assert first.status_code == 200
    calls = fake_g2b.calls
    second = await c.get(LOOKUP, params={"bid_no": "R26BK80000002"})
    assert second.json() == first.json()
    assert fake_g2b.calls == calls  # 두 번째는 DB에서
    detail = (await c.get(f"/api/v1/bids/{first.json()['bid_id']}")).json()
    assert detail["title"] == "정정공고"
    assert await _bid_count(full_api) == 1


async def test_prespec_number_falls_through_to_prespec_lookup(full_api, fake_g2b):
    fake_g2b.add("prespec", prespec_item("R26BD80000003", NOW - timedelta(days=40)))
    c = await member(full_api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R26BD80000003"})
    assert r.status_code == 200
    detail = (await c.get(f"/api/v1/bids/{r.json()['bid_id']}")).json()
    assert detail["source"] == "prespec"


async def test_unknown_number_is_404_and_calls_are_logged_for_budget(full_api, fake_g2b):
    c = await member(full_api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R00000000000"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert fake_g2b.calls == 2  # 공고 1회 + 사전규격 1회
    async with full_api.ctx.deps.db.session() as s:
        logged = (await s.execute(select(UsageLog.event, UsageLog.g2b_calls))).all()
    assert [tuple(x) for x in logged] == [("search", 2)]


async def test_rows_for_other_numbers_are_ignored(full_api, fake_g2b):
    """필터를 무시한 응답(검색용 API 같은)이 와도 다른 공고를 엉뚱하게 열지 않는다."""
    other = regular_item("R26BK89999999", NOW)
    fake_g2b.fail(
        httpx.Response(
            200,
            json={
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "정상"},
                    "body": {"items": [other], "totalCount": 1},
                }
            },
        )
    )
    c = await member(full_api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R26BK80000004"})
    assert r.status_code == 404
    assert await _bid_count(full_api) == 0


async def test_g2b_failure_is_503_not_404(full_api, fake_g2b):
    fake_g2b.fail(*[httpx.Response(500) for _ in range(4)])
    c = await member(full_api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R26BK80000005"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "g2b_unavailable"


async def test_without_g2b_client_db_miss_is_404(db, clock):
    api = build_api(db, make_auth_settings(), clock, g2b=None)
    c = await member(api, "a@corp.example")
    r = await c.get(LOOKUP, params={"bid_no": "R26BK80000006"})
    assert r.status_code == 404
