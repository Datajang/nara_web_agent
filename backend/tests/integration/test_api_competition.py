"""공고 상세 '경쟁 구도' (SPEC §15.6 GET /bids/{bidId}/competition, §15.11 P11).

P11 완료 기준: 한 요청의 새 호출이 6건을 넘지 않는다. 나머지는 '일부만 불러왔어요'로 남고
다음 요청이 이어 부른다. 불러온 개찰 결과는 캐시되고, 비교의 '직접 맞붙은 공고'에 반영된다.
"""

from datetime import UTC, datetime, timedelta
from statistics import median

import httpx
from sqlalchemy import select

from app.awards import participants
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.db.models import CollectorCoverage, UsageLog
from app.deps import Deps
from app.g2b.client import AWARD_SOURCES, G2BClient
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import award_item, opening_item, regular_item
from tests.helpers import admin_client, seed

US, THEM = "1234567890", "2345678901"
ORG = "1111111"
TARGET = "R26BK09000001"
KEYWORDS = {"데이터 정비": ["데이터 정비"]}
RATES = ["85.1", "86.2", "87.3", "88.4", "89.5", "90.6", "91.7", "92.8"]


def _aw(no, days_ago, bizno, title, org=ORG, rate="87.5"):
    return award_item(
        no,
        NOW - timedelta(days=days_ago),
        bizno=bizno,
        name="우리" if bizno == US else "가온",
        org_cd=org,
        org_name=f"기관{org}",
        title=title,
        rate=rate,
    )


SIMILAR = [
    _aw(f"R26BK0000010{i}", 10 + i, THEM if i % 2 else US, f"{2020 + i}년 데이터 정비 사업", rate=r)
    for i, r in enumerate(RATES)
]
AWARDS = [
    *SIMILAR,
    _aw("R26BK00000901", 5, THEM, "청사 청소 용역"),  # 같은 기관, 다른 사업
    _aw("R26BK00000902", 6, THEM, "2026년 데이터 정비 사업", org="9999999"),  # 다른 기관
    _aw(TARGET, 1, THEM, "2026년 데이터 정비 사업 고도화"),  # 이 공고가 이미 낙찰됨
]


async def _setup(api, fake_g2b):
    async with api.db.transaction() as s:
        s.add(
            CollectorCoverage(
                source="awards", covered_from=datetime(2021, 1, 1, tzinfo=UTC), covered_to=NOW
            )
        )
        await upsert_awards(s, [to_award(it) for it in AWARDS], KEYWORDS)
    it = regular_item(TARGET, NOW - timedelta(days=20), title="2026년 데이터 정비 사업 고도화 용역")
    it.update(dminsttCd=ORG, dminsttNm=f"기관{ORG}")
    (bid_id,) = await seed(api.ctx.deps, "regular", it)
    for a in AWARDS:
        no = a["bidNtceNo"]
        fake_g2b.add(
            "opening_compt",
            opening_item(no, a["bidwinnrBizno"], rank="1", name="낙찰사", total="90.5"),
            opening_item(no, US if a["bidwinnrBizno"] == THEM else THEM, rank="2", total="80.25"),
        )
    a = await admin_client(api)
    r = await a.put("/api/v1/admin/company", json={"our_bizno": US, "field_keywords": KEYWORDS})
    assert r.status_code == 200, r.text
    return a, f"b{bid_id}"


def _opening_calls(fake_g2b):
    return [r for r in fake_g2b.requests if "OpengCompt" in r.url.path]


