"""낙찰 수집을 받치는 부분: 클라이언트(7일 창·페이지 상한·소스 예산), 예산 집계, /readyz,
재분류 스크립트, CLI (SPEC §15.2~§15.4)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.awards import collector as awards
from app.awards.reclassify import reclassify
from app.collector import __main__ as collector_cli
from app.db.models import BidAward, CollectorRun, OrgSettings, UsageLog
from app.g2b.client import G2BBudgetExceeded, G2BClient, G2BIncomplete
from app.ops.status import last_collector_ok
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import FakeG2B, award_item, regular_item
from tests.helpers import seed


def _client(fake: FakeG2B, **kw) -> G2BClient:
    return G2BClient(fake.http_client(), TEST_KEYS, retry_delays=(0, 0, 0), **kw)


async def test_awards_fetch_splits_by_kst_dates():
    """클라이언트도 날짜 7개 단위로 자른다(수집기가 아닌 곳에서 불러도 07 오류 없음)."""
    fake = FakeG2B()
    fake.add("awards", award_item("R26BK00000001", NOW - timedelta(days=9)))
    items = await _client(fake).fetch("awards", NOW - timedelta(days=14), NOW)
    got = [(r.url.params["inqryBgnDt"], r.url.params["inqryEndDt"]) for r in fake.requests]
    assert len(items) == 1
    assert got == [
        ("202610271500", "202611022359"),
        ("202611030000", "202611092359"),
        ("202611100000", "202611101459"),
    ]


async def test_page_size_is_capped_at_999():
    """numOfRows=1000은 실제 API가 조용히 10행만 준다 (probe 2번)."""
    fake = FakeG2B()
    await _client(fake, page_size=1000).fetch("awards", NOW - timedelta(days=1), NOW)
    assert fake.requests[0].url.params["numOfRows"] == "999"


async def test_missing_page_raises_incomplete_for_awards_only():
    fake = FakeG2B()
    fake.add(
        "awards", *(award_item(f"R26BK1{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(15))
    )
    fake.add(
        "regular",
        *(regular_item(f"R26BK2{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(15)),
    )
    fake.drop_pages = {2}
    with pytest.raises(G2BIncomplete):
        await _client(fake, page_size=10).fetch("awards", NOW - timedelta(days=1), NOW)
    # 공고 수집은 기존 동작 그대로(받은 만큼)
    assert (
        len(await _client(fake, page_size=10).fetch("regular", NOW - timedelta(days=1), NOW)) == 10
    )


class _Budget:
    def __init__(self, limit: int) -> None:
        self.limit, self.pending, self.settled = limit, 0, 0

    async def reserve(self) -> None:
        if self.pending >= self.limit:
            raise G2BBudgetExceeded("소진")
        self.pending += 1

    def settle(self, n: int) -> None:
        self.pending -= n
        self.settled += n


async def test_source_budget_is_returned_when_global_budget_refuses():
    fake = FakeG2B()
    src, total = _Budget(5), _Budget(0)
    c = _client(fake, budget=total, source_budgets={"awards": src})
    with pytest.raises(G2BBudgetExceeded):
        await c.fetch("awards", NOW - timedelta(days=1), NOW)
    assert src.pending == 0 and fake.calls == 0
    # 공고 소스는 awards 예산을 쓰지 않는다
    total.limit = 10
    await c.fetch("regular", NOW - timedelta(days=1), NOW)
    assert src.pending == 0 and total.pending == 1


async def test_db_budget_counts_only_its_sources(db):
    async with db.transaction() as s:
        s.add_all(
            [
                UsageLog(event="collector", g2b_calls=7, cache={"source": "regular"}),
                UsageLog(event="collector", g2b_calls=3, cache={"source": "awards"}),
                UsageLog(event="search", g2b_calls=2, cache={}),
            ]
        )
    assert await DbCallBudget(db, 100).used_today() == 12
    assert await DbCallBudget(db, 100, sources={"awards", "contracts"}).used_today() == 3
    b = DbCallBudget(db, 3, sources={"awards"}, label="낙찰")
    with pytest.raises(G2BBudgetExceeded, match="낙찰 일일 호출 예산 3회"):
        await b.reserve()


async def test_readyz_last_ok_ignores_award_runs(deps):
    async with deps.db.transaction() as s:
        s.add(
            CollectorRun(
                source="awards",
                mode="incremental",
                window_from=NOW,
                window_to=NOW,
                status="ok",
                finished_at=NOW,
            )
        )
    assert await last_collector_ok(deps) is None


async def test_reclassify_recomputes_fields_and_prices(deps, fake_g2b):
    fake_g2b.add(
        "awards",
        award_item(
            "R26BK30000001",
            NOW - timedelta(hours=1),
            title="빅데이터 플랫폼 구축",
            amount="45000000",
        ),
    )
    await awards.backfill(deps, days=7)
    # 사전과 bids가 나중에 바뀜
    async with deps.db.transaction() as s:
        s.add(OrgSettings(id=1, field_keywords={"데이터": ["빅데이터"]}))
    await seed(
        deps, "regular", regular_item("R26BK30000001", NOW - timedelta(days=20), budget="50000000")
    )
    r1 = await reclassify(deps.db, batch=1)
    r2 = await reclassify(deps.db)
    assert (r1.scanned, r1.fields_changed, r1.prices_changed) == (1, 1, 1)
    assert (r2.fields_changed, r2.prices_changed) == (0, 0)  # 같은 사전이면 그대로
    async with deps.db.session() as s:
        row = await s.scalar(select(BidAward))
    assert row.fields == ["데이터"] and row.estimated_price == 50_000_000
    assert str(row.award_ratio) == "0.90000"


async def test_cli_rejects_fill_for_awards():
    with pytest.raises(SystemExit):
        await collector_cli.main(
            ["fill", "--source", "awards", "--from", "2026-11-01", "--to", "2026-11-02"]
        )
