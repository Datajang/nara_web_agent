"""파일 추출기 테스트. 네트워크(curl 서브프로세스)는 download_file 경계에서 가짜로 대체한다."""

import inspect
import io
import zipfile
from unittest.mock import AsyncMock, patch

import docx

from app.files import extractor
from app.files.extractor import (
    extract_text_from_bytes,
    extract_text_from_url,
    select_best_file_from_zip,
)


def _docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    doc = docx.Document()
    doc.add_paragraph(text)
    doc.save(buf)
    return buf.getvalue()


def test_extract_docx_from_bytes():
    assert "안녕하세요" in extract_text_from_bytes(_docx_bytes("안녕하세요 테스트"), "doc.docx")


async def test_extract_docx():
    fake = AsyncMock(return_value=(_docx_bytes("안녕하세요 테스트"), "doc.docx"))
    with patch.object(extractor, "download_file", fake):
        result = await extract_text_from_url("http://example.com/doc.docx", "doc.docx")
    assert "안녕하세요" in result
    fake.assert_awaited_once()


async def test_extract_url_download_error_returns_message():
    fake = AsyncMock(side_effect=RuntimeError("HTTP 404"))
    with patch.object(extractor, "download_file", fake):
        result = await extract_text_from_url("http://example.com/missing.hwp", "missing.hwp")
    assert result.startswith("Download failed")


def test_unsupported_extension():
    assert extract_text_from_bytes(b"abc", "a.txt").startswith("Unsupported file format")


def test_select_best_file_from_zip_priority():
    # 1순위: 파일명에 제안요청서·과업지시서 (확장자보다 우선)
    assert select_best_file_from_zip(["붙임1.hwp", "제안요청서.pdf"]) == "제안요청서.pdf"
    # 2순위: hwp/hwpx > docx/pdf
    assert select_best_file_from_zip(["a.pdf", "b.hwpx"]) == "b.hwpx"
    # 숨김 파일·__MACOSX 제외, 맞는 게 없으면 None
    assert select_best_file_from_zip(["__MACOSX/x.hwp", ".hidden.hwp", "a.txt"]) is None


def test_extract_from_zip_with_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("제안요청서.docx", _docx_bytes("과업 범위 설명"))
    assert "과업 범위" in extract_text_from_bytes(buf.getvalue(), "files.zip")


def test_function_signature_exists():
    params = list(inspect.signature(extract_text_from_url).parameters)
    assert params[0] == "url"
    assert "filename" in params
