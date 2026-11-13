"""공고 검색·상세 API 계약 (SPEC §6.3, §6.5-6·7, P1 결정 '수집 중'·'취소공고')."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import UsageLog
from app.search import service
from tests.conftest import NOW, build_api, make_auth_settings
from tests.fakes.downloader import docx_bytes
from tests.fakes.g2b import regular_item
from tests.helpers import make_profile, member, seed, sse

SEARCH = "/api/v1/bids/search"
CARD_KEYS = {
    "bid_id", "source", "bid_no", "title", "org_name", "budget", "deadline_at", "notice_at",
    "status", "cancelled", "revision", "detail_url", "has_files", "summary_ready", "bookmarked",
    "score", "reason",
}  # fmt: skip
Q = {"keywords": ["AI"], "days": 7, "source": "regular", "status": "all"}


def _items():
    return [
        regular_item("R26BK70000001", NOW - timedelta(days=1), title="AI 민원 분석 시스템"),
        regular_item(
            "R26BK70000002", NOW - timedelta(days=2), title="AI 학습데이터 구축", kind="취소공고"
        ),
        regular_item("R26BK70000003", NOW - timedelta(days=3), title="도로 포장 공사"),
    ]


async def test_search_returns_spec_shape_and_second_search_is_from_cache(full_api, fake_g2b):
    fake_g2b.add("regular", *_items())
    c = await member(full_api, "a@corp.example")
    first = (await c.post(SEARCH, json=Q)).json()
    second = (await c.post(SEARCH, json=Q)).json()
    await c.aclose()
    assert set(first) == {
        "run_id", "data_as_of", "incomplete", "collecting", "from_cache", "total",
        "truncated", "items",
    }  # fmt: skip
    assert first["from_cache"] is False and second["from_cache"] is True
    assert first["total"] == 2 and first["truncated"] is False
    item = first["items"][0]
    assert set(item) == CARD_KEYS
    assert item["bid_id"].startswith("b") and item["status"] == "open"
    assert item["deadline_at"].endswith("Z") or item["deadline_at"].endswith("+00:00")
    # 취소공고는 빼지 않고 표시만 (P1 사용자 결정)
    assert {i["bid_no"]: i["cancelled"] for i in first["items"]} == {
        "R26BK70000001": False,
        "R26BK70000002": True,
    }


async def test_cancelled_bids_stay_in_open_filter(full_api, fake_g2b):
    fake_g2b.add("regular", *_items())
    c = await member(full_api, "a@corp.example")
    body = (await c.post(SEARCH, json={**Q, "status": "open"})).json()
    await c.aclose()
    assert "R26BK70000002" in {i["bid_no"] for i in body["items"]}


@pytest.mark.parametrize(
    "bad",
    [
        {"limit": 101},
        {"limit": 0},
        {"keywords": [f"k{i}" for i in range(11)]},
        {"keywords": [""]},
        {"keywords": ["   "]},
        {"keywords": ["가" * 51]},
        {"sort": "bad"},
        {"match": "some"},
        {"days": 91},
        {"from": "2026-11-01"},
        {"from": "2026-11-05", "to": "2026-11-01"},
        {"top_n": 10},
    ],
)
async def test_search_validation_is_422(full_api, bad):
    """§6.5-6"""
    c = await member(full_api, "a@corp.example")
    r = await c.post(SEARCH, json=bad)
    await c.aclose()
    assert r.status_code == 422, bad
    assert r.json()["error"]["code"] == "validation_error"


async def test_snapshot_is_capped_and_paged(full_api, fake_g2b, monkeypatch):
    monkeypatch.setattr(service, "SNAPSHOT_MAX", 3)
    fake_g2b.add(
        "regular",
        *(
            regular_item(f"R26BK7100000{i}", NOW - timedelta(hours=i + 1), title="AI")
            for i in range(5)
        ),
    )
    c = await member(full_api, "a@corp.example")
    res = (await c.post(SEARCH, json={**Q, "limit": 2})).json()
    page = (await c.get(f"/api/v1/search-runs/{res['run_id']}", params={"offset": 2})).json()
    await c.aclose()
    assert (res["total"], res["truncated"], len(res["items"])) == (3, True, 2)
    assert len(page["items"]) == 1 and page["offset"] == 2


async def test_slow_fill_answers_collecting_then_logs_late_calls(db, clock, fake_llm, fake_g2b):
    from app.g2b.client import G2BClient
    from tests.conftest import TEST_KEYS

    fake_g2b.add("regular", *_items())
    fake_g2b.delay_s = 0.15
    http = fake_g2b.http_client()
    api = build_api(
        db,
        make_auth_settings(search_fill_wait_s=0.05),
        clock,
        llm=fake_llm,
        g2b=G2BClient(http, TEST_KEYS, page_size=100, retry_delays=(0, 0, 0)),
    )
    c = await member(api, "a@corp.example")
    first = (await c.post(SEARCH, json=Q)).json()
    assert first["collecting"] is True and first["incomplete"] is True
    for _ in range(60):  # 백그라운드 수집이 끝날 때까지
        await asyncio.sleep(0.1)
        async with db.session() as s:
            late = (
                (await s.execute(select(UsageLog).where(UsageLog.event == "collector")))
                .scalars()
                .all()
            )
        if late:
            break
    second = (await c.post(SEARCH, json=Q)).json()
    await c.aclose()
    await http.aclose()
    assert late and late[0].g2b_calls > 0  # 응답 뒤의 G2B 호출도 기록된다
    assert second["from_cache"] is True and second["collecting"] is False
    assert second["total"] == 2


RFP_URL = "https://www.g2b.go.kr/files/rfp-api.docx"


async def test_detail_lookup_and_file_text(full_api, fake_downloader):
    fake_downloader.files[RFP_URL] = (docx_bytes("과업 범위: AI 검색"), "제안요청서.docx")
    item = regular_item("R26BK72000001", NOW, files=[(RFP_URL, "제안요청서.docx")])
    (bid_id,) = await seed(full_api.ctx.deps, "regular", item)
    c = await member(full_api, "a@corp.example")
    before = (await c.get(f"/api/v1/bids/b{bid_id}")).json()
    assert before["summary"] is None and before["my_analysis_id"] is None
    assert [(f["name"], f["status"]) for f in before["files"]] == [("제안요청서.docx", "new")]
    assert "url" not in before["files"][0]  # 첨부 URL은 노출하지 않는다

    pid = await make_profile(c)
    events = await sse(c, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid})
    after = (await c.get(f"/api/v1/bids/b{bid_id}")).json()
    assert after["summary"]["headline"] and after["summary_ready"] is True
    assert after["my_analysis_id"] == events[-2]["analysis_id"]

    fid = after["files"][0]["file_id"]
    text = (await c.get(f"/api/v1/bids/b{bid_id}/files/{fid}/text", params={"max_chars": 5})).json()
    assert text["text"] == "과업 범위" and text["truncated"] is True

    found = await c.get("/api/v1/bids/lookup", params={"bid_no": "R26BK72000001"})
    missing = await c.get("/api/v1/bids/lookup", params={"bid_no": "R00000000000"})
    statuses = [
        (await c.get(path)).status_code
        for path in (
            "/api/v1/bids/bxyz",
            "/api/v1/bids/b999999",
            f"/api/v1/bids/b{bid_id}/files/999/text",
        )
    ]
    await c.aclose()
    assert found.json() == {"bid_id": f"b{bid_id}"}
    assert missing.status_code == 404 and statuses == [404, 404, 404]


async def test_search_rate_limited_with_retry_after(db, clock, fake_llm):
    """§6.5-7"""
    api = build_api(db, make_auth_settings(rate_limit_enabled=True), clock, llm=fake_llm)
    from tests.helpers import create_user, login

    await create_user(db, "rl@corp.example")
    c = api.client()
    assert (await login(c, "rl@corp.example")).status_code == 200
    codes = [(await c.post(SEARCH, json={"days": 1})).status_code for _ in range(31)]
    last = await c.post(SEARCH, json={"days": 1})
    await c.aclose()
    assert codes[:30] == [200] * 30 and codes[30] == 429
    assert int(last.headers["retry-after"]) >= 1


async def test_detail_links_related_prespec_both_ways(full_api):
    """§7.5 헤더: 사전규격 등록번호로 이어지는 공고 링크."""
    from tests.fakes.g2b import prespec_item

    reg = regular_item("R26BK73000001", NOW - timedelta(hours=2))
    reg["bfSpecRgstNo"] = "R26BD00000077"
    (rid,) = await seed(full_api.ctx.deps, "regular", reg)
    changed = regular_item("R26BK73000001", NOW, ord="001", title="[정정] AI", kind="변경공고")
    changed["bfSpecRgstNo"] = "R26BD00000077"
    await seed(full_api.ctx.deps, "regular", changed)  # 정정공고 → revision 2
    (pid,) = await seed(full_api.ctx.deps, "prespec", prespec_item("R26BD00000077", NOW))
    c = await member(full_api, "a@corp.example")
    r = (await c.get(f"/api/v1/bids/b{rid}")).json()
    p = (await c.get(f"/api/v1/bids/b{pid}")).json()
    await c.aclose()
    assert r["related_bid_id"] == f"b{pid}" and p["related_bid_id"] == f"b{rid}"
    assert r["revision"] == 2 and r["prespec_reg_no"] == "R26BD00000077"


async def test_detail_shows_g2b_facts_without_ai(full_api, fake_llm):
    """docs/decisions/2026-11-13-official-facts.md: 마감·예산·계약 방법은 G2B 값 그대로."""
    item = regular_item("R26BK72000009", NOW, deadline="2026-11-24 10:00:00", budget="90000000")
    item.update(asignBdgtAmt="99000000", sucsfbidMthdNm="협상에의한계약-협상에 의한 낙찰자 결정")
    (bid_id,) = await seed(full_api.ctx.deps, "regular", item)
    c = await member(full_api, "facts@corp.example")
    body = (await c.get(f"/api/v1/bids/b{bid_id}")).json()
    await c.aclose()
    assert body["official"]["deadline_label"] == "입찰 마감"
    assert body["official"]["deadline_at"].startswith("2026-11-24T01:00:00")
    assert body["official"]["assigned_budget"] == 99_000_000
    assert body["official"]["estimated_price"] == 90_000_000
    assert body["official"]["award_method"] == "협상에 의한 낙찰자 결정"
    assert body["summary"] is None and sum(fake_llm.calls.values()) == 0  # 요약 없이도 보인다


async def test_detail_lists_doc_budget_that_differs_from_g2b(full_api, fake_llm):
    """원문 사업금액이 G2B 배정예산과 다르면 둘 다 보여 준다."""
    from app.pipeline.summarize import get_or_create_summary

    deps = full_api.ctx.deps
    url = "https://www.g2b.go.kr/files/budget.docx"
    deps.downloader.files[url] = (
        docx_bytes("다. 사업금액: 665,000,000원 (부가세포함)"),
        "제안요청서.docx",
    )
    item = regular_item("R26BK72000010", NOW, files=[(url, "제안요청서.docx")])
    item.update(asignBdgtAmt="670900400")
    (bid_id,) = await seed(deps, "regular", item)
    await get_or_create_summary(deps, bid_id)  # 첨부를 받아 글자를 뽑아 둔다
    c = await member(full_api, "docbudget@corp.example")
    body = (await c.get(f"/api/v1/bids/b{bid_id}")).json()
    await c.aclose()
    assert body["official"]["assigned_budget"] == 670_900_400
    assert body["doc_budgets"] == [
        {"file": "제안요청서.docx", "label": "사업금액", "amount": 665_000_000}
    ]
