"""관리자용 사용량 집계 (SPEC §5.8): 일별 요청 수, 계층별 캐시 적중률, G2B 호출, LLM 토큰."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, Float, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import Label

from app.db.models import UsageLog

LAYERS = ("bids_db", "file_text", "summary", "analysis", "score")


@dataclass
class DailyUsage:
    day: date
    event: str
    requests: int
    g2b_calls: int
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    hit_rate: dict[str, float | None]


async def daily_usage(session: AsyncSession, since: datetime) -> list[DailyUsage]:
    day = cast(func.timezone("Asia/Seoul", UsageLog.created_at), Date).label("day")

    def rate(layer: str) -> Label[Any]:
        flag = UsageLog.cache[layer].astext
        hits = func.count().filter(flag == "true")
        seen = func.count().filter(flag.is_not(None))
        return (cast(hits, Float) / func.nullif(seen, 0)).label(layer)

    stmt = (
        select(
            day,
            UsageLog.event,
            func.count().label("requests"),
            func.sum(UsageLog.g2b_calls),
            func.sum(UsageLog.llm_calls),
            func.sum(UsageLog.prompt_tokens),
            func.sum(UsageLog.completion_tokens),
            *(rate(layer) for layer in LAYERS),
        )
        .where(UsageLog.created_at >= since)
        .group_by(day, UsageLog.event)
        .order_by(day, UsageLog.event)
    )
    out = []
    for row in (await session.execute(stmt)).all():
        d, event, req, g2b, llm, p_tok, c_tok, *rates = row
        out.append(
            DailyUsage(
                d,
                event,
                req,
                int(g2b or 0),
                int(llm or 0),
                int(p_tok or 0),
                int(c_tok or 0),
                dict(zip(LAYERS, rates, strict=True)),
            )
        )
    return out
