"""우리 투찰 결과 API (P12): GET /my-bids, GET /my-bids/{no}/{ord}/{clsfc}/{rbid}.

- 목록 = 우리 낙찰 + 개찰 결과에 우리가 있는 공고. 결과 won / lost(순위) / disqualified(사유)
- 순위를 추정하지 않는다: 순위가 비면 비고(낙찰하한선 미달 등)를 그대로 준다
- 상세: 참가업체 전체(순위·투찰·점수·비고·업체별 낙찰 수). 개찰 결과가 없으면 그 공고만 1회 부른다
"""

from datetime import timedelta
from decimal import Decimal

from app.awards import openings
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.db.models import BidJointMember
from tests.conftest import NOW
from tests.fakes.g2b import award_item, opening_item
from tests.helpers import admin_client

US, THEM, OTHER = "1234567890", "2345678901", "3456789012"
WON, LOST, DQ, NOT_US, WON_LATER = (f"R26BK0000005{i}" for i in range(5))


def _aw(no, days, winner, name="가온"):
    return award_item(no, NOW - timedelta(days=days), bizno=winner, name=name, title=f"{no} 용역")


AWARDS = [
    _aw(WON, 1, US, "우리"),
    _aw(LOST, 2, THEM),
    _aw(DQ, 3, THEM),
    _aw(NOT_US, 4, OTHER),
    _aw(WON_LATER, 5, US, "우리"),  # 개찰 결과를 아직 안 받은 우리 낙찰
]


def _openings(fake_g2b):
    fake_g2b.add(
        "opening_compt",
        opening_item(WON, US, rank="1", total="91.5"),
        opening_item(WON, THEM, rank="2", total="85.0"),
        opening_item(LOST, THEM, rank="1", amount="80000000", rate="88.1"),
        opening_item(LOST, OTHER, rank="2"),
        opening_item(LOST, US, rank="3", amount="85000000", rate="89.9", total="70.5"),
        opening_item(DQ, THEM, rank="1"),
        opening_item(DQ, US, rank="", amount="70000000", rate="80.0", remark="낙찰하한선 미달"),
        opening_item(NOT_US, OTHER, rank="1"),
        opening_item(WON_LATER, US, rank="1"),
        opening_item(WON_LATER, THEM, rank="", remark="협상평가부적격자"),
    )


async def _setup(api, fake_g2b):
    async with api.db.transaction() as s:
        await upsert_awards(s, [to_award(it) for it in AWARDS[:-1]], {})
    _openings(fake_g2b)
    a = await admin_client(api)
    r = await a.put("/api/v1/admin/company", json={"our_bizno": US, "field_keywords": {}})
    assert r.status_code == 200, r.text
    await openings.run(api.ctx.deps, "incremental")  # 자동 수집이 4공고를 받은 뒤
    async with api.db.transaction() as s:  # 우리 낙찰이 새로 들어옴(개찰 결과는 아직)
        await upsert_awards(s, [to_award(AWARDS[-1])], {})
    return a


def _calls(fake_g2b):
    return [r.url.params["bidNtceNo"] for r in fake_g2b.requests if "OpengCompt" in r.url.path]


