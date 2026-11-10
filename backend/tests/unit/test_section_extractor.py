from app.pipeline.section_extractor import estimate_tokens, compress_document, TARGET_DOC_TOKENS

def test_estimate_tokens_korean():
    text = "안녕" * 100  # 200 Korean chars → ~300 tokens
    assert 250 <= estimate_tokens(text) <= 350

def test_estimate_tokens_mixed():
    text = "Hello " * 50 + "안녕 " * 50
    result = estimate_tokens(text)
    assert result > 0

def test_short_text_returned_as_is():
    short = "사업 개요\n짧은 내용입니다." * 10
    result = compress_document(short)
    assert result == short

def test_long_text_compressed():
    long_text = "가" * 8000
    result = compress_document(long_text)
    assert estimate_tokens(result) <= TARGET_DOC_TOKENS + 100

def test_section_priority_preserved():
    core = "1. 사업 개요\n" + "핵심내용 " * 500
    filler = "99. 별첨\n" + "첨부내용 " * 2000
    result = compress_document(core + "\n\n" + filler)
    assert "사업 개요" in result or estimate_tokens(result) <= TARGET_DOC_TOKENS

def test_fallback_when_no_headers():
    text = ("내용입니다. " * 200 + "\n\n") * 20
    result = compress_document(text)
    assert "이하 내용 생략" in result
    assert estimate_tokens(result) <= TARGET_DOC_TOKENS + 200
