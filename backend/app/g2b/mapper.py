"""G2B 응답 항목 → BidRecord. 필드 매핑은 v1 `g2b_search.py`(61519ad)와 실제 응답 녹화본 기준.

| BidRecord | 일반공고(regular) | 사전규격(prespec) |
|---|---|---|
| bid_key | regular:{bidNtceNo} | prespec:{bfSpecRgstNo} |
| ord | bidNtceOrd | (없음) |
| title | bidNtceNm | prdctClsfcNoNm |
| org_name | dminsttNm → ntceInsttNm | orderInsttNm → rlDminsttNm |
| budget | bdgtAmt → presmptPrce | asignBdgtAmt |
| deadline_at | bidClseDt | opninRgstClseDt |
| notice_at | bidNtceDt | rgstDt → rcptDt |
| detail_url | bidNtceDtlUrl → bidNtceUrl | (없음) |
| files | ntceSpecDocUrl1~10 + ntceSpecFileNm1~10 | specDocFileUrl1~5 ("규격문서 N") |
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal

from app.g2b.models import BidFileRef, BidRecord

log = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))
# YYYYMMDD를 먼저: 반대 순서면 strptime이 8자리를 YYYYMDHM으로 읽는다
# (decisions/2026-11-11-g2b-date-parsing.md)
_FORMATS = ("%Y%m%d", "%Y%m%d%H%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")
FileKind = Literal["rfp", "spec", "other"]
_RFP_WORDS = ("제안요청", "과업지시")


def parse_kst(value: str | None) -> datetime | None:
    """G2B 날짜(KST, 4가지 형식) → UTC. 비었거나 해석 불가면 None(마감 미정)."""
    if not value or not value.strip():
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=KST).astimezone(UTC)
        except ValueError:
            continue
    log.warning("G2B 날짜 해석 실패: %r", value[:40])
    return None


def _amount(*values: Any) -> int | None:
    """첫 번째로 비어 있지 않은 금액. 숫자가 아니면 None, 0은 그대로(화면에서 '미공개')."""
    for v in values:
        if v is None or str(v).strip() == "":
            continue
        try:
            return int(float(str(v).replace(",", "")))
        except ValueError:
            return None
    return None


def _first(item: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = item.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def file_kind(name: str, source: str) -> FileKind:
    if source == "prespec":
        return "spec"
    return "rfp" if any(w in name for w in _RFP_WORDS) else "other"


def _files(source: str, item: dict[str, Any]) -> list[BidFileRef]:
    out: list[BidFileRef] = []
    if source == "regular":
        for i in range(1, 11):
            url = item.get(f"ntceSpecDocUrl{i}")
            if url:
                name = item.get(f"ntceSpecFileNm{i}") or f"첨부 {i}"
                out.append(
                    BidFileRef(url=url, name=name, kind=file_kind(name, source), origin="notice")
                )
    else:
        for i in range(1, 6):
            url = item.get(f"specDocFileUrl{i}")
            if url:
                out.append(BidFileRef(url=url, name=f"규격문서 {i}", kind="spec", origin="prespec"))
    return out


def to_record(source: str, item: dict[str, Any]) -> BidRecord:
    if source == "regular":
        no = str(item["bidNtceNo"])
        return BidRecord(
            bid_key=f"regular:{no}",
            source="regular",
            bid_no=no,
            ord=_first(item, "bidNtceOrd"),
            prespec_reg_no=_first(item, "bfSpecRgstNo"),
            title=str(item.get("bidNtceNm") or ""),
            org_name=_first(item, "dminsttNm", "ntceInsttNm"),
            budget=_amount(item.get("bdgtAmt"), item.get("presmptPrce")),
            deadline_at=parse_kst(item.get("bidClseDt")),
            notice_at=parse_kst(item.get("bidNtceDt")),
            detail_url=_first(item, "bidNtceDtlUrl", "bidNtceUrl"),
            files=_files(source, item),
            raw=item,
        )
    if source == "prespec":
        reg = str(item["bfSpecRgstNo"])
        return BidRecord(
            bid_key=f"prespec:{reg}",
            source="prespec",
            bid_no=reg,
            ord=None,
            prespec_reg_no=reg,
            title=str(item.get("prdctClsfcNoNm") or ""),
            org_name=_first(item, "orderInsttNm", "rlDminsttNm"),
            budget=_amount(item.get("asignBdgtAmt")),
            deadline_at=parse_kst(item.get("opninRgstClseDt")),
            notice_at=parse_kst(item.get("rgstDt") or item.get("rcptDt")),
            detail_url=None,
            files=_files(source, item),
            raw=item,
        )
    raise ValueError(f"알 수 없는 source: {source}")
