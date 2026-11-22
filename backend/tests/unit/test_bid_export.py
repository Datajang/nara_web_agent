"""입찰공고 목록 엑셀 (2026-11-22): 열 순서·값 규칙·수식 주입 방지·파일 이름."""

from datetime import UTC, datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

from app.bids.export import COLUMNS, export_filename, export_row, to_xlsx
from app.db.models import Bid

NOW = datetime(2026, 11, 22, 3, 0, tzinfo=UTC)  # KST 12:00


def regular(**raw: object) -> Bid:
    base: dict[str, object] = {
        "srvceDivNm": "일반용역",
        "pubPrcrmntClsfcNm": "정보시스템유지관리서비스",
        "ntceKindNm": "등록공고",
        "bidNtceOrd": "000",
        "stdNtceDocUrl": "https://www.g2b.go.kr/std/doc.hwp",
    }
    base.update(raw)
    return Bid(
        source="regular",
        bid_no="R26BK00000001",
        title="AI 민원 분석 시스템 구축",
        org_name="행정안전부",
        budget=300_000_000,
        notice_at=datetime(2026, 11, 20, 1, 0, tzinfo=UTC),
        deadline_at=NOW + timedelta(days=3),
        detail_url="https://www.g2b.go.kr/link/detail?no=R26BK00000001",
        files=[],
        raw=base,
    )


def test_columns_in_requested_order():
    assert COLUMNS == [
        "카테고리", "업무", "분류", "공고일", "공고명", "공고기관", "마감일",
        "추정가격", "입찰현황", "공고번호", "비고", "공고문", "URL",
    ]  # fmt: skip


def test_regular_row_values():
    row = export_row(regular(), NOW)
    assert row == [
        "일반공고",
        "일반용역",
        "정보시스템유지관리서비스",
        "2026-11-20 10:00",
        "AI 민원 분석 시스템 구축",
        "행정안전부",
        "2026-11-25 12:00",
        300_000_000,
        "진행중",
        "R26BK00000001-000",
        "",
        "https://www.g2b.go.kr/std/doc.hwp",
        "https://www.g2b.go.kr/link/detail?no=R26BK00000001",
    ]


def test_status_and_remark_rules():
    closed = regular(ntceKindNm="재공고")
    closed.deadline_at = NOW - timedelta(minutes=1)
    row = export_row(closed, NOW)
    assert row[8] == "마감" and row[10] == "재공고"
    changed = export_row(regular(ntceKindNm="변경공고", bidNtceOrd="002"), NOW)
    assert changed[10] == "변경공고 2차" and changed[9] == "R26BK00000001-002"
    cancelled = export_row(regular(ntceKindNm="취소공고"), NOW)
    assert cancelled[8] == "취소" and cancelled[10] == "취소공고"


def test_notice_doc_falls_back_to_first_attachment():
    b = regular(stdNtceDocUrl="")
    b.files = [{"url": "https://www.g2b.go.kr/a/1.hwp", "name": "공고서.hwp", "kind": "other"}]
    assert export_row(b, NOW)[11] == "https://www.g2b.go.kr/a/1.hwp"


def test_prespec_row():
    b = Bid(
        source="prespec",
        bid_no="R26BD00000009",
        prespec_reg_no="R26BD00000009",
        title="AI 플랫폼 구축",
        org_name="조달청",
        budget=None,
        notice_at=None,
        deadline_at=None,
        detail_url=None,
        files=[],
        raw={"bsnsDivNm": "기술용역", "specDocFileUrl1": "https://www.g2b.go.kr/spec/1.hwp"},
    )
    row = export_row(b, NOW)
    assert row[:3] == ["사전규격", "기술용역", ""]
    assert row[3] == "" and row[6] == "" and row[7] is None and row[8] == "진행중"
    assert row[9] == "R26BD00000009" and row[11] == "https://www.g2b.go.kr/spec/1.hwp"


def test_xlsx_header_values_and_no_formula_injection():
    evil = regular()
    evil.title = '=HYPERLINK("http://evil","클릭")'
    data = to_xlsx([export_row(evil, NOW)])
    ws = load_workbook(BytesIO(data)).active
    assert ws is not None
    assert [c.value for c in ws[1]] == COLUMNS
    title = ws.cell(row=2, column=5)
    assert title.value == evil.title and title.data_type == "s"
    assert ws.cell(row=2, column=8).value == 300_000_000
    assert ws.cell(row=2, column=13).hyperlink is not None
    assert ws.freeze_panes == "A2"


def test_filename_uses_kst_today():
    late = datetime(2026, 11, 22, 16, 0, tzinfo=UTC)  # KST 11-23 01:00
    assert export_filename(late) == "2026-11-23_입찰공고 목록.xlsx"
