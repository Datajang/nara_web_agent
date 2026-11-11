"""첨부 파일 파이프라인 (SPEC §5.6, §5.9-7)."""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import BidFile, FileText
from app.files.download import DownloadRejected, HttpDownloader
from app.files.store import ensure_bid_files
from tests.conftest import NOW
from tests.fakes.downloader import docx_bytes
from tests.fakes.g2b import regular_item
from tests.helpers import seed

ALLOW = frozenset({"www.g2b.go.kr"})


def _http(handler) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), seen


async def test_disallowed_host_fails_without_network():
    """§5.9-7: 허용 호스트 밖 URL은 네트워크 요청 없이 실패."""
    http, seen = _http(lambda r: httpx.Response(200, content=b"x"))
    dl = HttpDownloader(http, ALLOW, max_bytes=1024)
    with pytest.raises(DownloadRejected):
        await dl.fetch("https://evil.example.com/a.hwp")
    assert seen == []


async def test_redirect_to_disallowed_host_is_rejected():
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    http, seen = _http(handler)
    with pytest.raises(DownloadRejected):
        await HttpDownloader(http, ALLOW, max_bytes=1024).fetch("https://www.g2b.go.kr/a.hwp")
    assert len(seen) == 1


async def test_file_larger_than_limit_is_rejected():
    http, _ = _http(lambda r: httpx.Response(200, content=b"0" * 5000))
    with pytest.raises(DownloadRejected):
        await HttpDownloader(http, ALLOW, max_bytes=1024).fetch("https://www.g2b.go.kr/big.pdf")


async def test_filename_from_content_disposition():
    cd = "attachment;filename=%EC%A0%9C%EC%95%88%EC%9A%94%EC%B2%AD%EC%84%9C.hwp"
    http, _ = _http(
        lambda r: httpx.Response(200, content=b"abc", headers={"content-disposition": cd})
    )
    res = await HttpDownloader(http, ALLOW, max_bytes=1024).fetch("https://www.g2b.go.kr/x")
    assert res.filename == "제안요청서.hwp" and res.content == b"abc"


async def test_disallowed_attachment_marked_failed_in_db(deps, fake_downloader):
    item = regular_item(
        "R26BK70000001",
        NOW - timedelta(hours=1),
        files=[("https://evil.example.com/a.hwp", "제안요청서.hwp")],
    )
    (bid_id,) = await seed(deps, "regular", item)
    files = await ensure_bid_files(deps, bid_id)
    assert [(f.status, f.attempts) for f in files] == [("failed", 1)]
    assert "evil.example.com" in (files[0].error or "")
    assert fake_downloader.calls == []  # 다운로더를 부르기 전에 막는다


async def test_same_file_on_two_bids_is_extracted_once(deps, fake_downloader):
    content = docx_bytes("공통 과업지시서")
    fake_downloader.files["https://www.g2b.go.kr/a.docx"] = (content, "과업지시서.docx")
    fake_downloader.files["https://www.g2b.go.kr/b.docx"] = (content, "과업지시서.docx")
    a, b = await seed(
        deps,
        "regular",
        regular_item(
            "R26BK70000002", NOW, files=[("https://www.g2b.go.kr/a.docx", "과업지시서.docx")]
        ),
        regular_item(
            "R26BK70000003", NOW, files=[("https://www.g2b.go.kr/b.docx", "과업지시서.docx")]
        ),
    )
    await ensure_bid_files(deps, a)
    files = await ensure_bid_files(deps, b)
    assert files[0].status == "ok"
    async with deps.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(FileText)) == 1
        text_row = (await s.execute(select(FileText))).scalar_one()
    assert "공통 과업지시서" in text_row.text


async def test_unsupported_format(deps, fake_downloader):
    fake_downloader.files["https://www.g2b.go.kr/a.txt"] = (b"plain", "readme.txt")
    (bid_id,) = await seed(
        deps,
        "regular",
        regular_item("R26BK70000004", NOW, files=[("https://www.g2b.go.kr/a.txt", "readme.txt")]),
    )
    files = await ensure_bid_files(deps, bid_id)
    assert files[0].status == "unsupported"


async def test_ok_file_is_not_downloaded_again(deps, fake_downloader):
    fake_downloader.files["https://www.g2b.go.kr/c.docx"] = (docx_bytes("본문"), "c.docx")
    (bid_id,) = await seed(
        deps,
        "regular",
        regular_item("R26BK70000005", NOW, files=[("https://www.g2b.go.kr/c.docx", "c.docx")]),
    )
    await ensure_bid_files(deps, bid_id)
    await ensure_bid_files(deps, bid_id)
    assert len(fake_downloader.calls) == 1
    async with deps.db.session() as s:
        assert (await s.execute(select(BidFile.status))).scalar_one() == "ok"
