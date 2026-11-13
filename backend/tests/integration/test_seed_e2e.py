"""E2E 시험 데이터(scripts/seed_e2e.py, §12.8 main 병합 스모크). 외부 호출 없이 검색·분석이 된다."""

import pytest
from sqlalchemy import func, select

from app.db.models import Bid, CollectorCoverage
from scripts import seed_e2e
from tests.conftest import NOW
from tests.helpers import login, make_profile, sse


async def test_seed_is_idempotent_and_searchable_offline(full_api, fake_g2b):
    for _ in range(2):
        await seed_e2e.seed(full_api.db, "e2e-admin@corp.example", "e2e-admin-password-1", now=NOW)
    async with full_api.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(Bid)) == len(seed_e2e.TITLES)
        cov = (await s.scalars(select(CollectorCoverage))).all()
    assert {c.source for c in cov} == {"regular", "prespec"}
    assert all(c.covered_to > NOW for c in cov)  # 검색 창이 커버리지 안 → G2B를 부르지 않는다

    async with full_api.client() as c:
        assert (await login(c, "e2e-admin@corp.example", "e2e-admin-password-1")).status_code == 200
        r = await c.post("/api/v1/bids/search", json={"keywords": ["클라우드"], "days": 7})
        body = r.json()
        assert r.status_code == 200 and body["items"] and not body.get("collecting")
        pid = await make_profile(c)
        events = await sse(
            c, f"/api/v1/bids/{body['items'][0]['bid_id']}/analyze", {"profile_id": pid}
        )
    assert events[-1]["type"] == "done" and any(e["type"] == "result" for e in events)
    assert fake_g2b.calls == 0


async def test_seed_refuses_production(full_api, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(SystemExit):
        seed_e2e.guard()


async def test_seed_adds_a_member_without_team_for_the_invite_flow(full_api):
    member = ("e2e-member@corp.example", "e2e-member-password-1")
    await seed_e2e.seed(
        full_api.db, "e2e-admin@corp.example", "e2e-admin-password-1", now=NOW, member=member
    )
    async with full_api.client() as a, full_api.client() as m:
        await login(a, "e2e-admin@corp.example", "e2e-admin-password-1")
        assert (await login(m, *member)).status_code == 200
        code = (await a.post("/api/v1/teams", json={"name": "E2E 팀"})).json()["team"][
            "invite_code"
        ]
        assert (await m.post("/api/v1/teams/join", json={"code": code})).status_code == 200
    # 다시 시드하면 초대 흐름을 처음부터 다시 할 수 있게 회원은 팀 밖으로
    await seed_e2e.seed(
        full_api.db, "e2e-admin@corp.example", "e2e-admin-password-1", now=NOW, member=member
    )
    async with full_api.client() as m:
        await login(m, *member)
        me = (await m.get("/api/v1/me")).json()
    assert me["team"] is None and me["role"] == "member"
