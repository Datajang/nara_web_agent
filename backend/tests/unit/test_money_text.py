"""어시스턴트 도구 결과의 금액 표기와 금액만 대조하기 (2026-11-18 '3억을 30억으로 읽음')."""

from app.analysis.explain_check import unsupported_money
from app.bids.meta import money_reading, money_text


def test_money_text_gives_won_and_correct_reading():
    assert money_text(302_727_273) == "302,727,273원 (약 3억 272만 원)"
    assert money_text(1_500_000_000) == "1,500,000,000원 (15억 원)"
    assert money_text(45_000_000) == "45,000,000원 (4,500만 원)"
    assert money_text(123_456_789_012) == "123,456,789,012원 (약 1,234억 5,678만 원)"
    assert money_text(8_500) == "8,500원"
    assert money_text(None) == money_text(0) == "미공개"
    assert money_reading(100_000_000) == "1억"


def test_reading_in_payload_matches_its_own_number_check():
    payload = {"budget": money_text(302_727_273)}
    assert unsupported_money(["약 3억 272만 원", "3억 원", "302,727,273원"], payload) == []


def test_wrong_reading_is_caught_but_counts_dates_and_bounds_are_not():
    payload = {"budget": money_text(302_727_273)}
    assert unsupported_money(["302,727,273원 (약 30 억 2700 만원)"], payload) == ["30 억 2700 만"]
    assert unsupported_money(["약 30억 원"], payload) == ["30억"]
    ok = "3건, 2026-11-30 마감. 10억 이상 공고는 없고 5천만 원 미만도 없어요. 1억대 공고. 12%"
    assert unsupported_money([ok], payload) == []
