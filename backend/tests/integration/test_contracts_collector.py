"""계약 수집기 `contracts`: 공동수급 구성 (SPEC §15.4 계약정보, P11).

- 공동(단독이 아닌) 계약만 bid_joint_members에 저장, 같은 공고의 낙찰은 is_joint=true
- 낙찰이 계약보다 나중에 와도 is_joint가 맞춰진다(수집 순서 무관)
- 같은 창을 다시 받아도 행이 늘지 않는다, 예산(낙찰 몫)을 함께 쓴다, 백필은 낙찰 범위 안에서만
"""

from datetime import timedelta

from sqlalchemy import func, select

from app.awards import collector as awards
from app.awards import contracts
from app.db.models import BidAward, BidJointMember, CollectorCoverage, UsageLog
from tests.conftest import NOW
from tests.fakes.g2b import award_item, contract_item

LEAD, SUB, SOLO = "3178123292", "3288802700", "1078655270"


def _contracts():
    return [
        contract_item(
            "R26BK00000001",
            NOW - timedelta(days=1),
            [("주계약업체", "케이정보기술", "60", LEAD), ("도급업체", "윌코모시스템즈", "40", SUB)],
        ),
        contract_item(
            "R26BK00000002",
            NOW - timedelta(days=2),
            [("주계약업체", "유알피", "100", SOLO)],
            mode="단독",
        ),
        contract_item("", NOW - timedelta(days=2), [("주계약업체", "수의", "100", SOLO)]),
    ]


def _awards():
    return [
        award_item("R26BK00000001", NOW - timedelta(days=3), bizno=LEAD, name="케이정보기술"),
        award_item("R26BK00000002", NOW - timedelta(days=4), bizno=SOLO, name="유알피"),
    ]


async def _joint(deps):
    async with deps.db.session() as s:
        rows = (await s.execute(select(BidAward.bid_ntce_no, BidAward.is_joint))).all()
        members = (
            await s.execute(
                select(
                    BidJointMember.member_bizno, BidJointMember.bizno, BidJointMember.bid_ntce_ord
                ).order_by(BidJointMember.member_bizno)
            )
        ).all()
    return dict(rows), members


async def test_joint_contracts_mark_awards_and_store_members(deps, fake_g2b):
    fake_g2b.add("awards", *_awards())
    fake_g2b.add("contracts", *_contracts())
    await awards.incremental(deps)
    r = await contracts.incremental(deps)
    again = await contracts.incremental(deps)
    flags, members = await _joint(deps)
    assert r.status == again.status == "ok"
    assert flags == {"R26BK00000001": True, "R26BK00000002": False}
    # 주계약·도급 모두 저장, 주계약업체 = 낙찰 업체, 신체계는 차수 ''
    assert members == [(LEAD, LEAD, ""), (SUB, LEAD, "")]
    async with deps.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(BidJointMember)) == 2
        cov = await s.get(CollectorCoverage, "contracts")
        sources = (await s.execute(select(UsageLog.cache["source"].astext))).scalars().all()
    assert cov is not None
    assert "contracts" in sources  # 낙찰 몫 예산(cache.source)으로 센다


async def test_award_arriving_after_contract_is_marked_joint(deps, fake_g2b):
    fake_g2b.add("contracts", *_contracts())
    await contracts.incremental(deps)
    fake_g2b.add("awards", *_awards())
    await awards.incremental(deps)
    flags, _ = await _joint(deps)
    assert flags["R26BK00000001"] is True


async def test_backfill_stays_inside_award_coverage(deps, fake_g2b):
    assert (await contracts.backfill(deps, days=30)).g2b_calls == 0  # 낙찰 수집 전이면 할 일 없음
    fake_g2b.add("awards", *_awards())
    await awards.backfill(deps, days=7)
    await contracts.backfill(deps, days=365)
    async with deps.db.session() as s:
        a = await s.get(CollectorCoverage, "awards")
        c = await s.get(CollectorCoverage, "contracts")
    assert a is not None and c is not None
    assert c.covered_from >= a.covered_from