async def test_list_shows_wins_and_losses_with_rank_or_reason(full_api, fake_g2b):
    a = await _setup(full_api, fake_g2b)
    body = (await a.get("/api/v1/my-bids")).json()
    lost = (await a.get("/api/v1/my-bids?result=lost")).json()
    won = (await a.get("/api/v1/my-bids?result=won")).json()
    p1 = (await a.get("/api/v1/my-bids?limit=2")).json()
    p2 = (await a.get(f"/api/v1/my-bids?limit=2&cursor={p1['next_cursor']}")).json()
    bad = await a.get("/api/v1/my-bids?cursor=nope")
    await a.aclose()

    assert body["counts"] == {"all": 4, "won": 2, "lost": 2}
    by = {i["bid_ntce_no"]: i for i in body["items"]}
    assert [i["bid_ntce_no"] for i in body["items"]] == [WON, LOST, DQ, WON_LATER]  # 최신부터
    assert NOT_US not in by
    assert by[WON]["result"] == "won" and by[WON]["our_rank"] == 1 and by[WON]["valid_count"] == 2
    assert by[LOST]["result"] == "lost"
    assert (by[LOST]["our_rank"], by[LOST]["valid_count"], by[LOST]["our_bid_amount"]) == (
        3,
        3,
        85000000,
    )
    assert by[LOST]["winner_bizno"] == THEM and by[LOST]["our_total_score"] == 70.5
    # 순위가 비면 부적격: 순위를 만들지 않고 사유를 준다
    assert by[DQ]["result"] == "disqualified" and by[DQ]["our_rank"] is None
    assert by[DQ]["remark"] == "낙찰하한선 미달" and by[DQ]["valid_count"] == 1
    # 개찰 결과를 아직 안 받은 우리 낙찰: 낙찰은 보이고 순위는 모름
    assert by[WON_LATER]["result"] == "won" and by[WON_LATER]["fetched"] is False
    assert by[WON_LATER]["valid_count"] is None
    assert [i["bid_ntce_no"] for i in lost["items"]] == [LOST, DQ]
    assert [i["bid_ntce_no"] for i in won["items"]] == [WON, WON_LATER]
    assert [i["bid_ntce_no"] for i in p1["items"] + p2["items"]] == [WON, LOST, DQ, WON_LATER]
    assert p2["next_cursor"] is None and bad.status_code == 400
    scan = body["scan"]
    assert scan["fetched_notices"] == 4 and scan["award_notices"] == 5 and scan["since"]


async def test_list_filters_by_period_and_title(full_api, fake_g2b):
    """투찰 결과 필터(2026-11-24): 기간(등록일 KST, 끝 날 포함)·사업명(띄어쓰기 무시).

    결과별 건수도 같은 조건으로 센다."""
    a = await _setup(full_api, fake_g2b)
    period = (await a.get("/api/v1/my-bids?from=2026-11-07&to=2026-11-08")).json()
    titled = (await a.get("/api/v1/my-bids?q=00000051 용 역")).json()  # LOST의 사업명
    won_in = (await a.get("/api/v1/my-bids?result=won&from=2026-11-01&to=2026-11-07")).json()
    reversed_ = await a.get("/api/v1/my-bids?from=2026-11-08&to=2026-11-07")
    await a.aclose()

    assert [i["bid_ntce_no"] for i in period["items"]] == [LOST, DQ]  # 11-08, 11-07
    assert period["counts"] == {"all": 2, "won": 0, "lost": 2}
    assert [i["bid_ntce_no"] for i in titled["items"]] == [LOST]
    assert titled["counts"] == {"all": 1, "won": 0, "lost": 1}
    assert [i["bid_ntce_no"] for i in won_in["items"]] == [WON_LATER]  # WON은 11-09
    assert reversed_.status_code == 422


async def test_joint_member_win_counts_as_won(full_api, fake_g2b):
    """공동수급 구성원(대표는 타사)으로 낙찰한 공고도 '낙찰'. 역할·지분을 함께 준다(2026-11-24)."""
    a = await _setup(full_api, fake_g2b)
    joint = "R26BK00000059"
    async with full_api.db.transaction() as s:
        await upsert_awards(s, [to_award(_aw(joint, 6, THEM, "가온"))], {})
        s.add(
            BidJointMember(
                bid_ntce_no=joint,
                bid_ntce_ord="",
                bizno=THEM,
                member_bizno=US,
                role="도급업체",
                joint_mode="공동",
                share=Decimal("25"),
            )
        )
    body = (await a.get("/api/v1/my-bids")).json()
    won = (await a.get("/api/v1/my-bids?result=won")).json()
    lost = (await a.get("/api/v1/my-bids?result=lost")).json()
    await a.aclose()

    by = {i["bid_ntce_no"]: i for i in body["items"]}
    assert (by[joint]["result"], by[joint]["our_role"], by[joint]["our_share"]) == (
        "won",
        "member",
        25.0,
    )
    assert by[joint]["winner_name"] == "가온"
    assert by[WON]["our_role"] is None  # 단독 낙찰
    assert body["counts"] == {"all": 5, "won": 3, "lost": 2}
    assert joint in [i["bid_ntce_no"] for i in won["items"]]
    assert joint not in [i["bid_ntce_no"] for i in lost["items"]]


