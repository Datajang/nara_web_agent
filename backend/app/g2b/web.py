"""나라장터 웹 공고 상세의 제안서평가 일시 (2026-11-27).

결정 기록 docs/decisions/2026-11-27-proposal-eval-date.md.

Open API에는 평가 일시가 없다. 웹 공고 상세(PNPE027_01) '입찰진행정보'가 부르는
`selectItemAnncMngV.do`(POST JSON, 로그인·쿠키 없음)에서 읽는다. 웹 화면용 내부 주소라
예고 없이 바뀔 수 있으므로 이상한 응답은 G2BWebError로 올리고, 부르는 쪽은 날짜 없음처럼 다룬다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.g2b.mapper import KST

EVAL_URL = "https://www.g2b.go.kr/pn/pnp/pnpe/ItemBidPbac/selectItemAnncMngV.do"
# 웹 화면은 HTML5 브라우저가 아니면 안내 페이지를 준다
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
TIMEOUT = 15.0
EVAL_SUBJECT = "제안서평가"


class G2BWebError(Exception):
    """웹 응답이 예상과 다름(상태 코드·JSON 아님·ErrorCode≠0)."""


@dataclass(frozen=True)
class EvalPlan:
    at: datetime | None  # 제안서평가 시작(UTC). 수요기관 자체 평가는 대개 비어 있다
    host: str | None  # 평가 주관(조달청·수요기관)


class EvalDateSource(Protocol):
    async def eval_date(self, bid_no: str, ord_: str) -> EvalPlan: ...


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=KST).astimezone(UTC)
        except ValueError:
            continue
    return None


def parse_eval(body: dict[str, Any]) -> EvalPlan:
    step = body.get("dmEvlStepMap") or {}
    at = _parse(step.get("evlDt"))
    if at is None:  # 평가 단계 맵이 비면 입찰진행정보 표의 '제안서평가' 행
        rows = body.get("dmItemList1") or []
        row = next((r for r in rows if r.get("subject") == EVAL_SUBJECT), None) or {}
        at = _parse(row.get("startDt"))
    host = step.get("evlMaagSeNm")
    return EvalPlan(at=at, host=str(host) if host else None)


class G2BWebClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def eval_date(self, bid_no: str, ord_: str) -> EvalPlan:
        body = {"dmItemMap": {"bidPbancNo": bid_no, "bidPbancOrd": ord_}}
        try:
            r = await self._http.post(
                EVAL_URL, json=body, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            )
        except httpx.HTTPError as e:
            raise G2BWebError(type(e).__name__) from e
        if r.status_code != 200:
            raise G2BWebError(f"http {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise G2BWebError("JSON 아님") from e
        if not isinstance(data, dict) or str(data.get("ErrorCode")) != "0":
            msg = data.get("ErrorMsg") if isinstance(data, dict) else None
            raise G2BWebError(f"ErrorCode {msg}")
        return parse_eval(data)
