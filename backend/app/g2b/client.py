"""G2B OpenAPI 클라이언트 (SPEC §5.2).

- 페이지네이션: totalCount를 채울 때까지 pageNo를 올린다 (v1은 첫 페이지만 읽었다).
- 15일 넘는 구간은 나눠 호출 (넘으면 resultCode 07).
- 재시도: 네트워크 오류·5xx·타임아웃만 1·2·4초 백오프로 최대 3회. 4xx·비정상 resultCode는 즉시
  G2BError.
- 예외를 삼키지 않는다. 서비스키는 예외·로그에서 마스킹한다 (규칙 4).
- 호출 수는 ContextVar로 작업 단위로 센다 (usage_logs.g2b_calls 귀속).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
PRESPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
ENDPOINTS = {
    "regular": (BID_BASE, "getBidPblancListInfoServcPPSSrch", "bidNtceNm"),
    "prespec": (PRESPEC_BASE, "getPublicPrcureThngInfoServcPPSSrch", "prdctClsfcNoNm"),
}
MAX_SPAN = timedelta(days=15)
_KEY_PARAM = re.compile(r"(ServiceKey=)[^&\s'\"]+", re.IGNORECASE)


class G2BError(Exception):
    """G2B 호출 실패. '결과 0건'(빈 리스트)과 구분된다."""


class G2BBudgetExceeded(G2BError):
    """일일 호출 예산 초과 (G2B_DAILY_CALL_BUDGET)."""


class CallBudget(Protocol):
    async def reserve(self) -> None: ...

    def settle(self, n: int) -> None: ...


@dataclass
class CallCounter:
    value: int = 0
    parent: CallCounter | None = None

    def add(self) -> None:
        """중첩된 셈(검색 → fill → 수집)에서 바깥 카운터에도 더한다."""
        c: CallCounter | None = self
        while c is not None:
            c.value += 1
            c = c.parent


_counter: ContextVar[CallCounter | None] = ContextVar("g2b_call_counter", default=None)


@contextlib.contextmanager
def count_calls() -> Iterator[CallCounter]:
    """이 블록 안에서 일어난 G2B 호출 수를 센다 (자식 태스크 포함)."""
    c = CallCounter(parent=_counter.get())
    token = _counter.set(c)
    try:
        yield c
    finally:
        _counter.reset(token)


class G2BClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        keys: Mapping[str, str],
        *,
        page_size: int = 999,
        budget: CallBudget | None = None,
        retry_delays: Sequence[float] = (1, 2, 4),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.http, self.keys, self.page_size, self.budget = http, keys, page_size, budget
        self.retry_delays, self.sleep = retry_delays, sleep
        self.calls = 0

    def mask(self, text: str) -> str:
        text = _KEY_PARAM.sub(r"\1***", text)
        for k in self.keys.values():
            if k:
                text = text.replace(k, "***")
        return text

    def settle(self, n: int) -> None:
        """usage_logs에 기록된 호출 수를 예산의 '진행 중' 카운트에서 뺀다."""
        if self.budget is not None:
            self.budget.settle(n)

    async def fetch(
        self, source: str, start: datetime, end: datetime, keyword: str | None = None
    ) -> list[dict[str, Any]]:
        """[start, end) 구간 등록분 전체. 결과 0건이면 빈 리스트, 실패면 G2BError."""
        out: list[dict[str, Any]] = []
        cur = start
        while cur < end:
            nxt = min(cur + MAX_SPAN, end)
            out.extend(await self._fetch_span(source, cur, nxt, keyword))
            cur = nxt
        return out

    async def _fetch_span(
        self, source: str, start: datetime, end: datetime, keyword: str | None
    ) -> list[dict[str, Any]]:
        base, op, kw_param = ENDPOINTS[source]
        params: dict[str, str] = {
            "type": "json",
            "inqryDiv": "1",
            "inqryBgnDt": start.astimezone(KST).strftime("%Y%m%d%H%M"),
            # 끝은 배타적: 마지막 분까지 포함하도록 1분 뺀다
            "inqryEndDt": (end - timedelta(minutes=1)).astimezone(KST).strftime("%Y%m%d%H%M"),
            "numOfRows": str(self.page_size),
        }
        if keyword:
            params[kw_param] = keyword
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            body = await self._call(source, f"{base}/{op}", {**params, "pageNo": str(page)})
            got, total = _items(body), int(body.get("totalCount") or 0)
            items.extend(got)
            if not got or len(items) >= total:
                return items
            page += 1

    async def _call(self, source: str, url: str, params: dict[str, str]) -> dict[str, Any]:
        q = {"ServiceKey": self.keys.get(source, ""), **params}
        last = ""
        for attempt in range(len(self.retry_delays) + 1):
            if self.budget is not None:
                await self.budget.reserve()
            self.calls += 1
            if (c := _counter.get()) is not None:
                c.add()
            try:
                resp = await self.http.get(url, params=q, timeout=httpx.Timeout(30.0, connect=5.0))
            except httpx.TransportError as e:
                last = self.mask(f"{type(e).__name__}: {e}")
            else:
                if resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                else:
                    return self._parse(resp)
            if attempt < len(self.retry_delays):
                log.warning("G2B %s 재시도 %d: %s", source, attempt + 1, last)
                await self.sleep(self.retry_delays[attempt])
        raise G2BError(f"G2B {source} 호출 실패(재시도 {len(self.retry_delays)}회 후): {last}")

    def _parse(self, resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError as e:
            raise G2BError(
                f"G2B 응답이 JSON이 아님 (HTTP {resp.status_code}): {self.mask(resp.text[:200])}"
            ) from e
        if not isinstance(data, dict):
            raise G2BError("G2B 응답 형식 오류")
        if "response" in data:
            header = data["response"].get("header") or {}
            if header.get("resultCode") != "00":
                raise G2BError(f"G2B 오류 {header.get('resultCode')}: {header.get('resultMsg')}")
            return data["response"].get("body") or {}
        # 실제 오류 형태 2종 (docs/decisions/2026-11-11-g2b-probe.md)
        if err := data.get("nkoneps.com.response.ResponseError"):
            h = err.get("header") or {}
            raise G2BError(f"G2B 오류 {h.get('resultCode')}: {h.get('resultMsg')}")
        if err := data.get("OpenAPI_ServiceResponse"):
            h = err.get("cmmMsgHeader") or {}
            raise G2BError(f"G2B 인증 오류 {h.get('returnReasonCode')}: {h.get('errMsg')}")
        raise G2BError(f"G2B 알 수 없는 응답 (HTTP {resp.status_code})")


def _items(body: dict[str, Any]) -> list[dict[str, Any]]:
    """items의 세 가지 모양(list, {"item": ...}, "null"/빈값)을 목록으로."""
    items = body.get("items")
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        raw = items.get("item") or []
        return raw if isinstance(raw, list) else [raw]
    return []
