"""나라장터 웹 공고 상세(제안서평가 일시)의 가짜. 공고번호마다 돌려줄 값이나 예외를 정해 둔다."""

from __future__ import annotations

from app.g2b.web import EvalPlan


class FakeG2BWeb:
    def __init__(self) -> None:
        self.plans: dict[str, EvalPlan | Exception] = {}
        self.calls: list[tuple[str, str]] = []

    async def eval_date(self, bid_no: str, ord_: str) -> EvalPlan:
        self.calls.append((bid_no, ord_))
        got = self.plans.get(bid_no, EvalPlan(at=None, host=None))
        if isinstance(got, Exception):
            raise got
        return got
