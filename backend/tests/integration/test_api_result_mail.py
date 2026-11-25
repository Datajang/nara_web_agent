"""결과 메일 켜기·끄기 API (계획 Task 9)."""

from __future__ import annotations

from datetime import timedelta

from tests.conftest import NOW
from tests.fakes.g2b import kst_str, prespec_item, regular_item
from tests.helpers import member, seed


def _regular(no: str, opening) -> dict:
    it = regular_item(no, NOW - timedelta(days=1))
    it["opengDt"] = kst_str(opening)
    return it


async def test_put_bookmark_returns_watching(full_api):
    (bid_id,) = await seed(
        full_api.ctx.deps, "regular", _regular("R26BK93000001", NOW + timedelta(days=3))
    )
    c = await member(full_api, "a@corp.example")
    r = await c.put(f"/api/v1/bookmarks/b{bid_id}", json={})
    items = (await c.get("/api/v1/bookmarks")).json()["items"]
    await c.aclose()
    assert r.status_code == 200
    body = r.json()
    assert (body["notify_result"], body["watching"]) == (True, True)
    assert body["opening_at"].startswith("2026-11-13")
    assert items[0]["notify_result"] is True


async def test_put_bookmark_prespec_not_watching(full_api):
    (bid_id,) = await seed(
        full_api.ctx.deps, "prespec", prespec_item("R26BD93000001", NOW - timedelta(days=1))
    )
    c = await member(full_api, "a@corp.example")
    r = await c.put(f"/api/v1/bookmarks/b{bid_id}", json={})
    await c.aclose()
    assert r.status_code == 200
    assert (r.json()["watching"], r.json()["opening_at"]) == (False, None)


async def test_patch_bookmark_notify_off_on(full_api):
    (bid_id,) = await seed(
        full_api.ctx.deps, "regular", _regular("R26BK93000002", NOW + timedelta(days=3))
    )
    c = await member(full_api, "a@corp.example")
    p = f"/api/v1/bookmarks/b{bid_id}"
    await c.put(p, json={})
    off = await c.patch(p, json={"notify_result": False})
    after_off = (await c.get("/api/v1/bookmarks")).json()["items"][0]["notify_result"]
    on = await c.patch(p, json={"notify_result": True})
    after_on = (await c.get("/api/v1/bookmarks")).json()["items"][0]["notify_result"]
    await c.aclose()
    assert (off.status_code, on.status_code) == (200, 200)
    assert (after_off, after_on) == (False, True)
    assert on.json()["watching"] is True


async def test_patch_other_users_bookmark_404(full_api):
    (bid_id,) = await seed(
        full_api.ctx.deps, "regular", _regular("R26BK93000003", NOW + timedelta(days=3))
    )
    a = await member(full_api, "a@corp.example")
    b = await member(full_api, "b@corp.example")
    await a.put(f"/api/v1/bookmarks/b{bid_id}", json={})
    r = await b.patch(f"/api/v1/bookmarks/b{bid_id}", json={"notify_result": False})
    mine = (await a.get("/api/v1/bookmarks")).json()["items"][0]["notify_result"]
    await a.aclose()
    await b.aclose()
    assert r.status_code == 404
    assert mine is True


async def test_me_result_mail_toggle(full_api):
    c = await member(full_api, "a@corp.example")
    before = (await c.get("/api/v1/me")).json()["result_mail"]
    r = await c.patch("/api/v1/me", json={"result_mail": False})
    after = (await c.get("/api/v1/me")).json()["result_mail"]
    await c.aclose()
    assert (before, r.status_code, r.json()["result_mail"], after) == (True, 200, False, False)


async def test_put_bookmark_after_result_not_watching(full_api):
    """결과가 이미 나왔거나(final) 개찰 7일 지난 공고: watching=false, 개찰일은 준다."""
    from app.db.models import BidResultWatch

    deps = full_api.ctx.deps
    done, old = await seed(
        deps,
        "regular",
        _regular("R26BK93000010", NOW - timedelta(hours=3)),
        _regular("R26BK93000011", NOW - timedelta(days=9)),
    )
    async with deps.db.transaction() as s:
        s.add(
            BidResultWatch(
                bid_id=done,
                stage="final",
                notice_ord="000",
                opening_at=NOW - timedelta(hours=3),
                next_check_at=NOW,
                final_kind="awarded",
                final_at=NOW - timedelta(hours=1),
            )
        )
    c = await member(full_api, "a@corp.example")
    r1 = (await c.put(f"/api/v1/bookmarks/b{done}", json={})).json()
    r2 = (await c.put(f"/api/v1/bookmarks/b{old}", json={})).json()
    await c.aclose()
    assert (r1["watching"], r1["opening_at"] is not None) == (False, True)
    assert (r2["watching"], r2["opening_at"] is not None) == (False, True)


async def test_put_bookmark_missing_opening(full_api):
    """개찰일이 없는 일반공고도 북마크는 되고 watching=false, opening_at=null(Review 3)."""
    it = regular_item("R26BK93000012", NOW - timedelta(days=1))
    it["opengDt"] = ""
    (bid_id,) = await seed(full_api.ctx.deps, "regular", it)
    c = await member(full_api, "a@corp.example")
    r = await c.put(f"/api/v1/bookmarks/b{bid_id}", json={})
    await c.aclose()
    assert r.status_code == 200
    assert (r.json()["watching"], r.json()["opening_at"]) == (False, None)
