"""낙찰 매퍼·분야 분류·수집 창 계획 (SPEC §15.3·§15.4). 순수 함수."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

from app.awards.collector import plan_backfill, plan_incremental
from app.awards.fields import classify, clean_keywords
from app.awards.mapper import AWARD_FIELDS, normalize_bizno, normalize_name, to_award
from app.awards.store import award_ratio
from app.collector.coverage import Coverage
from app.collector.windows import split_dates

NOW = datetime(2026, 11, 16, 3, 0, tzinfo=UTC)
KST = timezone(timedelta(hours=9))
D = timedelta(days=1)

ITEM = {
    "bidNtceNo": "R26BK01796947",
    "bidNtceOrd": "001",
    "bidClsfcNo": "0",
    "rbidNo": "000",
    "ntceDivCd": "통050001",
    "bidNtceNm": "소방헬기 외주정비 용역",
    "prtcptCnum": "3",
    "bidwinnrNm": "한국항공서비스 주식회사",
    "bidwinnrBizno": "3408601051",
    "bidwinnrCeoNm": "대표자",
    "bidwinnrAdrs": "주소",
    "bidwinnrTelNo": "02-000-0000",
    "fnlSucsfCorpOfcl": "담당자",
    "sucsfbidAmt": "148370610",
    "sucsfbidRate": "96.358",
    "rlOpengDt": "2026-11-03 11:01:51",
    "dminsttCd": "6286337",
    "dminsttNm": "인천광역시 소방본부",
    "rgstDt": "2026-11-09 07:41:36",
    "fnlSucsfDate": "2026-11-09",
}


def test_to_award_reads_whitelist_only():
    r = to_award(ITEM)
    assert r is not None
    assert r.key == ("R26BK01796947", "001", "0", "000")
    assert (r.bizno, r.award_amount, r.g2b_award_rate) == (
        "3408601051",
        148370610,
        Decimal("96.358"),
    )
    assert r.participant_count == 3 and r.awarded_on == date(2026, 11, 9)
    assert r.registered_at == datetime(2026, 11, 8, 22, 41, 36, tzinfo=UTC)  # KST → UTC
    assert r.opened_at == datetime(2026, 11, 3, 2, 1, 51, tzinfo=UTC)
    stored = " ".join(str(v) for v in vars(r).values())
    for pii in ("대표자", "주소", "02-000-0000", "담당자"):
        assert pii not in stored
    assert {"bidwinnrCeoNm", "bidwinnrAdrs", "bidwinnrTelNo", "fnlSucsfCorpOfcl"}.isdisjoint(
        AWARD_FIELDS
    )


def test_to_award_handles_blanks_and_missing_keys():
    blank = {**ITEM, "sucsfbidRate": "", "sucsfbidAmt": "", "prtcptCnum": None, "rlOpengDt": ""}
    r = to_award(blank)
    assert r is not None
    assert (r.g2b_award_rate, r.award_amount, r.participant_count, r.opened_at) == (
        None,
        None,
        None,
        None,
    )
    assert r.seen_at == r.registered_at
    assert to_award({**ITEM, "bidNtceNo": ""}) is None
    assert to_award({**ITEM, "rgstDt": ""}) is None


def test_normalize_bizno():
    assert normalize_bizno("123-45-67890") == "1234567890"
    assert normalize_bizno("12345") is None
    assert normalize_bizno(None) is None
    assert normalize_bizno("") is None


def test_normalize_name_strips_legal_forms():
    assert normalize_name("주식회사 가온 데이터") == "가온데이터"
    assert normalize_name("(주)가온데이터") == "가온데이터"
    assert normalize_name("㈜가온데이터") == "가온데이터"
    assert normalize_name("Gaon Data Co.,Ltd.") == "gaondatacoltd"


def test_classify_is_deterministic_and_space_insensitive():
    kw = clean_keywords({"AI 분석": ["인공 지능", "AI"], "데이터 정비": ["DB 구축"], "빈": []})
    assert kw == {"AI 분석": ["인공 지능", "AI"], "데이터 정비": ["DB 구축"]}
    assert classify("인공지능 기반 db구축", kw) == ["AI 분석", "데이터 정비"]
    assert classify("청소 용역", kw) == []
    assert classify("x", {}) == []
    assert clean_keywords(None) == {} and clean_keywords({"a": "문자열"}) == {}


def test_award_ratio():
    assert award_ratio(80, 100) == Decimal("0.80000")
    assert award_ratio(None, 100) is None
    assert award_ratio(80, None) is None
    assert award_ratio(80, 0) is None


def _dates(s: datetime, e: datetime) -> int:
    """요청이 덮는 KST 날짜 수(끝은 '창 끝 - 1분')."""
    return ((e - timedelta(minutes=1)).astimezone(KST).date() - s.astimezone(KST).date()).days + 1


def _contiguous(cov: Coverage | None, windows):
    """창을 순서대로 합칠 때 매번 커버리지와 닿고, 창마다 KST 날짜 7개 이하다."""
    lo, hi = (cov.covered_from, cov.covered_to) if cov else (None, None)
    for s, e in windows:
        assert s < e and _dates(s, e) <= 7, (s, e)
        if lo is not None:
            assert not (e < lo or s > hi), (s, e, lo, hi)
            lo, hi = min(lo, s), max(hi, e)
        else:
            lo, hi = s, e
    return lo, hi


def test_plan_backfill_fresh_goes_newest_first():
    w = plan_backfill(None, NOW - 20 * D, NOW)
    # NOW = 11-16 12:00 KST → 최신 창은 11-10 00:00 KST부터(날짜 7개)
    assert w[0] == (datetime(2026, 11, 9, 15, 0, tzinfo=UTC), NOW)
    assert _contiguous(None, w) == (NOW - 20 * D, NOW)


def test_plan_backfill_fills_both_gaps_contiguously():
    cov = Coverage(NOW - 30 * D, NOW - 20 * D)
    w = plan_backfill(cov, NOW - 60 * D, NOW)
    assert w[0][0] == NOW - 20 * D  # covered_to에서 앞으로, 다음 KST 자정 7일 뒤까지
    assert w[0][1] == datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    assert _contiguous(cov, w) == (NOW - 60 * D, NOW)


def test_split_dates_keeps_each_request_within_seven_dates():
    for days in (1, 6, 7, 8, 30, 365):
        for newest in (True, False):
            w = split_dates(NOW - days * D, NOW, 7, newest_first=newest)
            _contiguous(None, sorted(w))
            assert min(s for s, _ in w) == NOW - days * D and max(e for _, e in w) == NOW
    # 자정에 끝나는 창: 끝-1분의 날짜로 센다
    mid = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)  # 11-10 00:00 KST
    assert split_dates(mid - 30 * D, mid, 7, newest_first=True)[0] == (mid - 7 * D, mid)


def test_plan_backfill_nothing_to_do():
    assert plan_backfill(Coverage(NOW - 60 * D, NOW), NOW - 30 * D, NOW) == []


def test_plan_incremental_refetches_last_14_days():
    cov = Coverage(NOW - 400 * D, NOW - 1 * D)
    w = plan_incremental(cov, NOW)
    assert w[0][0] == NOW - 14 * D and w[-1][1] == NOW
    _contiguous(cov, w)
    # covered_to가 오래됐으면 거기서부터
    old = Coverage(NOW - 400 * D, NOW - 30 * D)
    assert plan_incremental(old, NOW)[0][0] == NOW - 30 * D
    # 커버리지가 짧으면 covered_from에서
    short = Coverage(NOW - 3 * D, NOW - 1 * D)
    assert plan_incremental(short, NOW)[0][0] == NOW - 3 * D
    assert _contiguous(None, plan_incremental(None, NOW)) == (NOW - 14 * D, NOW)
