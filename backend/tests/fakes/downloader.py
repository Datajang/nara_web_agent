"""URL → 바이트를 돌려주는 가짜 다운로더. 호출 수를 센다."""

from __future__ import annotations

import io

import docx

from app.files.download import DownloadRejected, DownloadResult


def docx_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    d = docx.Document()
    d.add_paragraph(text)
    d.save(buf)
    return buf.getvalue()


class FakeDownloader:
    def __init__(self, files: dict[str, tuple[bytes, str]] | None = None) -> None:
        self.files = files or {}
        self.calls: list[str] = []

    async def fetch(self, url: str) -> DownloadResult:
        self.calls.append(url)
        if url not in self.files:
            raise DownloadRejected(f"not found: {url}")
        content, name = self.files[url]
        return DownloadResult(content=content, filename=name, content_type=None)
