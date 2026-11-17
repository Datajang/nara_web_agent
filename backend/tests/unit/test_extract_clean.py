"""추출 텍스트 정리: PostgreSQL text에 못 넣는 NUL(0x00)을 공백으로 (2026-11-17 분석 실패)."""

from app.files.extract import clean_text


def test_nul_used_as_word_space_becomes_space():
    raw = "주소: 충청북도\x00청주시\x00흥덕구\n용역\x00입찰\x00공고"
    assert clean_text(raw) == "주소: 충청북도 청주시 흥덕구\n용역 입찰 공고"
    assert "\x00" not in clean_text("\x00\x00a\x00")


def test_normal_text_is_unchanged():
    raw = "[Page 1]\n- 1 -\n입찰 공고\t(긴급)"
    assert clean_text(raw) == raw
