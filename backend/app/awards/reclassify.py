"""낙찰 분야 태그(fields)와 추정가격·비율 다시 계산 (SPEC §15.3). G2B를 부르지 않는다(DB만).

org_settings.field_keywords가 바뀌면 PUT /admin/company가 백그라운드로, 또는
scripts/reclassify_awards.py로 실행한다. 같은 사전이면 몇 번 돌려도 결과가 같다.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, update

from app.awards.fields import classify, clean_keywords
from app.awards.store import award_ratio, estimated_prices
from app.db.models import BidAward, OrgSettings
from app.db.session import Database


@dataclass
class ReclassifyResult:
    scanned: int = 0
    fields_changed: int = 0
    prices_changed: int = 0


async def reclassify(db: Database, batch: int = 2000) -> ReclassifyResult:
    res = ReclassifyResult()
    async with db.session() as s:
        row = await s.get(OrgSettings, 1)
    keywords = clean_keywords(row.field_keywords if row else None)
    last_id = 0
    while True:
        async with db.transaction() as s:
            rows = (
                await s.execute(
                    select(
                        BidAward.id,
                        BidAward.bid_ntce_no,
                        BidAward.title,
                        BidAward.fields,
                        BidAward.award_amount,
                        BidAward.estimated_price,
                        BidAward.award_ratio,
                    )
                    .where(BidAward.id > last_id)
                    .order_by(BidAward.id)
                    .limit(batch)
                )
            ).all()
            if not rows:
                return res
            prices = await estimated_prices(s, (r.bid_ntce_no for r in rows))
            for r in rows:
                values: dict[str, object] = {}
                fields = classify(r.title, keywords)
                if fields != list(r.fields or []):
                    values["fields"] = fields
                    res.fields_changed += 1
                est = prices.get(r.bid_ntce_no)
                ratio = award_ratio(r.award_amount, est)
                if est != r.estimated_price or ratio != r.award_ratio:
                    values.update(estimated_price=est, award_ratio=ratio)
                    res.prices_changed += 1
                if values:
                    await s.execute(update(BidAward).where(BidAward.id == r.id).values(**values))
            res.scanned += len(rows)
            last_id = rows[-1].id
