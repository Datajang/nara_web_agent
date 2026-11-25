"""마감 공고 사유 판정 (2026-11-26, docs/superpowers/specs/2026-11-26-closed-bid-reason-design.md).

순수 함수 decide: 공고 + 그 공고의 낙찰 행 + 개찰 상태 행 → 배지 하나(진행 중·취소면 None).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bids.outcome import decide, failed_reason
from app.db.models import Bid, BidAward, BidOpeningStatus

NOW = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
NO = "R26BK00000001"


def _bid(source="regular", deadline=NOW - timedelta(days=1), **raw) -> Bid:
    base = {"bidNtceOrd": "000", "opengDt": "2026-11-25 11:00:00", "ntceKindNm": "등록공고"}
    base.update(raw)
    return Bid(source=source, bid_no=NO, title="t", deadline_at=deadline, raw=base)


def _aw(name, clsfc="0", rbid="000", ord_="000") -> BidAward:
    return BidAward(
        bid_ntce_no=NO, bid_ntce_ord=ord_, bid_clsfc_no=clsfc, rbid_no=rbid, winner_name=name
    )


def _st(status, clsfc="0", rbid="000", ord_="000", text=None, top=None, n=None):
    return BidOpeningStatus(
        bid_ntce_no=NO,
        bid_ntce_ord=ord_,
        bid_clsfc_no=clsfc,
        rbid_no=rbid,
        status=status,
        result_text=text,
        top_name=top,
        participant_count=n,
    )


def test_open_cancelled_and_prespec():
    assert decide(_bid(deadline=NOW + timedelta(hours=1)), NOW, [], []) is None
    assert decide(_bid(deadline=None), NOW, [], []) is None
    assert decide(_bid(ntceKindNm="취소공고"), NOW, [_aw("가")], []) is None
    assert decide(_bid(source="prespec"), NOW, [], []).kind == "prespec_closed"  # type: ignore[union-attr]
    assert decide(_bid(source="prespec", deadline=NOW + timedelta(days=1)), NOW, [], []) is None


def test_awarded_wins_over_status_and_counts_other_classes():
    o = decide(
        _bid(), NOW, [_aw("(주)가온", "1"), _aw("(주)나래", "2")], [_st("개찰완료", top="x")]
    )
    assert o is not None and o.kind == "awarded"
    assert (o.company, o.more) == ("(주)가온", 1)


def test_award_uses_last_rebid_per_class():
    o = decide(_bid(), NOW, [_aw("옛", rbid="000"), _aw("새", rbid="001")], [])
    assert o is not None and (o.company, o.more) == ("새", 0)


def test_other_order_rows_are_ignored():
    """정정공고: 현재 차수(001)가 아닌 000 차수의 낙찰·상태는 보지 않는다."""
    bid = _bid(bidNtceOrd="001")
    o = decide(bid, NOW, [_aw("옛 차수", ord_="000")], [_st("유찰", ord_="000")])
    assert o is not None and o.kind == "waiting"


def test_failed_when_every_class_failed_with_reason():
    o = decide(
        _bid(), NOW, [], [_st("유찰", "1", text="단일응찰"), _st("유찰", "2", text="무응찰")]
    )
    assert o is not None and (o.kind, o.reason) == ("failed", "단독응찰")


def test_mixed_classes_and_rebids():
    # 한 분류 유찰 · 한 분류 개찰완료 → 개찰완료(1순위)
    o = decide(_bid(), NOW, [], [_st("유찰", "1"), _st("개찰완료", "2", top="(주)다온")])
    assert o is not None and (o.kind, o.company) == ("opened", "(주)다온")
    # 재입찰 000 → 001 개찰완료: 마지막 재입찰 행이 상태
    o = decide(_bid(), NOW, [], [_st("재입찰", rbid="000"), _st("개찰완료", rbid="001", top="라")])
    assert o is not None and (o.kind, o.company) == ("opened", "라")
    # 유찰 + 재입찰 진행 → 재입찰
    o = decide(_bid(), NOW, [], [_st("유찰", "1"), _st("재시담", "2")])
    assert o is not None and o.kind == "rebid"


def test_no_result_yet_uses_opening_date():
    before = decide(_bid(opengDt="2026-11-28 10:00:00"), NOW, [], [])
    assert before is not None and before.kind == "before_opening"
    assert before.opening_at == datetime(2026, 11, 28, 1, 0, tzinfo=UTC)
    waiting = decide(_bid(), NOW, [], [])
    assert waiting is not None and waiting.kind == "waiting"
    assert decide(_bid(opengDt=""), NOW, [], []) is None  # 개찰일 없음 → 지금처럼 '마감'만


def test_failed_reason_groups_free_text():
    assert failed_reason(["단독응찰"], [None]) == "단독응찰"
    assert failed_reason(["단일 응찰"], [None]) == "단독응찰"
    assert failed_reason(["전 업체 낙찰하한선 미달"], [None]) == "낙찰하한선 미달"
    assert failed_reason([None], [0]) == "무응찰"  # 문구가 없어도 참가 0이면 무응찰
    assert failed_reason(["기타 사유"], [3]) is None