async def test_export_follows_filters(full_api, fake_g2b):
    """투찰 결과 엑셀(2026-11-25): 화면 조건 그대로, 요약 + 연도별 시트, 시작>종료는 422."""
    from io import BytesIO

    from openpyxl import load_workbook

    a = await _setup(full_api, fake_g2b)
    full = await a.get("/api/v1/my-bids/export")
    lost = await a.get("/api/v1/my-bids/export?result=lost&q=용역")
    bad = await a.get("/api/v1/my-bids/export?from=2026-11-08&to=2026-11-07")
    await a.aclose()

    assert full.status_code == 200, full.text
    assert full.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in full.headers["content-disposition"]
    wb = load_workbook(BytesIO(full.content))
    assert wb.sheetnames == ["요약", "2026"]
    nos = [r[13] for r in list(wb["2026"].iter_rows(values_only=True))[1:]]
    assert sorted(nos) == sorted(f"{n}-000" for n in (WON, LOST, DQ, WON_LATER))
    summary = list(wb["요약"].iter_rows(values_only=True))
    assert summary[1][:4] == (2026, 4, 2, 2)
    assert any("받은 공고 4건" in str(r[0]) for r in summary)
    lw = load_workbook(BytesIO(lost.content))
    results = {r[1] for r in list(lw["2026"].iter_rows(values_only=True))[1:]}
    assert results == {"탈락", "부적격"}
    assert any(
        "결과 탈락 · 사업명 '용역'" in str(r[0]) for r in lw["요약"].iter_rows(values_only=True)
    )
    assert bad.status_code == 422


async def test_detail_lists_all_participants_and_loads_missing_once(full_api, fake_g2b):
    a = await _setup(full_api, fake_g2b)
    before = len(_calls(fake_g2b))
    dq = (await a.get(f"/api/v1/my-bids/{DQ}/000/0/000")).json()
    later = (await a.get(f"/api/v1/my-bids/{WON_LATER}/000/0/000")).json()
    later_again = (await a.get(f"/api/v1/my-bids/{WON_LATER}/000/0/000")).json()
    missing = await a.get("/api/v1/my-bids/R26BK99999999/000/0/000")
    await a.aclose()

    rows = dq["participants"]
    assert [(r["bizno"], r["rank"], r["remark"]) for r in rows] == [
        (THEM, 1, "정상"),
        (US, None, "낙찰하한선 미달"),
    ]
    assert rows[0]["is_winner"] and rows[1]["is_us"]
    assert rows[0]["award_count"] == 2  # THEM의 수집된 낙찰 수(경쟁사 정보)
    assert dq["item"]["result"] == "disqualified"
    # 안 받은 공고는 상세를 열 때 그 공고만 1회 불러오고, 다시 열면 부르지 않는다
    assert _calls(fake_g2b)[before:] == [WON_LATER]
    assert later["item"]["fetched"] is True and later["item"]["our_rank"] == 1
    assert [r["remark"] for r in later["participants"]] == ["정상", "협상평가부적격자"]
    assert later_again["participants"] == later["participants"]
    assert missing.status_code == 404


async def test_my_bids_need_company_settings(full_api):
    from tests.helpers import admin_client as login_admin

    a = await login_admin(full_api)
    r = await a.get("/api/v1/my-bids")
    await a.aclose()
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_configured"
