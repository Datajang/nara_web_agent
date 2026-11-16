"""P10 API: 비교·강점/약점, 경쟁사 레이더, 관심 경쟁사 (SPEC §15.5·§15.6·§15.11 P10)."""

from datetime import UTC, datetime, timedelta

from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.db.models import BidParticipant, CollectorCoverage
from tests.conftest import NOW
from tests.fakes.g2b import award_item
from tests.helpers import admin_client, member

US = "1234567890"
THEM = "2345678901"
OTHER = "3456789012"
LONE = "4567890123"


def _aw(no, days_ago, bizno, name, org="1111111", title="데이터 정비 사업", amount="100000000"):
    return award_item(
        no,
        NOW - timedelta(days=days_ago),
        bizno=bizno,
        name=name,
        org_cd=org,
        org_name=f"기관{org}",
        title=title,
        amount=amount,
    )


AWARDS = [
    # 우리: 3건, 기관 1111111×2·2222222, 분야 데이터 정비×2·AI
    _aw("R26BK00000001", 5, US, "우리"),
    _aw("R26BK00000002", 40, US, "우리", amount="200000000"),
    _aw("R26BK00000003", 80, US, "우리", org="2222222", title="AI 분석"),
    # 가온: 5건, 같은 기관 1111111, 데이터 정비
    *(_aw(f"R26BK0000010{i}", 10 + i, THEM, "가온", amount="300000000") for i in range(5)),
    # 나래: 2건, 다른 기관, AI
    _aw("R26BK00000201", 7, OTHER, "나래", org="9999999", title="AI 플랫폼"),
    _aw("R26BK00000202", 9, OTHER, "나래", org="9999999", title="AI 분석"),
    # 혼자: 1건(후보 제외)
    _aw("R26BK00000301", 3, LONE, "혼자"),
]


KEYWORDS = {"데이터 정비": ["데이터 정비"], "AI": ["AI"]}


async def _setup(api):
    async with api.db.transaction() as s:
        s.add(
            CollectorCoverage(
                source="awards",
                covered_from=datetime(2021, 1, 1, tzinfo=UTC),
                covered_to=NOW,
            )
        )
        await upsert_awards(s, [to_award(it) for it in AWARDS], KEYWORDS)
    a = await admin_client(api)
    r = await a.put("/api/v1/admin/company", json={"our_bizno": US, "field_keywords": KEYWORDS})
    assert r.status_code == 200, r.text
    return a


async def _list_all(c, bizno):
    items, cursor = [], None
    while True:
        q = f"/api/v1/awards?bizno={bizno}&limit=3" + (f"&cursor={cursor}" if cursor else "")
        page = (await c.get(q)).json()
        items += page["items"]
        if not (cursor := page["next_cursor"]):
            return items


async def test_compare_numbers_match_award_lists_and_rules(full_api):
    a = await _setup(full_api)
    r1 = (await a.get(f"/api/v1/compare/{THEM}")).json()
    r2 = (await a.get(f"/api/v1/compare/{THEM}")).json()
    us_items, them_items = await _list_all(a, US), await _list_all(a, THEM)
    await a.aclose()
    assert r1 == r2  # 같은 입력 → 같은 판정 (수용 기준)
    v = {x["key"]: x for x in r1["verdicts"]}
    # 판정 표의 숫자 = GET /awards 직접 합산 (수용 기준 3)
    for key, items in (("us", us_items), ("them", them_items)):
        assert v["count"][key] == len(items)
        assert v["amount_sum"][key] == sum(i["award_amount"] for i in items)
        assert v["org_count"][key] == len({i["dminstt_cd"] for i in items})
    assert (v["count"]["us"], v["count"]["them"], v["count"]["verdict"]) == (3, 5, "down")
    assert v["org_count"]["verdict"] == "up"  # 2 vs 1
    assert v["field:AI"]["verdict"] == "info" and v["field:AI"]["small_sample"]  # 1 vs 0
    assert v["field:데이터 정비"]["verdict"] == "down"  # 2 vs 5 → 2.5배
    assert v["head_to_head"]["verdict"] == "info"  # 개찰 결과 없음
    assert r1["strengths"] == ["org_count"]
    assert r1["weaknesses"][0] == "amount_sum"
    assert r1["note"] == "두 회사 모두 수집 완료된 기간"
    assert r1["us"] == {"bizno": US, "name": "우리"} and r1["them"]["name"] == "가온"
    assert r1["shared_orgs"] == [
        {"dminstt_cd": "1111111", "dminstt_name": "기관1111111", "us": 2, "them": 5}
    ]
    assert sum(y["us"] or 0 for y in r1["by_year"]) == 3
    # 2021-01부터 수집돼 5년 목표(2021-11~)를 다 덮는다
    assert r1["coverage"]["collecting"] is False and r1["coverage"]["complete_from"]


