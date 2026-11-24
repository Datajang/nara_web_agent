"""G2B OpenAPI 클라이언트 (SPEC §5.2).

- 페이지네이션: totalCount를 채울 때까지 pageNo를 올린다 (v1은 첫 페이지만 읽었다).
- 15일 넘는 구간은 나눠 호출 (넘으면 resultCode 07). 낙찰·계약은 7일 미만 (§15.2,
  docs/decisions/2026-11-16-awards-probe.md).
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

from app.collector.windows import split_dates, split_windows

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
# 입찰공고 v1.3: 서비스·오퍼레이션 모두 02. 운영계정 트래픽은 02에만 승인된다
# (docs/decisions/2026-11-24-bid-service-02.md)
BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService02"
PRESPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
AWARD_BASE = "http://apis.data.go.kr/1230000/as/ScsbidInfoService"
CONTRACT_BASE = "http://apis.data.go.kr/1230000/ao/CntrctInfoService"
# (기본 URL, 오퍼레이션, 키워드 파라미터). 낙찰·계약은 키워드 검색을 쓰지 않는다 (§15.2)
ENDPOINTS: dict[str, tuple[str, str, str | None]] = {
    "regular": (BID_BASE, "getBidPblancListInfoServcPPSSrch02", "bidNtceNm"),
    "prespec": (PRESPEC_BASE, "getPublicPrcureThngInfoServcPPSSrch", "prdctClsfcNoNm"),
    "awards": (AWARD_BASE, "getScsbidListSttusServc", None),
    "opening_compt": (AWARD_BASE, "getOpengResultListInfoOpengCompt", None),
    "contracts": (CONTRACT_BASE, "getCntrctInfoListServc", None),
    # 개찰 결과 자동 수집(P12). 같은 오퍼레이션이지만 예산을 따로 센다(G2B_OPENINGS_DAILY_BUDGET)
    "openings": (AWARD_BASE, "getOpengResultListInfoOpengCompt", None),
}
# 낙찰정보·계약정보 서비스 소스. 키는 NARA_AWARD_API_KEY(없으면 NARA_API_KEY)
AWARD_SOURCES = frozenset({"awards", "opening_compt", "contracts"})
OPENINGS_SOURCE = "openings"  # 낙찰정보 서비스 키를 쓰지만 낙찰 몫 예산이 아니라 자기 몫으로 센다
# 번호 단건 조회: 일반 조회 + inqryDiv=2. 검색용 PPSSrch는 번호 필터를 무시한다
# (docs/decisions/2026-11-12-g2b-single-lookup.md)
LOOKUP_ENDPOINTS = {
    "regular": (BID_BASE, "getBidPblancListInfoServc02", "bidNtceNo"),
    "prespec": (PRESPEC_BASE, "getPublicPrcureThngInfoServc", "bfSpecRgstNo"),
}
MAX_SPAN = timedelta(days=15)
# 공고(v1.3)·낙찰·계약: 조회 시작일~종료일이 KST 날짜 7개를 넘으면 resultCode 07 (분 길이와 무관)
SOURCE_MAX_DATES = {"regular": 7, "awards": 7, "contracts": 7}
# 모든 페이지를 받아야 성공으로 친다(창 완결성, §15.4). 중간에 빈 페이지면 G2BIncomplete
STRICT_PAGING = frozenset({"awards", "contracts"})
# numOfRows=1000은 오류 없이 10행만 온다 (2026-11-16 probe)
MAX_PAGE_SIZE = 999
_KEY_PARAM = re.compile(r"(ServiceKey=)[^&\s'\"]+", re.IGNORECASE)


class G2BError(Exception):
    """G2B 호출 실패. '결과 0건'(빈 리스트)과 구분된다."""


class G2BBudgetExceeded(G2BError):
    """일일 호출 예산 초과 (G2B_DAILY_CALL_BUDGET)."""


class G2BCallCapReached(G2BBudgetExceeded):
    """한 요청의 호출 상한(call_cap)에 닿았다. 재시도까지 포함해 센다 (§15.4 온디맨드 6건)."""


class G2BIncomplete(G2BError):
    """창의 일부 페이지만 받았다(totalCount보다 적음). 경계를 옮기면 안 된다."""


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


@dataclass
class CallCap:
    limit: int
    used: int = 0


_cap: ContextVar[CallCap | None] = ContextVar("g2b_call_cap", default=None)


@contextlib.contextmanager
def call_cap(limit: int) -> Iterator[CallCap]:
    """이 블록 안의 G2B 호출을 limit회로 막는다(재시도 포함). 넘으면 G2BCallCapReached."""
    c = CallCap(limit)
    token = _cap.set(c)
    try:
        yield c
    finally:
        _cap.reset(token)


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
        source_budgets: Mapping[str, CallBudget] | None = None,
    ) -> None:
        self.http, self.keys, self.budget = http, keys, budget
        self.page_size = min(page_size, MAX_PAGE_SIZE)
        # 소스별 추가 예산(예: awards 하루 300회). 전체 예산과 함께 센다 (§15.4)
        self.source_budgets = dict(source_budgets or {})
        self.retry_delays, self.sleep = retry_delays, sleep
        self.calls = 0

    def mask(self, text: str) -> str:
        text = _KEY_PARAM.sub(r"\1***", text)
        for k in self.keys.values():
            if k:
                text = text.replace(k, "***")
        return text

    def settle(self, n: int, source: str | None = None) -> None:
        """usage_logs에 기록된 호출 수를 예산의 '진행 중' 카운트에서 뺀다."""
        if self.budget is not None:
            self.budget.settle(n)
        if source is not None and (sb := self.source_budgets.get(source)) is not None:
            sb.settle(n)

    async def fetch(
        self, source: str, start: datetime, end: datetime, keyword: str | None = None
    ) -> list[dict[str, Any]]:
        """[start, end) 구간 등록분 전체. 결과 0건이면 빈 리스트, 실패면 G2BError."""
        out: list[dict[str, Any]] = []
        if source in SOURCE_MAX_DATES:
            spans = split_dates(start, end, SOURCE_MAX_DATES[source])
        else:
            spans = split_windows(start, end, MAX_SPAN)
        for a, b in spans:
            out.extend(await self._fetch_span(source, a, b, keyword))
        return out

    async def lookup(self, source: str, number: str) -> list[dict[str, Any]]:
        """번호로 1회 조회. 그 번호의 행(정정 차수별)만 돌려준다. 없으면 빈 리스트."""
        base, op, field = LOOKUP_ENDPOINTS[source]
        params = {"type": "json", "inqryDiv": "2", field: number, "numOfRows": "100", "pageNo": "1"}
        body = await self._call(source, f"{base}/{op}", params)
        return [it for it in _items(body) if str(it.get(field) or "") == number]

    async def opening_results(
        self, bid_ntce_no: str, bid_ntce_ord: str, source: str = "opening_compt"
    ) -> list[dict[str, Any]]:
        """공고(차수) 하나의 개찰완료 목록(업체별 순위·투찰·점수·비고, §15.2). 모든 분류·재입찰 행.

        source: 'opening_compt'(화면 온디맨드, 낙찰 몫) 또는 'openings'(자동 수집, 자기 몫).
        """
        base, op, _ = ENDPOINTS[source]
        params = {
            "type": "json",
            "bidNtceNo": bid_ntce_no,
            "bidNtceOrd": bid_ntce_ord,
            "numOfRows": str(self.page_size),
        }
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            body = await self._call(source, f"{base}/{op}", {**params, "pageNo": str(page)})
            got, total = _items(body), int(body.get("totalCount") or 0)
            items.extend(got)
            if not got or len(items) >= total:
                return [it for it in items if str(it.get("bidNtceNo") or "") == bid_ntce_no]
            page += 1

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
        if keyword and kw_param:
            params[kw_param] = keyword
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            body = await self._call(source, f"{base}/{op}", {**params, "pageNo": str(page)})
            got, total = _items(body), int(body.get("totalCount") or 0)
            items.extend(got)
            if len(items) >= total:
                return items
            if not got:
                if source in STRICT_PAGING:
                    raise G2BIncomplete(
                        f"G2B {source} 창 일부만 받음: {len(items)}/{total}건 (페이지 {page})"
                    )
                return items
            page += 1

    async def _call(self, source: str, url: str, params: dict[str, str]) -> dict[str, Any]:
        q = {"ServiceKey": self.keys.get(source, ""), **params}
        last = ""
        for attempt in range(len(self.retry_delays) + 1):
            await self._reserve(source)
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

    async def _reserve(self, source: str) -> None:
        """요청 상한 → 소스 예산 → 전체 예산 순으로 잡는다.

        전체가 초과면 잡았던 소스 몫을 돌려준다.
        """
        cap = _cap.get()
        if cap is not None:
            if cap.used >= cap.limit:
                raise G2BCallCapReached(f"요청당 G2B 호출 상한 {cap.limit}회")
            cap.used += 1
        sb = self.source_budgets.get(source)
        if sb is not None:
            await sb.reserve()
        if self.budget is not None:
            try:
                await self.budget.reserve()
            except G2BBudgetExceeded:
                if sb is not None:
                    sb.settle(1)
                raise

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
