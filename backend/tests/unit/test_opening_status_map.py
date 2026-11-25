"""개찰결과 목록 행 → bid_opening_status (2026-11-26, decisions/2026-11-26-opening-status-bulk)."""

from datetime import UTC, datetime

from app.awards.status import to_status


def _item(**kw):
    base = {
        "bidNtceNo": "R26BK01835732",
        "bidNtceOrd": "000",
        "bidClsfcNo": "0",
        "rbidNo": "001",
        "progrsDivCdNm": "개찰완료",
        "opengDt": "2026-11-25 16:00:00",
        "inptDt": "2026-11-25 18:09:28",
        "prtcptCnum": "7",
        "opengRsltNtcCntnts": "개찰완료",
        "opengCorpInfo": "주식회사 여행원^3908601319^나윤수^100418000^99.023",
    }
    base.update(kw)
    return base


def test_maps_key_status_times_and_top_company():
    r = to_status(_item())
    assert r is not None
    assert r.key == ("R26BK01835732", "000", "0", "001")
    assert r.status == "개찰완료" and r.participant_count == 7
    assert r.opened_at == datetime(2026, 11, 25, 7, 0, tzinfo=UTC)
    assert r.input_at == datetime(2026, 11, 25, 9, 9, 28, tzinfo=UTC)
    assert (r.top_name, r.top_bizno) == ("주식회사 여행원", "3908601319")
    assert r.result_text == "개찰완료"


def test_failed_row_without_company_and_long_text():
    r = to_status(
        _item(progrsDivCdNm="유찰", opengCorpInfo="", prtcptCnum="0", opengRsltNtcCntnts="가" * 300)
    )
    assert r is not None and r.status == "유찰" and r.participant_count == 0
    assert r.top_name is None and r.top_bizno is None
    assert r.result_text == "가" * 200


def test_defaults_and_unusable_rows():
    r = to_status(_item(bidNtceOrd="", bidClsfcNo=None, rbidNo="", opengCorpInfo="이름만"))
    assert r is not None and r.key[1:] == ("000", "0", "000")
    assert r.top_name == "이름만" and r.top_bizno is None
    assert to_status(_item(bidNtceNo="")) is None
    assert to_status(_item(progrsDivCdNm="")) is None
