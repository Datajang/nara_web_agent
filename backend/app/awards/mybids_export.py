"""투찰 결과 엑셀 (2026-11-25, docs/superpowers/specs/2026-11-25-my-bids-export-design.md).

화면 조건 그대로의 목록을 '요약' + 연도별 시트(낙찰 등록일 KST, 최근 연도부터)로 만든다.
시트 안은 개찰일 최신순(없으면 등록일). 글자 칸은 수식으로 해석되지 않게 문자열 형식으로 쓴다.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

if TYPE_CHECKING:
    from app.api.schemas.mybids import MyBidOut

KST = ZoneInfo("Asia/Seoul")
COLUMNS = [
    "개찰일", "결과", "사업명", "수요기관", "우리 순위", "유효 업체 수", "우리 투찰금액",
    "투찰률(%)", "낙찰 업체", "낙찰금액", "낙찰가와 차이", "공동수급", "비고", "공고번호",
]  # fmt: skip
_WIDTHS = [11, 8, 50, 24, 9, 11, 15, 10, 24, 15, 15, 13, 24, 20]
SUMMARY_COLUMNS = ["연도", "투찰", "낙찰", "탈락", "낙찰률(%)", "우리 낙찰 금액(지분 반영)"]
_SUMMARY_WIDTHS = [10, 8, 8, 8, 11, 26]
_MONEY = "#,##0"
_DIFF = "+#,##0;-#,##0;0"
_RESULT = {"won": "낙찰", "lost": "탈락", "disqualified": "부적격"}
_FILTER = {"all": "전체", "won": "낙찰", "lost": "탈락"}
_WON_FILL = PatternFill("solid", fgColor="E6F4EA")
_TITLE_COL, _MONEY_COLS, _LINK_COL = 3, {7, 10}, 14


def _year(b: MyBidOut) -> int:
    return b.registered_at.astimezone(KST).year


def _pct(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _joint(b: MyBidOut) -> str | None:
    if b.our_role is None:
        return None
    label = "구성원" if b.our_role == "member" else "대표"
    return f"{label} {_pct(b.our_share)}%" if b.our_share is not None else label


def _our_amount(b: MyBidOut) -> int:
    """낙찰 건의 우리 몫(공동수급이면 지분만큼)."""
    if b.result != "won" or b.award_amount is None:
        return 0
    if b.our_share is None:
        return b.award_amount
    return round(b.award_amount * b.our_share / 100)


def _notice_no(b: MyBidOut) -> str:
    return f"{b.bid_ntce_no}-{b.bid_ntce_ord}" if b.bid_ntce_ord else b.bid_ntce_no


def _link(b: MyBidOut, origin: str) -> str:
    parts = (b.bid_ntce_no, b.bid_ntce_ord, b.bid_clsfc_no, b.rbid_no)
    return f"{origin.rstrip('/')}/my-awards/bids/" + "/".join(quote(p, safe="") for p in parts)


def _row(b: MyBidOut) -> list[Any]:
    member = b.our_role == "member"
    opened = b.opened_at.astimezone(KST).replace(tzinfo=None) if b.opened_at else None
    if b.result == "won" and not member:
        winner = "우리 회사"
    else:
        winner = b.winner_name or b.winner_bizno or ""
    diff = None
    if b.result != "won" and b.our_bid_amount is not None and b.award_amount is not None:
        diff = b.our_bid_amount - b.award_amount
    return [
        opened,
        _RESULT[b.result],
        b.title,
        b.dminstt_name or "",
        None if member else b.our_rank,
        None if member else b.valid_count,
        None if member else b.our_bid_amount,
        None if member else b.our_bid_rate,
        winner,
        b.award_amount,
        diff,
        _joint(b),
        b.remark,
        _notice_no(b),
    ]


def _put(ws: Worksheet, r: int, c: int, value: Any) -> Any:
    cell = ws.cell(row=r, column=c)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"  # 수식 주입 방지: '='로 시작해도 글자 그대로
    return cell


def _header(ws: Worksheet, names: Sequence[str], widths: Sequence[int]) -> None:
    for c, name in enumerate(names, start=1):
        _put(ws, 1, c, name).font = Font(bold=True)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _year_sheet(ws: Worksheet, items: list[MyBidOut], origin: str) -> None:
    _header(ws, COLUMNS, _WIDTHS)
    items = sorted(items, key=lambda b: b.opened_at or b.registered_at, reverse=True)
    for r, b in enumerate(items, start=2):
        for c, value in enumerate(_row(b), start=1):
            cell = _put(ws, r, c, value)
            if c == 1 and value is not None:
                cell.number_format = "yyyy-mm-dd"
            elif c in _MONEY_COLS:
                cell.number_format = _MONEY
            elif c == 11:
                cell.number_format = _DIFF
            elif c == _TITLE_COL:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        if b.result == "won":
            ws.cell(row=r, column=2).fill = _WON_FILL
        if origin.startswith(("http://", "https://")):
            link = ws.cell(row=r, column=_LINK_COL)
            link.hyperlink = _link(b, origin)
            link.style = "Hyperlink"
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = ws.dimensions


def _stats(items: Sequence[MyBidOut]) -> list[Any]:
    won = sum(1 for b in items if b.result == "won")
    rate = round(won / len(items) * 100, 1) if items else 0.0
    return [len(items), won, len(items) - won, rate, sum(_our_amount(b) for b in items)]


def _summary(
    ws: Worksheet,
    by_year: dict[int, list[MyBidOut]],
    scan_done: int,
    cond: str,
    now: datetime,
) -> None:
    _header(ws, SUMMARY_COLUMNS, _SUMMARY_WIDTHS)
    years = sorted(by_year, reverse=True)
    rows: list[list[Any]] = [[y, *_stats(by_year[y])] for y in years]
    if rows:
        rows.append(["합계", *_stats([b for y in years for b in by_year[y]])])
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            cell = _put(ws, r, c, value)
            if c == 6:
                cell.number_format = _MONEY
        if row[0] == "합계":
            for c in range(1, 7):
                ws.cell(row=r, column=c).font = Font(bold=True)
    notes = [
        f"조건: {cond}",
        f"만든 날짜: {now.astimezone(KST):%Y-%m-%d %H:%M}",
        f"탈락은 개찰 결과를 받은 공고만 나와요(받은 공고 {scan_done:,}건 기준).",
        "낙찰률 = 낙찰 ÷ 투찰. 공동수급은 우리 지분만큼 금액에 넣어요.",
    ]
    for i, note in enumerate(notes, start=len(rows) + 3):
        _put(ws, i, 1, note)


def build_xlsx(
    items: Sequence[MyBidOut], scan_done: int, cond: str, now: datetime, origin: str
) -> bytes:
    by_year: dict[int, list[MyBidOut]] = defaultdict(list)
    for b in items:
        by_year[_year(b)].append(b)
    wb = Workbook()
    summary = wb.active
    assert summary is not None
    summary.title = "요약"
    _summary(summary, by_year, scan_done, cond, now)
    for y in sorted(by_year, reverse=True):
        _year_sheet(wb.create_sheet(str(y)), by_year[y], origin)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def describe(result: str, date_from: date | None, date_to: date | None, q: str | None) -> str:
    """요약 시트에 적을 화면 조건 한 줄."""
    out = [f"결과 {_FILTER.get(result, result)}"]
    if date_from or date_to:
        out.append(f"기간 {date_from or ''}~{date_to or ''}")
    if q:
        out.append(f"사업명 '{q}'")
    return " · ".join(out)


def export_filename(now: datetime) -> str:
    return f"{now.astimezone(KST):%Y-%m-%d}_투찰 결과.xlsx"
