"""P9 API: 회사 설정·우리 수주 현황·업체 검색 (SPEC §15.6·§15.7·§15.11 P9). DB만, G2B 호출 없음."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.api.routers import awards as awards_router
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.db.models import BidAward, BidJointMember, CollectorCoverage, UsageLog
from tests.conftest import NOW
from tests.fakes.g2b import award_item, regular_item
from tests.helpers import admin_client, member, seed

US = "1234567890"
THEM = "2345678901"
OTHER = "3456789012"
COVERED_FROM = datetime(2024, 3, 31, 15, 0, tzinfo=UTC)  # 2024-04-01 00:00 KST


async def _seed_awards(api, *items, cover_from=COVERED_FROM):
    async with api.db.transaction() as s:
        await upsert_awards(s, [to_award(it) for it in items], {})
        s.add(CollectorCoverage(source="awards", covered_from=cover_from, covered_to=NOW))


def _aw(no, days_ago, bizno=US, name="(주)예시컴퍼니", **kw):
    return award_item(no, NOW - timedelta(days=days_ago), bizno=bizno, name=name, **kw)


def _member(no, *, lead, member, share):
    return BidJointMember(
        bid_ntce_no=no,
        bid_ntce_ord="",
        bizno=lead,
        member_bizno=member,
        role="주계약업체" if lead == member else "도급업체",
        joint_mode="공동",
        share=Decimal(share),
    )


async def _configure(c, bizno=US, **kw):
    r = await c.put("/api/v1/admin/company", json={"our_bizno": bizno, **kw})
    assert r.status_code == 200, r.text
    return r.json()


async def test_permissions(full_api):
    m = await member(full_api, "m@corp.example")
    assert (await m.get("/api/v1/company")).status_code == 200
    assert (await m.put("/api/v1/admin/company", json={})).status_code == 403
    r = await m.post("/api/v1/admin/company/lookup", json={"bizno": US})
    assert r.status_code == 403
    await m.aclose()
    anon = full_api.client()
    assert (await anon.get("/api/v1/awards")).status_code == 401
    await anon.aclose()


async def test_lookup_fills_name_from_collected_awards(full_api):
    await _seed_awards(full_api, _aw("R26BK00000001", 3, name="(주)예시컴퍼니"))
    a = await admin_client(full_api)
    r = (await a.post("/api/v1/admin/company/lookup", json={"bizno": "123-45-67890"})).json()
    assert r == {"found": True, "bizno": US, "name": "(주)예시컴퍼니", "award_count": 1}
    r = (await a.post("/api/v1/admin/company/lookup", json={"bizno": "9999999999"})).json()
    assert r["found"] is False and r["name"] is None
    bad = await a.post("/api/v1/admin/company/lookup", json={"bizno": "12345"})
    assert bad.status_code == 422
    # 이름을 비우면 찾은 이름으로 저장, 없는 번호면 이름을 직접 받아야 한다
    saved = await _configure(a)
    assert saved["configured"] and saved["our_name"] == "(주)예시컴퍼니"
    r = await a.put("/api/v1/admin/company", json={"our_bizno": "9999999999"})
    assert r.status_code == 422 and r.json()["error"]["details"][0]["field"] == "our_name"
    saved = await _configure(a, "9999999999", our_name="새회사")
    assert saved["our_name"] == "새회사" and saved["our_bizno"] == "9999999999"
    await a.aclose()


async def test_company_status_reports_progress_and_budget(full_api):
    await _seed_awards(full_api, _aw("R26BK00000001", 3, bizno=None))
    async with full_api.db.transaction() as s:
        s.add(UsageLog(event="collector", g2b_calls=12, cache={"source": "awards"}))
        s.add(UsageLog(event="collector", g2b_calls=50, cache={"source": "regular"}))
        s.add(UsageLog(event="collector", g2b_calls=7, cache={"source": "openings"}))
    a = await admin_client(full_api)
    r = (await a.get("/api/v1/company")).json()
    await a.aclose()
    assert r["configured"] is False and r["backfill_years"] == 5
    assert r["coverage"]["collecting"] is True  # 5년 목표 중 2024-04부터만
    years = {y["year"]: y["ratio"] for y in r["years"]}
    assert years[2022] == 0 and years[2025] == 1 and 0 < years[2024] < 1
    assert r["calls_today"] == 12 and r["calls_budget"] == 300
    # 개찰 결과(P12)는 낙찰 몫과 따로 센다
    assert r["openings_calls_today"] == 7 and r["openings_calls_budget"] == 300
    assert r["unidentified_count"] == 1


async def test_summary_not_configured(full_api):
    m = await member(full_api, "m@corp.example")
    r = await m.get("/api/v1/awards/summary")
    await m.aclose()
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_configured"


async def test_summary_matches_list_and_never_shows_zero_for_uncollected(full_api):
    await seed(
        full_api.ctx.deps, "regular", regular_item("R26BK00000001", NOW - timedelta(days=40))
    )
    await _seed_awards(
        full_api,
        _aw("R26BK00000001", 10, amount="80000000", org_cd="1111111", org_name="행정안전부"),
        _aw("R26BK00000002", 200, amount="50000000", org_cd="1111111", org_name="행정안전부"),
        _aw("R26BK00000003", 500, amount="30000000", org_cd="2222222", org_name="조달청"),
        _aw("R26BK00000004", 20, bizno=THEM, name="가온데이터(주)", amount="99000000"),
    )
    a = await admin_client(full_api)
    await _configure(a)
    sm = (await a.get("/api/v1/awards/summary")).json()
    items, cursor = [], None
    while True:
        q = "/api/v1/awards?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await a.get(q)).json()
        items += page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            break
    await a.aclose()
    assert sm["is_us"] and sm["name"] == "(주)예시컴퍼니"
    assert sm["count"] == len(items) == page["total"] == 3
    assert sm["amount_sum"] == sum(i["award_amount"] for i in items) == 160_000_000
    assert sm["amount_avg"] == 53_333_333 and sm["org_count"] == 2
    assert sm["by_org"][0] == {
        "dminstt_cd": "1111111",
        "dminstt_name": "행정안전부",
        "count": 2,
        "amount_sum": 130_000_000,
    }
    # 기본 기간은 5년 전부터, 수집은 2024-04부터 → 앞쪽 해는 0이 아니라 '수집 중'
    p = sm["period"]
    assert p["collecting"] is True and p["counted_from"] == "2024-04-01"
    by_year = {y["year"]: y for y in sm["by_year"]}
    assert by_year[2022] == {"year": 2022, "count": None, "amount_sum": None, "collecting": True}
    assert by_year[2025]["collecting"] is False and by_year[2025]["count"] == 1
    assert sum((y["count"] or 0) for y in sm["by_year"]) == 3
    # 추정가격은 공고 DB에 있는 공고만, G2B 낙찰률은 따로
    first = next(i for i in items if i["bid_ntce_no"] == "R26BK00000001")
    assert first["estimated_price"] == 100_000_000 and first["award_ratio"] == 0.8
    assert first["g2b_award_rate"] == 87.5 and first["bid_id"] and first["bid_id"].startswith("b")
    other = next(i for i in items if i["bid_ntce_no"] == "R26BK00000002")
    assert other["estimated_price"] is None and other["award_ratio"] is None
    assert other["bid_id"] is None


async def test_period_inside_coverage_is_complete(full_api):
    await _seed_awards(full_api, _aw("R26BK00000001", 10))
    a = await admin_client(full_api)
    await _configure(a)
    r = (await a.get("/api/v1/awards/summary?from=2025-01-01&to=2025-12-31")).json()
    await a.aclose()
    assert r["period"]["collecting"] is False and r["count"] == 0
    assert r["by_year"] == [{"year": 2025, "count": 0, "amount_sum": 0, "collecting": False}]


async def test_list_filters_by_field_and_org(full_api):
    await _seed_awards(
        full_api,
        _aw("R26BK00000001", 3, title="데이터 정비 사업", org_cd="1111111"),
        _aw("R26BK00000002", 4, title="청사 청소", org_cd="2222222"),
    )
    a = await admin_client(full_api)
    await _configure(a, field_keywords={"데이터 정비": ["데이터 정비"]})
    await asyncio.gather(*awards_router._jobs)  # 사전이 바뀌어 재분류가 돈다
    by_field = (await a.get("/api/v1/awards?field=데이터 정비")).json()
    by_org = (await a.get("/api/v1/awards?org=2222222")).json()
    sm = (await a.get("/api/v1/awards/summary")).json()
    bad = await a.get("/api/v1/awards?cursor=@@@")
    await a.aclose()
    assert [i["title"] for i in by_field["items"]] == ["데이터 정비 사업"]
    assert [i["title"] for i in by_org["items"]] == ["청사 청소"]
    assert sm["by_field"] == [{"field": "데이터 정비", "count": 1}]
    assert sm["fields"] == ["데이터 정비"]
    assert bad.status_code == 400


async def test_list_filters_by_title_and_period(full_api):
    """우리 수주 현황 낙찰 목록 필터(2026-11-24).

    사업명은 띄어쓰기를 무시하고, 기간은 등록일(KST) 기준으로 끝 날을 포함한다."""
    await _seed_awards(
        full_api,
        _aw("R26BK00000001", 3, title="데이터 정비 사업"),  # 11-07
        _aw("R26BK00000002", 4, title="청사 청소 용역"),  # 11-06
        _aw("R26BK00000003", 40, title="데이터정비 고도화"),  # 10-01
    )
    a = await admin_client(full_api)
    await _configure(a)
    by_q = (await a.get("/api/v1/awards?q=데이터 정비")).json()
    by_period = (await a.get("/api/v1/awards?from=2026-11-06&to=2026-11-07")).json()
    both = (await a.get("/api/v1/awards?q=청소&from=2026-11-01&to=2026-11-10")).json()
    literal = (await a.get("/api/v1/awards?q=%25")).json()  # % 는 글자 그대로
    too_long = await a.get("/api/v1/awards?q=" + "가" * 101)
    await a.aclose()
    assert [i["title"] for i in by_q["items"]] == ["데이터 정비 사업", "데이터정비 고도화"]
    assert by_q["total"] == 2
    assert [i["title"] for i in by_period["items"]] == ["데이터 정비 사업", "청사 청소 용역"]
    assert [i["title"] for i in both["items"]] == ["청사 청소 용역"] and both["total"] == 1
    assert literal["items"] == [] and literal["total"] == 0
    assert too_long.status_code == 422


async def test_our_view_counts_joint_member_wins_by_share(full_api):
    """우리가 구성원(대표는 타사)인 공동수급 낙찰(2026-11-24).

    우리 수주 현황 건수에 넣고 금액은 지분만큼.

    다른 업체 화면은 그대로. 같은 공고의 다른 분류(대표가 다른 업체)에는 잇지 않는다."""
    await _seed_awards(
        full_api,
        _aw("R26BK00000011", 3, title="우리 대표 공동", amount="100000000"),
        _aw(
            "R26BK00000012",
            4,
            bizno=THEM,
            name="(주)타사",
            title="타사 대표 공동",
            amount="200000000",
        ),
        _aw(
            "R26BK00000012",
            4,
            bizno=OTHER,
            name="(주)딴곳",
            clsfc="1",
            title="딴곳 분류",
            amount="300000000",
        ),
    )
    async with full_api.db.transaction() as s:
        s.add_all(
            [
                _member("R26BK00000011", lead=US, member=US, share="70"),
                _member("R26BK00000011", lead=US, member=THEM, share="30"),
                _member("R26BK00000012", lead=THEM, member=THEM, share="75"),
                _member("R26BK00000012", lead=THEM, member=US, share="25"),
            ]
        )
    a = await admin_client(full_api)
    await _configure(a)
    ours = (await a.get("/api/v1/awards/summary")).json()
    lst = (await a.get("/api/v1/awards")).json()
    them = (await a.get(f"/api/v1/companies/{THEM}")).json()
    them_list = (await a.get(f"/api/v1/awards?bizno={THEM}")).json()
    await a.aclose()

    assert (ours["count"], ours["member_count"]) == (2, 1)
    assert ours["amount_sum"] == 100_000_000 + 50_000_000  # 대표 낙찰은 전액, 구성원은 25%
    assert sum(y["count"] or 0 for y in ours["by_year"]) == 2
    by = {i["title"]: i for i in lst["items"]}
    assert set(by) == {"우리 대표 공동", "타사 대표 공동"} and lst["total"] == 2
    assert (by["우리 대표 공동"]["our_role"], by["우리 대표 공동"]["our_share"]) == ("lead", 70.0)
    assert (by["타사 대표 공동"]["our_role"], by["타사 대표 공동"]["our_share"]) == ("member", 25.0)
    assert by["타사 대표 공동"]["winner_name"] == "(주)타사"
    # 다른 업체 화면은 자기 대표 낙찰만, 전액
    assert (them["count"], them["amount_sum"], them["member_count"]) == (1, 200_000_000, 0)
    assert [i["our_role"] for i in them_list["items"]] == [None]


async def test_put_starts_reclassify_only_when_keywords_change(full_api):
    await _seed_awards(full_api, _aw("R26BK00000001", 3, title="AI 분석 플랫폼"))
    a = await admin_client(full_api)
    r1 = await _configure(a, field_keywords={"AI": ["AI"]})
    await asyncio.gather(*awards_router._jobs)
    r2 = await _configure(a, field_keywords={"AI": ["AI"]}, backfill_years=7)
    await a.aclose()
    assert r1["reclassify_started"] is True and r2["reclassify_started"] is False
    assert r2["backfill_years"] == 7
    async with full_api.db.session() as s:
        assert await s.scalar(select(BidAward.fields)) == ["AI"]


async def test_company_search_by_name_or_bizno_and_logged(full_api):
    await _seed_awards(
        full_api,
        _aw("R26BK00000001", 3),
        _aw("R26BK00000002", 4, bizno=THEM, name="가온데이터시스템(주)"),
        _aw("R26BK00000003", 5, bizno=THEM, name="가온데이터시스템(주)"),
        _aw("R26BK00000004", 6, bizno="3456789012", name="주식회사 가온"),
    )
    a = await admin_client(full_api)
    await _configure(a)
    by_name = (await a.get("/api/v1/companies/search?q=가온 데이터")).json()["items"]
    broad = (await a.get("/api/v1/companies/search?q=(주)가온")).json()["items"]
    by_no = (await a.get("/api/v1/companies/search?q=123-45-67890")).json()["items"]
    short = await a.get("/api/v1/companies/search?q=가")
    pct = (await a.get("/api/v1/companies/search?q=%25%25")).status_code
    await a.aclose()
    assert [(h["bizno"], h["award_count"]) for h in by_name] == [(THEM, 2)]
    assert [h["bizno"] for h in broad] == [THEM, "3456789012"]  # 낙찰 많은 순
    assert by_no[0]["bizno"] == US and by_no[0]["is_us"] is True
    assert short.status_code == 422 and pct == 422
    async with full_api.db.session() as s:
        logs = (
            (await s.execute(select(UsageLog.cache).where(UsageLog.event == "company_search")))
            .scalars()
            .all()
        )
    assert len(logs) == 3 and {"by": "bizno", "results": 1} in logs
    assert all("q" not in c for c in logs)  # 검색어는 남기지 않는다


async def test_company_detail(full_api):
    await _seed_awards(full_api, _aw("R26BK00000002", 4, bizno=THEM, name="가온데이터시스템(주)"))
    m = await member(full_api, "m@corp.example")
    r = (await m.get(f"/api/v1/companies/{THEM}")).json()
    other = (await m.get(f"/api/v1/awards?bizno={THEM}")).json()
    missing = await m.get("/api/v1/companies/9999999999")
    bad = await m.get("/api/v1/companies/123")
    await m.aclose()
    assert r["name"] == "가온데이터시스템(주)" and r["is_us"] is False and r["count"] == 1
    assert other["total"] == 1 and other["items"][0]["winner_name"] == "가온데이터시스템(주)"
    assert missing.status_code == 404 and bad.status_code == 422


async def test_changing_our_company_changes_results(full_api):
    await _seed_awards(
        full_api,
        _aw("R26BK00000001", 3),
        _aw("R26BK00000002", 4, bizno=THEM, name="가온"),
        _aw("R26BK00000003", 5, bizno=THEM, name="가온"),
    )
    a = await admin_client(full_api)
    await _configure(a)
    before = (await a.get("/api/v1/awards/summary")).json()
    await _configure(a, THEM)
    after = (await a.get("/api/v1/awards/summary")).json()
    await a.aclose()
    assert (before["bizno"], before["count"]) == (US, 1)
    assert (after["bizno"], after["count"], after["name"]) == (THEM, 2, "가온")