async def test_similar_awards_distribution_and_six_call_cap(full_api, fake_g2b):
    a, ref = await _setup(full_api, fake_g2b)
    r1 = (await a.get(f"/api/v1/bids/{ref}/competition?limit=10")).json()
    calls_1 = len(_opening_calls(fake_g2b))
    r2 = (await a.get(f"/api/v1/bids/{ref}/competition?limit=10")).json()
    calls_2 = len(_opening_calls(fake_g2b))
    r3 = (await a.get(f"/api/v1/bids/{ref}/competition?limit=10")).json()
    calls_3 = len(_opening_calls(fake_g2b))
    compare = (await a.get(f"/api/v1/compare/{THEM}")).json()
    await a.aclose()

    # 같은 수요기관의 비슷한 사업만(청소·다른 기관 제외), 이 공고 자체는 this_award
    assert r1["org"] == {"code": ORG, "name": f"기관{ORG}"}
    assert {x["bid_ntce_no"] for x in r1["similar"]} == {x["bidNtceNo"] for x in SIMILAR}
    assert r1["similar_total"] == 8 and r1["this_award"]["bid_ntce_no"] == TARGET
    rates = [float(x) for x in RATES]
    assert r1["distribution"]["g2b_rate"] == {
        "n": 8,
        "min": min(rates),
        "median": round(median(rates), 5),
        "max": max(rates),
    }
    assert r1["distribution"]["award_ratio"] is None  # 추정가격 있는 낙찰 없음

    # 온디맨드: 필요한 공고 9건(이 공고 + 비슷한 8건) 중 한 요청에 6건까지
    st1, st2, st3 = (r["participants_status"] for r in (r1, r2, r3))
    assert calls_1 == 6 and st1 == {
        "requested": 9,
        "loaded": 6,
        "fetched_now": 6,
        "partial": True,
        "failed": False,
        "budget_exhausted": False,
    }
    assert calls_2 - calls_1 == 3 and st2["fetched_now"] == 3 and st2["partial"] is False
    assert calls_3 == calls_2 and st3["loaded"] == 9  # 캐시만 읽음
    # 이 공고가 맨 먼저 불러와지고, 못 부른 공고는 participants=null('일부만')
    assert r1["this_award"]["participants"] is not None
    assert sum(x["participants"] is None for x in r1["similar"]) == 3
    p = r3["this_award"]["participants"]
    assert [(x["rank"], x["is_winner"], x["is_us"]) for x in p] == [
        (1, True, False),
        (2, False, True),
    ]
    assert all(x["us_participated"] for x in r3["similar"])

    # 우리 회사: 이 기관 낙찰 4건, 불러온 개찰 결과 중 참가 9건·낙찰 4건
    assert r3["us"] == {"bizno": US, "name": "우리", "org_awards": 4, "participated": 9, "won": 4}
    # 개찰 결과가 쌓여 '직접 맞붙은 공고'가 판정된다(우리 4승, 가온 5승)
    h2h = next(v for v in compare["verdicts"] if v["key"] == "head_to_head")
    assert compare["head_to_head"] == {"matched": 9, "us_wins": 4, "them_wins": 5}
    assert h2h["verdict"] == "down" and h2h["small_sample"] is False

    async with full_api.db.session() as s:
        logs = (await s.execute(select(UsageLog).where(UsageLog.event == "competition"))).scalars()
        logs = list(logs)
    assert [x.g2b_calls for x in logs] == [6, 3]  # 캐시만 읽은 요청은 G2B 기록 없음
    assert all(x.cache["source"] == "opening_compt" for x in logs)


async def test_competition_without_company_or_awards(full_api):
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item(TARGET, NOW))
    a = await admin_client(full_api)
    r = await a.get(f"/api/v1/bids/b{bid_id}/competition")
    await a.aclose()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["us"] is None and body["similar"] == [] and body["this_award"] is None
    assert body["period"]["collecting"] is True  # 낙찰 수집 전
    assert body["participants_status"]["requested"] == 0


async def _deps_with(full_api, http, budget):
    g2b = G2BClient(
        http,
        TEST_KEYS,
        retry_delays=(0, 0, 0),
        source_budgets=dict.fromkeys(AWARD_SOURCES, budget),
    )
    d = full_api.ctx.deps
    return Deps(db=d.db, g2b=g2b, llm=None, downloader=None, settings=d.settings, clock=d.clock)


async def test_awards_budget_stops_on_demand_calls(full_api, fake_g2b):
    await _setup(full_api, fake_g2b)
    budget = DbCallBudget(full_api.db, 2, sources=AWARD_SOURCES, label="낙찰")
    async with fake_g2b.http_client() as http:
        deps = await _deps_with(full_api, http, budget)
        res = await participants.ensure(deps, [(x["bidNtceNo"], "000") for x in SIMILAR], None)
    assert (res.fetched_now, res.g2b_calls, res.budget_exhausted) == (2, 2, True)
    assert len(res.missing) == 6


async def test_retries_count_toward_the_six_call_cap(full_api, fake_g2b):
    await _setup(full_api, fake_g2b)
    fake_g2b.fail(*(httpx.Response(503) for _ in range(20)))
    budget = DbCallBudget(full_api.db, 300, sources=AWARD_SOURCES)
    async with fake_g2b.http_client() as http:
        deps = await _deps_with(full_api, http, budget)
        notices = [(x["bidNtceNo"], "000") for x in SIMILAR]
        res = await participants.ensure(deps, notices, None, max_calls=6)
    assert res.g2b_calls <= 6 and res.failed and res.fetched_now == 0
