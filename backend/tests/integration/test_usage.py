"""usage_logs 집계 (SPEC §5.8)와 일일 예산 집계."""

from datetime import timedelta

from app.db.models import UsageLog
from app.usage.budget import DbCallBudget
from app.usage.stats import daily_usage
from tests.conftest import NOW


async def test_daily_usage_hit_rates(db):
    async with db.transaction() as s:
        s.add_all(
            [
                UsageLog(event="search", cache={"bids_db": False}, g2b_calls=4),
                UsageLog(event="search", cache={"bids_db": True}, g2b_calls=0),
                UsageLog(event="search", cache={"bids_db": True}, g2b_calls=0),
                UsageLog(
                    event="analyze",
                    cache={"summary": True, "analysis": False},
                    llm_calls=1,
                    prompt_tokens=10,
                    completion_tokens=5,
                ),
            ]
        )
    async with db.session() as s:
        rows = {r.event: r for r in await daily_usage(s, NOW - timedelta(days=3650))}
    assert rows["search"].requests == 3 and rows["search"].g2b_calls == 4
    assert abs(rows["search"].hit_rate["bids_db"] - 2 / 3) < 1e-9
    assert rows["search"].hit_rate["summary"] is None
    assert rows["analyze"].hit_rate == {
        "bids_db": None,
        "file_text": None,
        "summary": 1.0,
        "analysis": 0.0,
        "score": None,
    }
    assert (rows["analyze"].prompt_tokens, rows["analyze"].completion_tokens) == (10, 5)


async def test_budget_counts_logged_and_pending_calls(db):
    async with db.transaction() as s:
        s.add(UsageLog(event="collector", g2b_calls=3))
    budget = DbCallBudget(db, limit=5)
    await budget.reserve()
    await budget.reserve()
    assert await budget.used_today() == 5
    budget.settle(2)
    assert await budget.used_today() == 3
