"""내 기록·북마크·피드백·관리자 API와 개인 자원 격리 (SPEC §6.2, §6.5-2·8)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import Analysis
from tests.conftest import NOW
from tests.fakes.g2b import regular_item
from tests.helpers import admin_client, make_profile, member, seed, sse


async def _owner_resources(api, fake_g2b):
    """사용자 A가 검색·분석·북마크·대화를 하나씩 만든다."""
    fake_g2b.add("regular", regular_item("R26BK95000001", NOW - timedelta(hours=1), title="AI"))
    (bid_id,) = await seed(api.ctx.deps, "regular", regular_item("R26BK95000002", NOW))
    a = await member(api, "owner@corp.example")
    pid = await make_profile(a)
    run = (await a.post("/api/v1/bids/search", json={"keywords": ["AI"], "days": 7})).json()
    events = await sse(a, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid})
    aid = events[-2]["analysis_id"]
    assert (await a.put(f"/api/v1/bookmarks/b{bid_id}", json={"note": "검토"})).status_code == 204
    cid = (await a.post("/api/v1/conversations", json={"profile_id": pid})).json()["id"]
    return a, {"run": run["run_id"], "aid": aid, "bid": bid_id, "cid": cid, "pid": pid}


FOREIGN = [
    ("GET", "/api/v1/search-runs/{run}", None),
    ("DELETE", "/api/v1/search-runs/{run}", None),
    ("GET", "/api/v1/analyses/{aid}", None),
    ("DELETE", "/api/v1/analyses/{aid}", None),
    ("DELETE", "/api/v1/bookmarks/b{bid}", None),
    ("PUT", "/api/v1/bookmarks/b{bid}", {"analysis_id": "{aid}"}),
    ("GET", "/api/v1/conversations/{cid}/messages", None),
    ("PATCH", "/api/v1/conversations/{cid}", {"title": "탈취"}),
    ("DELETE", "/api/v1/conversations/{cid}", None),
    ("POST", "/api/v1/conversations/{cid}/messages", {"content": "안녕"}),
    ("POST", "/api/v1/conversations", {"profile_id": "{pid}"}),
    ("POST", "/api/v1/bids/b{bid}/analyze", {"profile_id": "{pid}"}),
    ("POST", "/api/v1/recommend", {"profile_id": "{pid}"}),
    ("GET", "/api/v1/profiles/{pid}", None),
    ("POST", "/api/v1/feedback", {"target_type": "analysis", "target_id": "{aid}", "rating": 1}),
]


@pytest.mark.parametrize(("method", "path", "body"), FOREIGN)
async def test_other_users_resources_are_404(full_api, fake_g2b, method, path, body):
    """§6.5-2: 남의 run_id·analysis_id·conversation_id·북마크는 조회·수정·삭제 모두 404."""
    a, ids = await _owner_resources(full_api, fake_g2b)
    b = await member(full_api, "intruder@corp.example")

    def fill(v):
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            return ids[v[1:-1]]
        return v

    payload = {k: fill(v) for k, v in body.items()} if body else None
    r = await b.request(method, path.format(**ids), json=payload)
    assert r.status_code == 404, f"{method} {path} → {r.status_code} {r.text}"
    assert r.json()["error"]["code"] == "not_found"
    # 원래 주인의 자원은 그대로
    assert (await a.get(f"/api/v1/search-runs/{ids['run']}")).status_code == 200
    assert (await a.get(f"/api/v1/analyses/{ids['aid']}")).status_code == 200
    assert len((await a.get("/api/v1/bookmarks")).json()["items"]) == 1
    assert (await a.get(f"/api/v1/conversations/{ids['cid']}/messages")).status_code == 200
    await a.aclose()
    await b.aclose()


async def test_bookmarks_put_is_idempotent_and_delete_twice_404(full_api):
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK96000001", NOW))
    c = await member(full_api, "a@corp.example")
    p = f"/api/v1/bookmarks/b{bid_id}"
    codes = [(await c.put(p, json={"note": n})).status_code for n in ("처음", "바꿈")]
    items = (await c.get("/api/v1/bookmarks")).json()["items"]
    card = (await c.get(f"/api/v1/bids/b{bid_id}")).json()
    first, second = (await c.delete(p)).status_code, (await c.delete(p)).status_code
    unknown = (await c.put("/api/v1/bookmarks/b999999", json={})).status_code
    await c.aclose()
    assert codes == [204, 204] and len(items) == 1 and items[0]["note"] == "바꿈"
    assert items[0]["bid"]["bookmarked"] is True and card["bookmarked"] is True
    assert (first, second, unknown) == (204, 404, 404)


async def test_deleting_my_analysis_keeps_shared_row(full_api):
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK96000002", NOW))
    c = await member(full_api, "a@corp.example")
    pid = await make_profile(c)
    aid = (await sse(c, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid}))[-2]["analysis_id"]
    listed = (await c.get("/api/v1/analyses")).json()
    detail = (await c.get(f"/api/v1/analyses/{aid}")).json()
    assert (await c.delete(f"/api/v1/analyses/{aid}")).status_code == 204
    after = (await c.get("/api/v1/analyses")).json()
    await c.aclose()
    assert listed["total"] == 1 and listed["items"][0]["bid"]["bid_id"] == f"b{bid_id}"
    assert listed["items"][0]["profile_name"] == "우리 팀"  # §7.7 사용한 프로필명
    assert detail["analysis"]["fit"]["verdict"] in {"strong", "possible", "weak"}
    assert detail["markdown"].startswith("## 사업 개요")
    assert after["total"] == 0
    async with full_api.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(Analysis)) == 1


async def test_search_runs_list_and_delete(full_api):
    c = await member(full_api, "a@corp.example")
    run_id = (await c.post("/api/v1/bids/search", json={"days": 3})).json()["run_id"]
    listed = (await c.get("/api/v1/search-runs", params={"kind": "search"})).json()
    deleted = await c.delete(f"/api/v1/search-runs/{run_id}")
    after = (await c.get("/api/v1/search-runs")).json()
    await c.aclose()
    assert listed["total"] == 1 and listed["items"][0]["query"]["days"] == 3
    assert deleted.status_code == 204 and after["total"] == 0


async def test_feedback_on_own_targets(full_api):
    c = await member(full_api, "a@corp.example")
    run_id = (await c.post("/api/v1/bids/search", json={"days": 3})).json()["run_id"]
    ok = await c.post(
        "/api/v1/feedback",
        json={"target_type": "search_run", "target_id": run_id, "rating": -1, "comment": "부족"},
    )
    bad_rating = await c.post(
        "/api/v1/feedback", json={"target_type": "search_run", "target_id": run_id, "rating": 5}
    )
    missing = await c.post(
        "/api/v1/feedback", json={"target_type": "assistant_message", "target_id": 1, "rating": 1}
    )
    await c.aclose()
    assert ok.status_code == 201 and ok.json()["id"] > 0
    assert (bad_rating.status_code, missing.status_code) == (422, 404)


async def test_responses_never_leak_secrets_or_other_emails(full_api, fake_g2b):
    """§6.5-8 (응답 실측): 다른 회원의 응답에 주인 이메일·해시가 나타나지 않는다."""
    a, ids = await _owner_resources(full_api, fake_g2b)
    b = await member(full_api, "viewer@corp.example")
    bodies = [
        (await b.get(p)).text
        for p in (
            "/api/v1/me",
            "/api/v1/search-runs",
            "/api/v1/analyses",
            "/api/v1/bookmarks",
            "/api/v1/conversations",
            "/api/v1/profiles",
            f"/api/v1/bids/b{ids['bid']}",
        )
    ]
    bodies.append((await b.post("/api/v1/bids/search", json={"keywords": ["AI"], "days": 7})).text)
    await a.aclose()
    await b.aclose()
    for text in bodies:
        assert "owner@corp.example" not in text
        assert "password_hash" not in text and "$argon2" not in text and "token_hash" not in text


def test_response_schemas_have_no_secret_fields():
    """§6.5-8 (스키마): 응답 모델에 비밀번호 해시·토큰 해시가 없고, email은 본인·관리자 모델에만."""
    from scripts.export_openapi import build_openapi

    schemas = build_openapi()["components"]["schemas"]
    email_ok = {"MeOut", "AdminUserOut", "DevMail", "RegisterIn", "LoginIn", "EmailIn"}
    for name, sch in schemas.items():
        props = set(sch.get("properties", {}))
        assert not props & {"password_hash", "token_hash", "family_id", "password"} or name in {
            "RegisterIn",
            "LoginIn",
            "ResetIn",
        }, name
        if "email" in props:
            assert name in email_ok, name


async def test_admin_usage_and_collector(full_api, fake_g2b):
    fake_g2b.add("regular", regular_item("R26BK97000001", NOW - timedelta(hours=1)))
    adm = await admin_client(full_api)
    await adm.post("/api/v1/bids/search", json={"days": 2, "source": "regular"})
    usage = (await adm.get("/api/v1/admin/usage")).json()["items"]
    started = await adm.post("/api/v1/admin/collector/run", json={"source": "regular"})
    import asyncio

    for _ in range(30):
        body = (await adm.get("/api/v1/admin/collector/runs")).json()
        runs, coverage = body["items"], body["coverage"]
        if any(r["mode"] == "incremental" and r["status"] != "running" for r in runs):
            break
        await asyncio.sleep(0.1)
    member_c = await member(full_api, "m@corp.example")
    forbidden = await member_c.get("/api/v1/admin/usage")
    await adm.aclose()
    await member_c.aclose()
    search_row = next(r for r in usage if r["event"] == "search")
    assert {"prompt_tokens", "completion_tokens"} <= set(search_row)  # §7.9 입력·출력 토큰
    assert [c["source"] for c in coverage] == ["regular"]
    assert search_row["requests"] == 1 and search_row["hit_rate"]["bids_db"] == 0.0
    assert started.status_code == 202
    assert any(r["mode"] == "incremental" for r in runs)
    assert forbidden.status_code == 403


async def test_feedback_stores_reason_model_and_prompt_version(full_api, fake_g2b):
    """§12.7-1: 👎 사유 코드와 대상의 model·prompt_version을 함께 저장한다."""
    from app.db.models import Feedback

    a, ids = await _owner_resources(full_api, fake_g2b)
    down = await a.post(
        "/api/v1/feedback",
        json={
            "target_type": "analysis",
            "target_id": ids["aid"],
            "rating": -1,
            "reason": "missing",
        },
    )
    run_fb = await a.post(
        "/api/v1/feedback", json={"target_type": "search_run", "target_id": ids["run"], "rating": 1}
    )
    up_with_reason = await a.post(
        "/api/v1/feedback",
        json={"target_type": "search_run", "target_id": ids["run"], "rating": 1, "reason": "wrong"},
    )
    unknown_reason = await a.post(
        "/api/v1/feedback",
        json={"target_type": "search_run", "target_id": ids["run"], "rating": -1, "reason": "spam"},
    )
    await a.aclose()
    assert (down.status_code, run_fb.status_code) == (201, 201)
    assert (up_with_reason.status_code, unknown_reason.status_code) == (422, 422)
    async with full_api.db.session() as s:
        analysis = await s.get(Analysis, ids["aid"])
        rows = {f.target_type: f for f in (await s.scalars(select(Feedback))).all()}
    assert analysis is not None
    fa = rows["analysis"]
    assert (fa.reason, fa.model, fa.prompt_version) == (
        "missing",
        analysis.model_id,
        analysis.prompt_version,
    )
    fr = rows["search_run"]
    settings = full_api.ctx.deps.settings
    assert fr.reason is None and fr.model == settings.llm_model_id
    assert fr.prompt_version == f"v6+{settings.llm_model_id}"


async def test_admin_usage_includes_feedback_by_reason(full_api, fake_g2b):
    """§12.7-2: 운영자가 👎를 사유별로 모아 본다(관리자 사용량 화면)."""
    a, ids = await _owner_resources(full_api, fake_g2b)
    for reason in ("missing", "missing", "too_long"):
        r = await a.post(
            "/api/v1/feedback",
            json={
                "target_type": "analysis",
                "target_id": ids["aid"],
                "rating": -1,
                "reason": reason,
            },
        )
        assert r.status_code == 201
    await a.post(
        "/api/v1/feedback", json={"target_type": "search_run", "target_id": ids["run"], "rating": 1}
    )
    await a.aclose()
    admin = await admin_client(full_api)
    body = (await admin.get("/api/v1/admin/usage")).json()
    await admin.aclose()
    fb = {(x["target_type"], x["rating"], x["reason"]): x["count"] for x in body["feedback"]}
    assert fb == {
        ("analysis", -1, "missing"): 2,
        ("analysis", -1, "too_long"): 1,
        ("search_run", 1, None): 1,
    }