async def test_compare_shows_joint_partners_of_both_companies(full_api):
    from app.awards.contracts import upsert_members

    from .test_api_competitors import THEM, US
    from .test_api_explain_tools import _setup

    a = await _setup(full_api)  # 낙찰: 우리 R26BK00000001·2, 가온 R26BK00000100~
    before = (await a.get(f"/api/v1/compare/{THEM}")).json()["joint"]
    async with full_api.db.transaction() as s:
        await s.merge(CollectorCoverage(source="contracts", covered_from=NOW, covered_to=NOW))
        a1, b1 = ("주계약업체", "우리", "70", US), ("도급업체", "파트너A", "30", LEAD)
        a2, b2 = ("주계약업체", "가온", "60", THEM), ("도급업체", "파트너B", "40", SUB)
        await upsert_members(
            s,
            [
                contract_item("R26BK00000001", NOW, [a1, b1]),
                contract_item("R26BK00000002", NOW, [a1, b1]),
                contract_item("R26BK00000100", NOW, [a2, b2]),
            ],
        )
    r = (await a.get(f"/api/v1/compare/{THEM}")).json()
    summary = (await a.get("/api/v1/awards/summary")).json()
    await a.aclose()
    assert before == {"collected": False, "us": [], "them": []}  # 계약정보 수집 전
    assert r["joint"]["collected"] is True
    assert r["joint"]["us"] == [{"bizno": LEAD, "name": "파트너A", "count": 2}]
    assert r["joint"]["them"] == [{"bizno": SUB, "name": "파트너B", "count": 1}]
    assert summary["joint_count"] == 2  # 낙찰 is_joint도 맞춰짐


async def test_backfill_stops_at_per_run_cap_as_normal_and_resumes(deps, fake_g2b):
    """계약은 낙찰보다 훨씬 많아 백필을 하루 몫씩 나눠 받는다. 상한은 정상 종료."""
    import dataclasses

    fake_g2b.add("awards", *_awards())
    await awards.backfill(deps, days=21)
    fake_g2b.add(
        "contracts",
        *(
            contract_item(f"R26BK0000{i:04d}", NOW - timedelta(days=i * 7 + 1), [])
            for i in range(3)
        ),
    )
    capped = dataclasses.replace(
        deps, settings=deps.settings.model_copy(update={"g2b_contracts_backfill_calls": 1})
    )
    first = await contracts.backfill(capped, days=21)
    async with deps.db.session() as s:
        after_first = (await s.get(CollectorCoverage, "contracts")).covered_from
    second = await contracts.backfill(capped, days=21)
    async with deps.db.session() as s:
        after_second = (await s.get(CollectorCoverage, "contracts")).covered_from
    assert first.status == second.status == "ok"
    assert first.g2b_calls == 1 and "상한" in (first.error or "")
    assert after_second < after_first  # 다음 실행이 이어서 과거로


async def test_contract_personal_fields_are_never_stored(deps, fake_g2b):
    """§15.9: corpList의 대표자명(5번째)·담당자(9번째) 칸은 읽지 않는다."""
    it = contract_item("R26BK00000001", NOW - timedelta(days=1), [])
    it["corpList"] = (
        f"[1^주계약업체^공동^케이정보기술^홍길동대표^대한민국^60^채권자^김담당^{LEAD}],"
        f"[2^도급업체^공동^윌코모시스템즈^이대표^대한민국^40^^박담당^{SUB}]"
    )
    fake_g2b.add("contracts", it)
    await contracts.incremental(deps)
    async with deps.db.session() as s:
        rows = (await s.execute(select(BidJointMember))).scalars().all()
    dump = " ".join(str(v) for r in rows for v in vars(r).values())
    assert len(rows) == 2
    for secret in ("홍길동대표", "이대표", "김담당", "박담당", "채권자"):
        assert secret not in dump