async def test_head_to_head_counts_only_notices_both_entered(full_api):
    a = await _setup(full_api)
    async with full_api.db.transaction() as s:
        for no, biznos in (
            ("R26BK00000001", (US, THEM)),  # 우리 낙찰
            ("R26BK00000100", (US, THEM)),  # 가온 낙찰
            ("R26BK00000101", (US, THEM)),  # 가온 낙찰
            ("R26BK00000102", (THEM,)),  # 우리는 안 들어감 → 안 셈
        ):
            for b in biznos:
                s.add(
                    BidParticipant(
                        bid_ntce_no=no, bid_ntce_ord="000", bid_clsfc_no="0", rbid_no="000", bizno=b
                    )
                )
    r = (await a.get(f"/api/v1/compare/{THEM}")).json()
    await a.aclose()
    assert r["head_to_head"] == {"matched": 3, "us_wins": 1, "them_wins": 2}
    h = next(x for x in r["verdicts"] if x["key"] == "head_to_head")
    assert (h["verdict"], h["small_sample"]) == ("down", True)


async def test_compare_errors(full_api):
    m = await member(full_api, "m@corp.example")
    assert (await m.get(f"/api/v1/compare/{THEM}")).json()["error"]["code"] == "not_configured"
    await m.aclose()
    a = await _setup(full_api)
    assert (await a.get(f"/api/v1/compare/{US}")).status_code == 400
    assert (await a.get("/api/v1/compare/9999999999")).status_code == 404
    assert (await a.get("/api/v1/compare/123")).status_code == 422
    await a.aclose()


async def test_candidates_by_overlap(full_api):
    a = await _setup(full_api)
    r = (await a.get("/api/v1/competitors/candidates")).json()
    ai = (await a.get("/api/v1/competitors/candidates?field=AI")).json()
    by_org = (await a.get("/api/v1/competitors/candidates?org=9999999")).json()
    await a.aclose()
    got = [(c["bizno"], c["overlap"], c["org_overlap"], c["field_overlap"]) for c in r["items"]]
    # 가온: 우리 3건 중 기관 겹침 2(1111111), 분야 겹침 2(데이터 정비) → 100×(0.6×2/3 + 0.4×2/3)
    # 나래: 기관 0, 분야 AI 1/3 → 100×0.4/3. 혼자(1건)·우리는 제외
    assert got == [(THEM, 66.7, 0.6667, 0.6667), (OTHER, 13.3, 0.0, 0.3333)]
    assert r["our_count"] == 3 and r["us"]["bizno"] == US
    assert [c["bizno"] for c in ai["items"]] == [OTHER]  # AI 낙찰만: 우리 1, 나래 2
    assert by_org["items"] == []  # 우리가 그 기관 낙찰이 없음


async def test_watch_list(full_api):
    a = await _setup(full_api)
    m = await member(full_api, "m@corp.example")
    put = await m.put(f"/api/v1/competitors/watch/{THEM}")
    again = await a.put(f"/api/v1/competitors/watch/{THEM}")  # 서비스 전체 공유, 멱등
    missing = await m.put("/api/v1/competitors/watch/9999999999")
    listed = (await a.get("/api/v1/competitors/watch")).json()["items"]
    cand = (await a.get("/api/v1/competitors/candidates")).json()["items"]
    cmp_watched = (await a.get(f"/api/v1/compare/{THEM}")).json()["watched"]
    deleted = await m.delete(f"/api/v1/competitors/watch/{THEM}")
    after = (await a.get("/api/v1/competitors/watch")).json()["items"]
    await a.aclose()
    await m.aclose()
    assert put.status_code == again.status_code == 200 and missing.status_code == 404
    assert [(w["bizno"], w["name"], w["award_count"]) for w in listed] == [(THEM, "가온", 5)]
    assert cand[0]["watched"] is True and cmp_watched is True
    assert deleted.status_code == 204 and after == []


async def test_changing_our_company_recomputes(full_api):
    a = await _setup(full_api)
    before = (await a.get(f"/api/v1/compare/{OTHER}")).json()
    cand_before = [
        c["bizno"] for c in (await a.get("/api/v1/competitors/candidates")).json()["items"]
    ]
    await a.put(
        "/api/v1/admin/company",
        json={"our_bizno": THEM, "field_keywords": KEYWORDS},
    )
    after = (await a.get(f"/api/v1/compare/{OTHER}")).json()
    cand_after = [
        c["bizno"] for c in (await a.get("/api/v1/competitors/candidates")).json()["items"]
    ]
    await a.aclose()
    assert before["us"]["bizno"] == US and after["us"]["bizno"] == THEM
    cnt = lambda r: next(v["us"] for v in r["verdicts"] if v["key"] == "count")  # noqa: E731
    assert (cnt(before), cnt(after)) == (3, 5)
    assert THEM in cand_before and US in cand_after and THEM not in cand_after
