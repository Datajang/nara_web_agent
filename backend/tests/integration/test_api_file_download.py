"""첨부 원본 내려받기 (§6.2 files/{id}/download).

원본은 저장하지 않으므로 누를 때 G2B에서 다시 받아 넘긴다.
"""

from typing import Any
from urllib.parse import quote

from tests.conftest import NOW
from tests.fakes.g2b import regular_item
from tests.helpers import member, seed

URL = "https://www.g2b.go.kr/files/rfp-dl.hwp"
NAME = "제안요청서(AI 플랫폼).hwp"


async def _bid(full_api) -> tuple[Any, int, int]:
    """로그인한 회원 클라이언트(호출자가 aclose), 공고 id, 첨부 id."""
    item = regular_item("R26BK73000001", NOW, files=[(URL, NAME)])
    (bid_id,) = await seed(full_api.ctx.deps, "regular", item)
    c = await member(full_api, "dl@corp.example")
    fid = (await c.get(f"/api/v1/bids/b{bid_id}")).json()["files"][0]["file_id"]
    return c, bid_id, fid


async def test_download_streams_original_bytes_as_attachment(full_api, fake_downloader):
    fake_downloader.files[URL] = (b"HWP-ORIGINAL-BYTES", "server-name.hwp")
    c, bid_id, fid = await _bid(full_api)
    r = await c.get(f"/api/v1/bids/b{bid_id}/files/{fid}/download")
    await c.aclose()
    assert r.status_code == 200
    assert r.content == b"HWP-ORIGINAL-BYTES"
    # 브라우저가 열어 보지 않고 저장하게 한다 (업로드된 HTML이 우리 출처에서 실행되지 않게)
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.headers["x-content-type-options"] == "nosniff"
    cd = r.headers["content-disposition"]
    assert cd.startswith("attachment;") and f"filename*=UTF-8''{quote(NAME)}" in cd
    assert URL not in r.text and "g2b.go.kr" not in str(r.headers)  # 첨부 URL은 노출하지 않는다
    assert fake_downloader.calls == [URL]


async def test_download_of_unknown_or_other_bids_file_is_404(full_api, fake_downloader):
    c, bid_id, fid = await _bid(full_api)
    (other,) = await seed(full_api.ctx.deps, "regular", regular_item("R26BK73000002", NOW))
    codes = [
        (await c.get(path)).status_code
        for path in (
            f"/api/v1/bids/b{bid_id}/files/999999/download",
            f"/api/v1/bids/b{other}/files/{fid}/download",
        )
    ]
    await c.aclose()
    assert codes == [404, 404] and fake_downloader.calls == []


async def test_download_failure_is_502_with_korean_message(full_api, fake_downloader):
    c, bid_id, fid = await _bid(full_api)  # fake_downloader에 없는 URL → DownloadRejected
    r = await c.get(f"/api/v1/bids/b{bid_id}/files/{fid}/download")
    await c.aclose()
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "file_unavailable" and "첨부 파일" in err["message"]
    assert "rfp-dl" not in r.text  # 실패 사유에도 URL을 싣지 않는다


async def test_download_needs_login(full_api, fake_downloader):
    fake_downloader.files[URL] = (b"x", NAME)
    c, bid_id, fid = await _bid(full_api)
    await c.aclose()
    async with full_api.client() as anon:
        r = await anon.get(f"/api/v1/bids/b{bid_id}/files/{fid}/download")
    assert r.status_code == 401 and fake_downloader.calls == []
