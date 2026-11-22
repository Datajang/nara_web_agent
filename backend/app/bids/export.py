"""입찰공고 목록 엑셀 (2026-11-22, docs/decisions/2026-11-22-bid-export.md).

화면에 보이는 공고(최대 500건 = 검색 상한)를 사용자가 정한 13열로 내려준다.
수집 공고는 모두 용역이라 카테고리=공고 구분(일반공고/사전규격), 업무=용역 구분, 분류=공공조달분류.
문자열은 수식으로 해석되지 않게 문자열 형식으로 쓴다(=, +, -, @로 시작하는 공고명 대비).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.bids.cards import is_cancelled
from app.db.models import Bid

KST = ZoneInfo("Asia/Seoul")
COLUMNS = [
    "카테고리", "업무", "분류", "공고일", "공고명", "공고기관", "마감일",
    "추정가격", "입찰현황", "공고번호", "비고", "공고문", "URL",
]  # fmt: skip
_WIDTHS = [10, 10, 24, 17, 60, 28, 17, 15, 9, 20, 16, 40, 40]
_URL_COLS = {12, 13}  # 1부터: 공고문, URL
_MONEY_COL = 8
_PLAIN_KIND = "등록공고"


def _kst(dt: datetime | None) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M") if dt else ""


def _text(raw: dict[str, Any], key: str) -> str:
    v = raw.get(key)
    return str(v).strip() if v is not None else ""


def _status(b: Bid, now: datetime) -> str:
    if is_cancelled(b):
        return "취소"
    if b.deadline_at is not None and b.deadline_at <= now:
        return "마감"
    return "진행중"


def _remark(raw: dict[str, Any]) -> str:
    """공고 종류(등록공고는 생략)와 변경 차수."""
    kind = _text(raw, "ntceKindNm")
    if not kind or kind == _PLAIN_KIND:
        return ""
    ord_ = _text(raw, "bidNtceOrd")
    n = int(ord_) if ord_.isdigit() else 0
    return f"{kind} {n}차" if n > 0 else kind


def _notice_doc(b: Bid, raw: dict[str, Any]) -> str:
    if b.source == "prespec":
        return _text(raw, "specDocFileUrl1")
    url = _text(raw, "stdNtceDocUrl")
    if url:
        return url
    for f in b.files or []:
        if isinstance(f, dict) and f.get("url"):
            return str(f["url"])
    return ""


def _bid_number(b: Bid, raw: dict[str, Any]) -> str:
    if b.source == "prespec":
        return b.prespec_reg_no or b.bid_no
    ord_ = _text(raw, "bidNtceOrd")
    return f"{b.bid_no}-{ord_}" if ord_ else b.bid_no


def export_row(b: Bid, now: datetime) -> list[Any]:
    raw: dict[str, Any] = b.raw if isinstance(b.raw, dict) else {}
    regular = b.source == "regular"
    return [
        "일반공고" if regular else "사전규격",
        _text(raw, "srvceDivNm" if regular else "bsnsDivNm"),
        _text(raw, "pubPrcrmntClsfcNm") if regular else "",
        _kst(b.notice_at),
        b.title,
        b.org_name or "",
        _kst(b.deadline_at),
        b.budget,
        _status(b, now),
        _bid_number(b, raw),
        _remark(raw),
        _notice_doc(b, raw),
        b.detail_url or "",
    ]


def to_xlsx(rows: list[list[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "입찰공고 목록"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r, row in enumerate(rows, start=2):
        for col, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=col)
            if isinstance(value, str):
                cell.value = value
                cell.data_type = "s"  # 수식 주입 방지: '='로 시작해도 글자 그대로
                if col in _URL_COLS and value.startswith("https://"):
                    cell.hyperlink = value
                    cell.style = "Hyperlink"
            else:
                cell.value = value
                if col == _MONEY_COL and value is not None:
                    cell.number_format = "#,##0"
    for i, w in enumerate(_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_filename(now: datetime) -> str:
    return f"{now.astimezone(KST):%Y-%m-%d}_입찰공고 목록.xlsx"
