"""개찰 결과 자동 수집 `openings` (P12 우리 투찰 결과).

- 증분: 최근 14일 낙찰 공고 중 안 받은 것을 받고 비고(탈락 사유)까지 저장.
  다시 돌려도 다시 부르지 않는다
- 백필: 오래된 공고를 우리 낙찰 → 우리 분야·기관 → 나머지 순으로
- 하루 몫(openings)을 다 쓰면 정상 종료, 낙찰 몫 예산과 따로 센다
- 공고 하나의 G2B 오류는 건너뛰고, 연속 3번이면 멈춘다
"""

from datetime import timedelta

import httpx
from sqlalchemy import select

from app.awards import openings
from app.awards.mapper import to_award
from app.awards.store import upsert_awards
from app.db.models import BidParticipant, CollectorRun, OrgSettings, UsageLog
from app.deps import Deps
from app.g2b.client import OPENINGS_SOURCE, G2BClient
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import award_item, opening_item

US, THEM, OTHER = "1234567890", "2345678901", "3456789012"
OUR_ORG = "7777777"


async def _awards(deps, items, us=US, keywords=None):
    async with deps.db.transaction() as s:
        s.add(OrgSettings(id=1, our_bizno=us, our_name="우리", field_keywords=keywords or {}))
        await upsert_awards(s, [to_award(it) for it in items], keywords or {})


def _calls(fake_g2b):
    return [r.url.params["bidNtceNo"] for r in fake_g2b.requests if "OpengCompt" in r.url.path]


async def test_incremental_fetches_recent_notices_once_with_remarks(deps, fake_g2b):
    await _awards(
        deps,
        [
            award_item("R26BK00000001", NOW - timedelta(days=1), bizno=THEM),
            award_item("R26BK00000002", NOW - timedelta(days=3), bizno=THEM),
            award_item("R26BK00000003", NOW - timedelta(days=30), bizno=THEM),  # 백필 몫
        ],
    )
    fake_g2b.add(
        "opening_compt",
        opening_item("R26BK00000001", THEM, rank="1"),
        opening_item("R26BK00000001", US, rank="", remark="낙찰하한선 미달"),
    )
    r = await openings.run(deps, "incremental")
    again = await openings.run(deps, "incremental")
    assert r.status == again.status == "ok"
    assert _calls(fake_g2b) == ["R26BK00000001", "R26BK00000002"]  # 최신부터, 두 번째 실행은 0회
    assert (r.inserted, r.fetched, r.g2b_calls, again.g2b_calls) == (2, 2, 2, 0)
    async with deps.db.session() as s:
        ours = await s.scalar(select(BidParticipant).where(BidParticipant.bizno == US))
        logs = (await s.execute(select(UsageLog.cache["source"].astext))).scalars().all()
        runs = (await s.execute(select(CollectorRun.source, CollectorRun.mode))).all()
    assert ours is not None and ours.rank is None and ours.remark == "낙찰하한선 미달"
    assert OPENINGS_SOURCE in logs and ("openings", "incremental") in runs


async def test_order_our_wins_then_our_fields_and_orgs_then_rest(deps, fake_g2b):
    old = NOW - timedelta(days=40)
    await _awards(
        deps,
        [
            award_item("R26BK00000011", old + timedelta(days=5), bizno=THEM, title="청소 용역"),
            award_item("R26BK00000012", old, bizno=US, title="청소", org_cd=OUR_ORG),  # 우리 낙찰
            award_item("R26BK00000013", old + timedelta(days=1), bizno=THEM, title="데이터 정비"),
            award_item("R26BK00000014", old + timedelta(days=2), bizno=OTHER, org_cd=OUR_ORG),
            award_item("R26BK00000015", NOW - timedelta(days=1), bizno=THEM),  # 증분 몫이라 제외
        ],
        keywords={"데이터": ["데이터 정비"]},
    )
    deps.settings.g2b_openings_daily_budget = 10
    r = await openings.run(deps, "backfill")
    assert r.status == "ok"
    # 우리 낙찰 → (우리 분야 또는 우리가 낙찰한 기관, 최신부터) → 나머지
    assert _calls(fake_g2b) == ["R26BK00000012", "R26BK00000014", "R26BK00000013", "R26BK00000011"]
    # 증분도 같은 순서(최근 14일 안에서): 우리와 관련된 공고가 먼저
    async with deps.db.transaction() as s:
        await upsert_awards(
            s,
            [
                to_award(award_item("R26BK00000016", NOW - timedelta(days=1), bizno=THEM)),
                to_award(
                    award_item(
                        "R26BK00000017", NOW - timedelta(days=3), bizno=OTHER, org_cd=OUR_ORG
                    )
                ),
            ],
            {},
        )
    fake_g2b.requests.clear()
    await openings.run(deps, "incremental")
    # 15(분야)·17(우리 기관)이 먼저(최신부터), 관련 없는 16은 더 최신이어도 뒤
    assert _calls(fake_g2b) == ["R26BK00000015", "R26BK00000017", "R26BK00000016"]


async def test_openings_budget_is_its_own_share_and_stops_cleanly(db, fake_g2b, settings):
    http = fake_g2b.http_client()
    g2b = G2BClient(
        http,
        TEST_KEYS,
        retry_delays=(0,),
        source_budgets={
            OPENINGS_SOURCE: DbCallBudget(db, 2, sources=[OPENINGS_SOURCE], label="개찰 결과")
        },
    )
    deps = Deps(db=db, g2b=g2b, llm=None, downloader=None, settings=settings, clock=lambda: NOW)  # type: ignore[arg-type]
    await _awards(
        deps,
        [award_item(f"R26BK0000002{i}", NOW - timedelta(days=i + 1), bizno=THEM) for i in range(4)],
    )
    async with deps.db.transaction() as s:  # 낙찰 몫을 많이 써도 개찰 결과 몫과 무관
        s.add(UsageLog(event="collector", g2b_calls=500, cache={"source": "awards"}))
    r1 = await openings.run(deps, "incremental")
    r2 = await openings.run(deps, "incremental")
    await http.aclose()
    assert (r1.status, r1.g2b_calls, r1.inserted) == ("ok", 2, 2)
    assert "개찰 결과" in (r1.error or "")
    assert (r2.status, r2.g2b_calls) == ("ok", 0)  # 오늘 몫 소진: 다음 날 이어 받는다


async def test_one_bad_notice_is_skipped_three_in_a_row_stop(deps, fake_g2b):
    await _awards(
        deps,
        [award_item(f"R26BK0000003{i}", NOW - timedelta(days=i + 1), bizno=THEM) for i in range(5)],
    )
    err = httpx.Response(500, text="oops")
    deps.g2b.retry_delays = ()  # 재시도 없이: 실패 응답 하나 = 공고 하나 실패
    fake_g2b.fail(err)  # 첫 공고만 실패
    r = await openings.run(deps, "incremental")
    assert r.status == "ok" and r.inserted == 4  # 하나 건너뜀, 다음 실행에서 다시
    again = await openings.run(deps, "incremental")
    assert again.inserted == 1

    await _more(deps)
    fake_g2b.fail(err, err, err)
    stopped = await openings.run(deps, "incremental")
    assert stopped.status == "failed" and stopped.inserted == 0


async def _more(deps):
    async with deps.db.transaction() as s:
        await upsert_awards(
            s,
            [
                to_award(award_item(f"R26BK0000004{i}", NOW - timedelta(days=i + 1), bizno=THEM))
                for i in range(4)
            ],
            {},
        )
