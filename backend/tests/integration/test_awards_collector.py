"""낙찰 수집기 (SPEC §15.4·§15.11 P8, docs/decisions/2026-11-16-awards-probe.md).

P8 완료 기준: 같은 창을 두 번 받아도 행이 늘지 않음 · 예산을 넘으면 멈춤 · (실제 30일은 수동 확인).
그 밖: 개인정보 미저장, 일부 페이지만 받은 창은 미완료, 사업자번호 없는 낙찰, 추정가격·분야.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, inspect, select, text

from app.awards import collector as awards
from app.db.models import (
    BidAward,
    CollectorCoverage,
    CollectorRun,
    Company,
    OrgSettings,
    UsageLog,
)
from app.g2b.client import G2BClient
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import award_item, regular_item
from tests.helpers import seed

AWARD_TABLES = (
    "companies",
    "bid_awards",
    "bid_participants",
    "bid_joint_members",
    "bid_participant_fetches",
    "org_settings",
    "watched_companies",
)


async def _count(deps, model):
    async with deps.db.session() as s:
        return await s.scalar(select(func.count()).select_from(model))


async def _coverage(deps):
    async with deps.db.session() as s:
        return await s.get(CollectorCoverage, "awards")


async def test_same_window_twice_adds_no_rows(deps, fake_g2b):
    fake_g2b.add(
        "awards",
        *(award_item(f"R26BK0{i:07d}", NOW - timedelta(hours=i + 1)) for i in range(5)),
        award_item("R26BK09999999", NOW - timedelta(days=3), bizno="2345678901", name="나래(주)"),
    )
    first = await awards.backfill(deps, days=7)
    second = await awards.backfill(deps, days=7)  # 이미 덮은 구간이면 호출하지 않음
    third = await awards.incremental(deps)  # 최근 14일을 다시 받음
    assert first.status == second.status == third.status == "ok"
    assert first.inserted == 6 and third.inserted == 0 and third.updated == 0
    assert await _count(deps, BidAward) == 6
    assert await _count(deps, Company) == 2


async def test_windows_cover_at_most_seven_kst_dates(deps, fake_g2b):
    """시작일~종료일이 KST 날짜 8개 이상이면 resultCode 07 → 창은 KST 자정에 맞춘 7일."""
    result = await awards.backfill(deps, days=21)
    assert result.status == "ok"
    got = [(r.url.params["inqryBgnDt"], r.url.params["inqryEndDt"]) for r in fake_g2b.requests]
    # NOW = 2026-11-10 15:00 KST. 최신 창이 먼저, 짧은 조각은 가장 오래된 쪽
    assert got == [
        ("202611040000", "202611101459"),
        ("202610280000", "202611032359"),
        ("202610210000", "202610272359"),
        ("202610201500", "202610202359"),
    ]
    for r in fake_g2b.requests:
        assert r.url.params["numOfRows"] == "100" and r.url.params["inqryDiv"] == "1"
    cov = await _coverage(deps)
    assert cov.covered_from == NOW - timedelta(days=21) and cov.covered_to == NOW


async def test_partial_pages_do_not_complete_window(deps, fake_g2b):
    fake_g2b.add(
        "awards",
        *(award_item(f"R26BK1{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(150)),
    )
    fake_g2b.drop_pages = {2}  # 100행 페이지 1만 오고 2는 빈 목록
    result = await awards.backfill(deps, days=7)
    assert result.status == "failed" and "일부만" in (result.error or "")
    assert await _coverage(deps) is None  # 경계를 옮기지 않음
    assert await _count(deps, BidAward) == 0  # 그 창은 저장하지 않음


async def test_budget_stops_backfill_and_keeps_contiguous_coverage(deps, fake_g2b, db):
    """하루 awards 예산을 넘으면 멈추고, 받은 창까지만 커버리지가 이어진다 (§15.4, 수용 기준 8)."""
    budget = DbCallBudget(db, 2, sources={"awards"}, label="낙찰")
    deps.g2b = G2BClient(
        fake_g2b.http_client(),
        TEST_KEYS,
        page_size=100,
        retry_delays=(0, 0, 0),
        source_budgets={"awards": budget},
    )
    fake_g2b.add("awards", award_item("R26BK20000001", NOW - timedelta(days=1)))
    result = await awards.backfill(deps, days=35)  # 5창 필요
    assert result.status == "failed" and "예산" in (result.error or "")
    assert fake_g2b.calls == 2 and result.g2b_calls == 2
    cov = await _coverage(deps)
    # 두 창(11-04~11-10, 10-28~11-03 KST)까지만: covered_from = 10-28 00:00 KST
    assert cov.covered_to == NOW and cov.covered_from == datetime(2026, 10, 27, 15, 0, tzinfo=UTC)
    async with deps.db.session() as s:
        logged = await s.scalar(
            select(func.sum(UsageLog.g2b_calls)).where(UsageLog.cache["source"].astext == "awards")
        )
    assert logged == 2
    # 다음 날(예산 초기화 가정): 남은 과거 창부터 이어서 채운다
    deps.g2b = G2BClient(fake_g2b.http_client(), TEST_KEYS, page_size=100, retry_delays=(0, 0, 0))
    again = await awards.backfill(deps, days=35)
    cov = await _coverage(deps)
    assert again.status == "ok" and cov.covered_from == NOW - timedelta(days=35)


async def test_personal_fields_are_never_stored(deps, fake_g2b):
    fake_g2b.add("awards", award_item("R26BK30000001", NOW - timedelta(hours=2), pii=True))
    await awards.backfill(deps, days=7)
    async with deps.db.engine.connect() as conn:
        cols = await conn.run_sync(
            lambda c: {t: [x["name"] for x in inspect(c).get_columns(t)] for t in AWARD_TABLES}
        )
        values: list[str] = []
        for t in ("companies", "bid_awards"):
            for row in (await conn.execute(text(f"SELECT * FROM {t}"))).all():
                values += [str(v) for v in row]
    dump = " ".join(values)
    assert "R26BK30000001" in dump  # 행은 저장됨
    banned = ("ceo", "adrs", "addr", "tel", "phone", "ofcl", "raw")
    assert not [c for cs in cols.values() for c in cs if any(b in c.lower() for b in banned)]
    for secret in ("홍길동대표", "어딘가로", "02-555-0199", "김담당"):
        assert secret not in dump


async def test_award_without_bizno_is_kept_but_unidentified(deps, fake_g2b):
    fake_g2b.add(
        "awards",
        award_item("R26BK40000001", NOW - timedelta(hours=1), bizno=None, name="알 수 없음"),
        award_item("R26BK40000002", NOW - timedelta(hours=2), bizno="12345"),  # 10자리 아님
        award_item("R26BK40000003", NOW - timedelta(hours=3), bizno="123-45-67890"),
    )
    await awards.backfill(deps, days=7)
    await awards.incremental(deps)  # NULL 사업자번호도 멱등
    async with deps.db.session() as s:
        rows = dict((await s.execute(select(BidAward.bid_ntce_no, BidAward.bizno))).all())
    assert rows == {
        "R26BK40000001": None,
        "R26BK40000002": None,
        "R26BK40000003": "1234567890",
    }
    assert await _count(deps, Company) == 1


async def test_lots_and_rebids_are_separate_rows(deps, fake_g2b):
    """한 공고의 분류(bidClsfcNo)·재입찰(rbidNo)은 각각 한 행 (probe 1번)."""
    t = NOW - timedelta(hours=1)
    fake_g2b.add(
        "awards",
        award_item("R26BK50000001", t, clsfc="0"),
        award_item("R26BK50000001", t, clsfc="1", bizno="2345678901"),
        award_item("R26BK50000001", t, clsfc="1", rbid="001", bizno="2345678901"),
    )
    await awards.backfill(deps, days=7)
    assert await _count(deps, BidAward) == 3


async def test_winner_change_updates_row(deps, fake_g2b):
    t = NOW - timedelta(hours=5)
    fake_g2b.add("awards", award_item("R26BK60000001", t, bizno="1111111111", name="갑"))
    await awards.backfill(deps, days=7)
    fake_g2b.items["awards"] = [
        award_item("R26BK60000001", t + timedelta(hours=1), bizno="2222222222", name="을")
    ]
    r = await awards.incremental(deps)
    assert r.updated == 1
    async with deps.db.session() as s:
        assert await s.scalar(select(BidAward.bizno)) == "2222222222"
        assert await s.scalar(select(func.count()).select_from(BidAward)) == 1


async def test_company_name_follows_latest_award(deps, fake_g2b):
    """백필은 과거로 가므로, 과거 낙찰의 옛 상호가 최신 상호를 덮지 않는다."""
    fake_g2b.add("awards", award_item("R26BK70000001", NOW - timedelta(days=1), name="새이름(주)"))
    await awards.backfill(deps, days=7)
    fake_g2b.add("awards", award_item("R26BK70000002", NOW - timedelta(days=10), name="옛이름(주)"))
    await awards.backfill(deps, days=14)
    async with deps.db.session() as s:
        c = await s.get(Company, "1234567890")
    assert c.name == "새이름(주)" and c.name_norm == "새이름"
    assert c.first_seen_at < c.last_seen_at


async def test_estimated_price_and_ratio_only_when_bid_known(deps, fake_g2b):
    await seed(deps, "regular", regular_item("R26BK80000001", NOW - timedelta(days=30)))
    fake_g2b.add(
        "awards",
        award_item("R26BK80000001", NOW - timedelta(hours=1), amount="80000000"),
        award_item("R26BK80000002", NOW - timedelta(hours=2), amount="50000000"),
    )
    await awards.backfill(deps, days=7)
    async with deps.db.session() as s:
        rows = {
            r.bid_ntce_no: r
            for r in (await s.execute(select(BidAward))).scalars()  # noqa: B020
        }
    known, unknown = rows["R26BK80000001"], rows["R26BK80000002"]
    assert known.estimated_price == 100_000_000 and known.award_ratio == Decimal("0.80000")
    assert known.g2b_award_rate == Decimal("87.500")  # G2B 낙찰률은 따로
    assert unknown.estimated_price is None and unknown.award_ratio is None


async def test_fields_from_org_settings_keywords(deps, fake_g2b):
    async with deps.db.transaction() as s:
        s.add(
            OrgSettings(
                id=1,
                field_keywords={"데이터 정비": ["데이터 정비", "DB구축"], "AI 분석": ["인공지능"]},
            )
        )
    fake_g2b.add(
        "awards",
        award_item("R26BK90000001", NOW - timedelta(hours=1), title="인공지능 기반 DB 구축 사업"),
        award_item("R26BK90000002", NOW - timedelta(hours=2), title="청사 청소 용역"),
    )
    await awards.backfill(deps, days=7)
    async with deps.db.session() as s:
        got = dict((await s.execute(select(BidAward.bid_ntce_no, BidAward.fields))).all())
    assert got == {"R26BK90000001": ["AI 분석", "데이터 정비"], "R26BK90000002": []}


async def test_backfill_years_from_org_settings(deps, fake_g2b):
    async with deps.db.transaction() as s:
        s.add(OrgSettings(id=1, backfill_years=1))
    result = await awards.backfill(deps)
    cov = await _coverage(deps)
    assert result.status == "ok" and cov.covered_from == NOW - timedelta(days=365)
    assert fake_g2b.calls == 53  # 365일 ÷ 7일 창


async def test_runs_use_existing_modes(deps, fake_g2b):
    await awards.backfill(deps, days=7)
    await awards.incremental(deps)
    async with deps.db.session() as s:
        runs = (await s.execute(select(CollectorRun.source, CollectorRun.mode))).all()
    assert runs == [("awards", "backfill"), ("awards", "incremental")]
