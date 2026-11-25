"""투찰 결과 엑셀 (2026-11-25, docs/superpowers/specs/2026-11-25-my-bids-export-design.md).

순수 함수라 DB 없이 본다: 요약 + 연도별 시트, 14열, 구성원 낙찰, 수식 주입 방지.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from io import BytesIO

from openpyxl import load_workbook

from app.api.schemas.mybids import MyBidOut
from app.awards.mybids_export import COLUMNS, build_xlsx, describe, export_filename

UTC = UTC
NOW = datetime(2026, 11, 25, 3, 0, tzinfo=UTC)
ORIGIN = "https://nara.example"


def _b(no: str, reg: datetime, result: str = "lost", **kw) -> MyBidOut:
    base = dict(
        bid_ntce_no=no,
        bid_ntce_ord="000",
        bid_clsfc_no="0",
        rbid_no="000",
        title=f"{no} 용역",
        dminstt_name="행정안전부",
        registered_at=reg,
        opened_at=reg,
        result=result,
        our_rank=2,
        valid_count=5,
        participant_count=6,
        our_bid_amount=105_000_000,
        our_bid_rate=88.123,
        our_total_score=None,
        remark=None,
        winner_bizno="2345678901",
        winner_name="(주)가온",
        award_amount=100_000_000,
        fetched=True,
        bid_id=None,
    )
    base.update(kw)
    return MyBidOut(**base)  # type: ignore[arg-type]


def _wb(items, scan_done=10, cond="결과 전체"):
    return load_workbook(BytesIO(build_xlsx(items, scan_done, cond, NOW, ORIGIN)))


def _rows(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def test_sheets_are_summary_then_years_desc_by_registered_kst():
    """연도는 낙찰 등록일 KST 기준: 2025-12-31 15:00Z는 2026년."""
    items = [
        _b("A", datetime(2024, 5, 1, tzinfo=UTC)),
        _b("B", datetime(2025, 12, 31, 15, 0, tzinfo=UTC)),
        _b("C", datetime(2025, 6, 1, tzinfo=UTC), result="won", winner_bizno="us"),
    ]
    wb = _wb(items)
    assert wb.sheetnames == ["요약", "2026", "2025", "2024"]
    assert [r[13] for r in _rows(wb["2026"])[1:]] == ["B-000"]
    assert _rows(wb["2025"])[0] == COLUMNS


def test_columns_and_values_for_lost_row():
    reg = datetime(2026, 3, 12, 1, 0, tzinfo=UTC)
    ws = _wb([_b("R1", reg, remark="낙찰하한선 미달")])["2026"]
    head, row = _rows(ws)[:2]
    assert len(head) == 14 and head[0] == "개찰일" and head[13] == "공고번호"
    assert row[0].date() == date(2026, 3, 12)
    assert row[1:5] == ["탈락", "R1 용역", "행정안전부", 2]
    assert row[5:8] == [5, 105_000_000, 88.123]
    assert row[8:11] == ["(주)가온", 100_000_000, 5_000_000]  # 낙찰가와 차이 = 우리 − 낙찰
    assert row[11] is None and row[12] == "낙찰하한선 미달"
    link = ws.cell(row=2, column=14).hyperlink
    assert link is not None and link.target == f"{ORIGIN}/my-awards/bids/R1/000/0/000"
    assert ws.cell(row=2, column=7).number_format == "#,##0"
    assert ws.freeze_panes == "D2" and ws.auto_filter.ref


def test_won_lead_says_us_and_no_diff():
    ws = _wb([_b("W", datetime(2026, 1, 5, tzinfo=UTC), result="won", our_rank=1)])["2026"]
    row = _rows(ws)[1]
    assert row[1] == "낙찰" and row[8] == "우리 회사" and row[10] is None
    assert ws.cell(row=2, column=2).fill.fgColor.rgb.endswith("E6F4EA")


def test_joint_member_row_blanks_our_bid_and_shows_lead():
    m = _b(
        "J",
        datetime(2026, 2, 1, tzinfo=UTC),
        result="won",
        our_role="member",
        our_share=25.0,
        our_rank=None,
        valid_count=None,
        our_bid_amount=None,
        our_bid_rate=None,
        winner_name="(주)대표사",
    )
    lead = _b("L", datetime(2026, 2, 2, tzinfo=UTC), result="won", our_role="lead", our_share=60.0)
    wb = _wb([m, lead])
    rows = {r[13]: r for r in _rows(wb["2026"])[1:]}
    assert rows["J-000"][4:8] == [None, None, None, None]
    assert rows["J-000"][8] == "(주)대표사" and rows["J-000"][11] == "구성원 25%"
    assert rows["L-000"][11] == "대표 60%"
    summary = _rows(wb["요약"])
    # 연도 · 투찰 · 낙찰 · 탈락 · 낙찰률 · 우리 낙찰 금액(지분 반영): 25% + 60% of 1억
    assert summary[1] == [2026, 2, 2, 0, 100.0, 85_000_000]


def test_summary_counts_rate_and_notes():
    items = [
        _b("A", datetime(2026, 4, 1, tzinfo=UTC), result="won", award_amount=50_000_000),
        _b("B", datetime(2026, 4, 2, tzinfo=UTC)),
        _b("C", datetime(2026, 4, 3, tzinfo=UTC), result="disqualified", our_rank=None),
        _b("D", datetime(2025, 4, 3, tzinfo=UTC)),
    ]
    rows = _rows(_wb(items, scan_done=1234, cond="결과 전체 · 사업명 'AI'")["요약"])
    assert rows[0] == ["연도", "투찰", "낙찰", "탈락", "낙찰률(%)", "우리 낙찰 금액(지분 반영)"]
    assert rows[1] == [2026, 3, 1, 2, 33.3, 50_000_000]
    assert rows[2] == [2025, 1, 0, 1, 0.0, 0]
    assert rows[3] == ["합계", 4, 1, 3, 25.0, 50_000_000]
    notes = [r[0] for r in rows[4:] if r[0]]
    assert "조건: 결과 전체 · 사업명 'AI'" in notes
    assert "만든 날짜: 2026-11-25 12:00" in notes
    assert any("받은 공고 1,234건" in n for n in notes)


def test_empty_list_has_summary_only():
    wb = _wb([])
    assert wb.sheetnames == ["요약"]


def test_formula_like_title_stays_text():
    ws = _wb([_b("F", datetime(2026, 1, 1, tzinfo=UTC), title="=HYPERLINK(1)")])["2026"]
    cell = ws.cell(row=2, column=3)
    assert cell.value == "=HYPERLINK(1)" and cell.data_type == "s"


def test_describe_and_filename():
    assert describe("all", None, None, None) == "결과 전체"
    assert (
        describe("lost", date(2026, 1, 1), date(2026, 12, 31), "AI")
        == "결과 탈락 · 기간 2026-01-01~2026-12-31 · 사업명 'AI'"
    )
    assert describe("won", date(2026, 1, 1), None, None) == "결과 낙찰 · 기간 2026-01-01~"
    assert export_filename(datetime(2026, 11, 24, 16, 0, tzinfo=UTC)) == "2026-11-25_투찰 결과.xlsx"
