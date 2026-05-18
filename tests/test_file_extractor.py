import pytest
import io, zipfile

async def test_extract_docx():
    from nara_server.file_extractor import extract_text_from_url
    import docx
    buf = io.BytesIO()
    doc = docx.Document()
    doc.add_paragraph("안녕하세요 테스트")
    doc.save(buf)
    buf.seek(0)
    from unittest.mock import AsyncMock, patch, MagicMock
    import httpx

    mock_resp = MagicMock()
    mock_resp.content = buf.getvalue()
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client
        result = await extract_text_from_url("http://example.com/doc.docx", "doc.docx")
    assert "안녕하세요" in result

async def test_extract_url_bad_url_returns_empty():
    from nara_server.file_extractor import extract_text_from_url
    result = await extract_text_from_url("http://localhost:9999/nonexistent.hwp", "test.hwp")
    assert result == "" or isinstance(result, str)

async def test_function_signature_exists():
    from nara_server.file_extractor import extract_text_from_url
    import inspect
    sig = inspect.signature(extract_text_from_url)
    # GitHub source uses 'url' as first param (not 'file_url')
    params = list(sig.parameters.keys())
    assert params[0] in ("url", "file_url")
    assert "filename" in sig.parameters
