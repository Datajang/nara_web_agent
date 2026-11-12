"""P6 팀 (SPEC §13 P6 팀 규칙 1~5). 관리자 없이 회원이 만들고 초대 코드로 초대, 한 계정 한 팀."""

from typing import Any

import pytest

from tests.helpers import member

T = "/api/v1/teams"


@pytest.fixture
async def people(api) -> Any:
    cs = {n: await member(api, f"{n}@corp.example") for n in ("own", "mem", "out")}
    yield cs
    for c in cs.values():
        await c.aclose()


async def _team(c, name: str = "AI 플랫폼팀") -> dict[str, Any]:
    r = await c.post(T, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def _join(c, code: str) -> Any:
    return await c.post(f"{T}/join", json={"code": code})


def _err(r) -> str:
    return r.json()["error"]["code"]


async def test_create_makes_owner_and_one_team_per_account(people):
    own = people["own"]
    assert (await own.get(f"{T}/me")).json() == {"team": None, "role": None, "members": []}
    t = await _team(own)
    assert t["team"]["name"] == "AI 플랫폼팀" and t["role"] == "owner"
    assert len(t["team"]["invite_code"]) == 10
    assert [m["role"] for m in t["members"]] == ["owner"]
    r = await own.post(T, json={"name": "두 번째"})
    assert r.status_code == 409 and _err(r) == "already_in_team"


async def test_join_with_code_and_rules(people):
    own, mem, out = people["own"], people["mem"], people["out"]
    code = (await _team(own))["team"]["invite_code"]
    bad = await _join(mem, "WRONGCODE1")
    assert bad.status_code == 404 and _err(bad) == "invalid_invite"
    ok = await _join(mem, code)
    assert ok.status_code == 200 and ok.json()["role"] == "member"
    again = await _join(mem, code)
    assert again.status_code == 409 and _err(again) == "already_in_team"
    seen = (await mem.get(f"{T}/me")).json()
    assert seen["team"]["invite_code"] == code  # 팀원 누구나 초대 코드를 본다
    assert sorted(m["role"] for m in seen["members"]) == ["member", "owner"]
    other = await _team(out, "다른 팀")
    assert (await _join(own, other["team"]["invite_code"])).status_code == 409


async def test_owner_only_actions(people):
    own, mem = people["own"], people["mem"]
    code = (await _team(own))["team"]["invite_code"]
    await _join(mem, code)
    mem_id = next(
        m["user_id"] for m in (await own.get(f"{T}/me")).json()["members"] if m["role"] == "member"
    )
    for method, path, body in (
        ("PATCH", f"{T}/me", {"name": "바꿈"}),
        ("POST", f"{T}/me/invite-code", None),
        ("DELETE", f"{T}/me/members/{mem_id}", None),
    ):
        r = await mem.request(method, path, json=body)
        assert r.status_code == 403 and _err(r) == "not_team_owner", path
    assert (await own.patch(f"{T}/me", json={"name": "바꾼 이름"})).json()["team"][
        "name"
    ] == "바꾼 이름"


async def test_rotating_code_invalidates_the_old_one(people):
    own, mem = people["own"], people["mem"]
    old = (await _team(own))["team"]["invite_code"]
    new = (await own.post(f"{T}/me/invite-code")).json()["team"]["invite_code"]
    assert new != old
    assert (await _join(mem, old)).status_code == 404
    assert (await _join(mem, new)).status_code == 200


async def test_owner_removes_member_but_not_self(people):
    own, mem = people["own"], people["mem"]
    await _join(mem, (await _team(own))["team"]["invite_code"])
    members = (await own.get(f"{T}/me")).json()["members"]
    own_id = next(m["user_id"] for m in members if m["role"] == "owner")
    mem_id = next(m["user_id"] for m in members if m["role"] == "member")
    r = await own.delete(f"{T}/me/members/{own_id}")
    assert r.status_code == 422
    assert (await own.delete(f"{T}/me/members/{mem_id}")).status_code == 204
    assert (await mem.get(f"{T}/me")).json()["team"] is None


async def test_leaving_passes_ownership_then_last_one_deletes_team(people):
    own, mem, out = people["own"], people["mem"], people["out"]
    code = (await _team(own))["team"]["invite_code"]
    await _join(mem, code)
    await _join(out, code)
    pid = (
        await mem.post(
            "/api/v1/profiles", json={"name": "팀 공용", "description": "AI", "scope": "team"}
        )
    ).json()["id"]
    assert (await own.post(f"{T}/me/leave")).status_code == 204
    after = (await mem.get(f"{T}/me")).json()
    roles = {m["display_name"]: m["role"] for m in after["members"]}
    assert after["role"] == "owner" and len(roles) == 2  # 먼저 들어온 mem이 팀장
    await out.post(f"{T}/me/leave")
    await mem.post(f"{T}/me/leave")
    assert (await mem.get(f"{T}/me")).json()["team"] is None
    assert (await mem.get(f"/api/v1/profiles/{pid}")).status_code == 404  # 팀 프로필도 사라짐
    assert (await own.post(f"{T}/join", json={"code": code})).status_code == 404


async def test_team_profiles_shared_inside_team_only(people):
    own, mem, out = people["own"], people["mem"], people["out"]
    await _join(mem, (await _team(own))["team"]["invite_code"])
    r = await mem.post(
        "/api/v1/profiles", json={"name": "팀 공용", "description": "AI 검색", "scope": "team"}
    )
    assert r.status_code == 201 and r.json()["scope"] == "team"
    pid = r.json()["id"]
    mine = await own.post("/api/v1/profiles", json={"name": "개인", "description": "x"})
    assert mine.json()["scope"] == "personal"
    names = {p["name"]: p["scope"] for p in (await own.get("/api/v1/profiles")).json()["items"]}
    assert names == {"팀 공용": "team", "개인": "personal"}
    assert {p["name"] for p in (await mem.get("/api/v1/profiles")).json()["items"]} == {"팀 공용"}
    assert (
        await own.patch(f"/api/v1/profiles/{pid}", json={"keywords": ["AI", "검색"]})
    ).status_code == 200
    assert (await out.get(f"/api/v1/profiles/{pid}")).status_code == 404
    r = await mem.delete(f"/api/v1/profiles/{pid}")
    assert r.status_code == 403 and _err(r) == "not_team_owner"  # 팀 프로필 삭제는 팀장만
    assert (await own.delete(f"/api/v1/profiles/{pid}")).status_code == 204


async def test_team_profile_needs_a_team(people):
    r = await people["out"].post("/api/v1/profiles", json={"name": "팀", "scope": "team"})
    assert r.status_code == 409 and _err(r) == "no_team"


async def test_me_has_interest_keywords_and_team(people):
    own = people["own"]
    me = (await own.get("/api/v1/me")).json()
    assert me["interest_keywords"] == [] and me["team"] is None
    r = await own.patch(
        "/api/v1/me", json={"interest_keywords": [" AI ", "검색", "AI", "데이터 플랫폼"]}
    )
    assert r.json()["interest_keywords"] == ["AI", "검색", "데이터 플랫폼"]
    await _team(own)
    me = (await own.get("/api/v1/me")).json()
    assert me["team"]["name"] == "AI 플랫폼팀" and me["team_role"] == "owner"
