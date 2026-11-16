"""낙찰 응답 항목 → 저장할 행. 화이트리스트 필드만 읽는다 (SPEC §15.4·§15.9).

저장하지 않는 필드(개인정보): bidwinnrCeoNm, bidwinnrAdrs, bidwinnrTelNo, fnlSucsfCorpOfcl.
필드 사실은 docs/decisions/2026-11-16-awards-probe.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.g2b.mapper import parse_kst

# 매퍼가 읽는 응답 필드 전부. 이 밖의 필드는 어디에도 남지 않는다
AWARD_FIELDS = frozenset(
    {
        "bidNtceNo",
        "bidNtceOrd",
        "bidClsfcNo",
        "rbidNo",
        "bidNtceNm",
        "prtcptCnum",
        "bidwinnrNm",
        "bidwinnrBizno",
        "sucsfbidAmt",
        "sucsfbidRate",
        "rlOpengDt",
        "dminsttCd",
        "dminsttNm",
        "rgstDt",
        "fnlSucsfDate",
    }
)
_LEGAL_FORMS = re.compile(
    r"주식회사|유한회사|유한책임회사|합자회사|합명회사|사단법인|재단법인|협동조합"
)
_ABBR = re.compile(r"\((주|유|사|재|합)\)|㈜|㈔|㈕")
_NON_WORD = re.compile(r"[^0-9a-z가-힣]")


@dataclass
class AwardRow:
    bid_ntce_no: str
    bid_ntce_ord: str
    bid_clsfc_no: str
    rbid_no: str
    bizno: str | None
    winner_name: str | None
    title: str
    award_amount: int | None
    g2b_award_rate: Decimal | None
    participant_count: int | None
    dminstt_cd: str | None
    dminstt_name: str | None
    opened_at: datetime | None
    awarded_on: date | None
    registered_at: datetime
    fields: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.bid_ntce_no, self.bid_ntce_ord, self.bid_clsfc_no, self.rbid_no)

    @property
    def seen_at(self) -> datetime:
        """업체의 first/last_seen 기준 시각: 개찰, 없으면 등록."""
        return self.opened_at or self.registered_at


def normalize_bizno(value: Any) -> str | None:
    """숫자만 남겨 10자리면 사업자번호, 아니면 None('식별 불가')."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits if len(digits) == 10 else None


def normalize_name(name: str) -> str:
    """검색용 업체명: 법인 형태 표기·공백·기호를 빼고 소문자로 (§15.6 업체명 일부 검색)."""
    s = _ABBR.sub("", name)
    s = _LEGAL_FORMS.sub("", s)
    return _NON_WORD.sub("", s.lower())


def _text(item: dict[str, Any], key: str) -> str | None:
    v = item.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(value: Any) -> int | None:
    s = str(value or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return int(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    s = str(value or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _date(value: Any) -> date | None:
    s = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def to_award(item: dict[str, Any]) -> AwardRow | None:
    """공고번호나 등록일시가 없으면 None(저장 불가 행)."""
    no = _text(item, "bidNtceNo")
    registered_at = parse_kst(_text(item, "rgstDt"))
    if not no or registered_at is None:
        return None
    return AwardRow(
        bid_ntce_no=no,
        bid_ntce_ord=_text(item, "bidNtceOrd") or "000",
        bid_clsfc_no=_text(item, "bidClsfcNo") or "0",
        rbid_no=_text(item, "rbidNo") or "000",
        bizno=normalize_bizno(item.get("bidwinnrBizno")),
        winner_name=_text(item, "bidwinnrNm"),
        title=_text(item, "bidNtceNm") or "",
        award_amount=_int(item.get("sucsfbidAmt")),
        g2b_award_rate=_decimal(item.get("sucsfbidRate")),
        participant_count=_int(item.get("prtcptCnum")),
        dminstt_cd=_text(item, "dminsttCd"),
        dminstt_name=_text(item, "dminsttNm"),
        opened_at=parse_kst(_text(item, "rlOpengDt")),
        awarded_on=_date(item.get("fnlSucsfDate")),
        registered_at=registered_at,
    )
