"""P6 분석 공유 (SPEC §13 P6): 팀 프로필 분석은 같은 팀원에게만, 개인 프로필 분석은 본인만."""

from tests.conftest import NOW
from tests.fakes.g2b import regular_item
from tests.helpers import make_profile, member, seed, sse


async def _setup(full_api):
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK76000001", NOW))
    a = await member(full_api, "ta@corp.example")
    b = await member(full_api, "tb@corp.example")
    c = await member(full_api, "tc@corp.example")
    code = (await a.post("/api/v1/teams", json={"name": "팀"})).json()["team"]["invite_code"]
    await b.post("/api/v1/teams/join", json={"code": code})
    team_pid = await make_profile(a, scope="team", name="팀 프로필")
    events = await sse(a, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": team_pid})
    return a, b, c, bid_id, events[-2]["analysis_id"]


async def test_teammate_sees_team_analysis_outsider_does_not(full_api):
    a, b, c, bid_id, aid = await _setup(full_api)
    try:
        assert (await b.get(f"/api/v1/bids/b{bid_id}")).json()["team_analysis_id"] == aid
        assert (await b.get(f"/api/v1/analyses/{aid}")).status_code == 200
        team = (await b.get("/api/v1/analyses", params={"scope": "team"})).json()
        assert [(it["analysis_id"], it["profile_name"]) for it in team["items"]] == [
            (aid, "팀 프로필")
        ]
        assert (await b.get("/api/v1/analyses")).json()["items"] == []  # 내 기록은 그대로 본인 것만

        assert (await c.get(f"/api/v1/bids/b{bid_id}")).json()["team_analysis_id"] is None
        assert (await c.get(f"/api/v1/analyses/{aid}")).status_code == 404
        assert (await c.get("/api/v1/analyses", params={"scope": "team"})).json()["items"] == []
        # 팀원이 남의 분석 기록을 지울 수는 없다
        assert (await b.delete(f"/api/v1/analyses/{aid}")).status_code == 404

        await b.post("/api/v1/teams/me/leave")  # 나가면 더는 못 본다
        assert (await b.get(f"/api/v1/analyses/{aid}")).status_code == 404
    finally:
        for x in (a, b, c):
            await x.aclose()


async def test_personal_profile_analysis_stays_private(full_api):
    a, b, c, bid_id, _ = await _setup(full_api)
    try:
        (other,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK76000002", NOW))
        pid = await make_profile(a, name="개인")
        mine = (await sse(a, f"/api/v1/bids/b{other}/analyze", {"profile_id": pid}))[-2]
        assert (await b.get(f"/api/v1/bids/b{other}")).json()["team_analysis_id"] is None
        assert (await b.get(f"/api/v1/analyses/{mine['analysis_id']}")).status_code == 404
    finally:
        for x in (a, b, c):
            await x.aclose()
