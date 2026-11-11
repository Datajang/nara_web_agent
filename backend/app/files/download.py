"""첨부 다운로드 (SPEC §5.6). httpx 스트리밍 + 인증서 검증 (probe: g2b가 httpx로 정상 응답).

- 허용 호스트 밖이면 요청하지 않는다(SSRF). 리다이렉트는 수동으로 최대 3회, 매번 호스트 재검사.
- FILE_MAX_MB 초과 시 중단. 읽기 타임아웃 30초, 네트워크 오류·5xx는 2회 재시도.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import unquote, urljoin, urlparse

import httpx

MAX_REDIRECTS = 3
RETRIES = 2


class DownloadRejected(Exception):
    """허용 호스트 밖·크기 초과·HTTP 오류 등으로 받지 않은 파일."""


@dataclass
class DownloadResult:
    content: bytes
    filename: str | None
    content_type: str | None


class Downloader(Protocol):
    async def fetch(self, url: str) -> DownloadResult: ...


def host_allowed(url: str, allow_hosts: frozenset[str]) -> bool:
    p = urlparse(url)
    return p.scheme in ("https", "http") and (p.hostname or "").lower() in allow_hosts


def filename_from_disposition(value: str | None) -> str | None:
    if not value:
        return None
    if m := re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", value):
        return unquote(m.group(1).strip().strip('"'))
    if m := re.search(r'filename\s*=\s*"?([^";]+)"?', value):
        return unquote(m.group(1).strip())
    return None


class HttpDownloader:
    def __init__(
        self, http: httpx.AsyncClient, allow_hosts: frozenset[str], max_bytes: int
    ) -> None:
        self.http, self.allow_hosts, self.max_bytes = http, allow_hosts, max_bytes

    async def fetch(self, url: str) -> DownloadResult:
        last: Exception | None = None
        for _ in range(RETRIES + 1):
            try:
                return await self._fetch_once(url)
            except (httpx.TransportError, _Retryable) as e:
                last = e
        raise DownloadRejected(f"다운로드 실패: {type(last).__name__}: {last}")

    async def _fetch_once(self, url: str) -> DownloadResult:
        for _ in range(MAX_REDIRECTS + 1):
            if not host_allowed(url, self.allow_hosts):
                raise DownloadRejected(f"허용되지 않은 호스트: {urlparse(url).hostname}")
            timeout = httpx.Timeout(30.0, connect=5.0)
            async with self.http.stream(
                "GET", url, follow_redirects=False, timeout=timeout
            ) as resp:
                if resp.is_redirect:
                    url = urljoin(url, resp.headers.get("location", ""))
                    continue
                if resp.status_code >= 500:
                    raise _Retryable(f"HTTP {resp.status_code}")
                if resp.status_code >= 400:
                    raise DownloadRejected(f"HTTP {resp.status_code}")
                declared = int(resp.headers.get("content-length") or 0)
                if declared > self.max_bytes:
                    raise DownloadRejected(f"파일 크기 초과: {declared} bytes")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > self.max_bytes:
                        raise DownloadRejected(f"파일 크기 초과: {self.max_bytes} bytes 넘음")
                return DownloadResult(
                    content=bytes(buf),
                    filename=filename_from_disposition(resp.headers.get("content-disposition")),
                    content_type=resp.headers.get("content-type"),
                )
        raise DownloadRejected(f"리다이렉트 {MAX_REDIRECTS}회 초과")


class _Retryable(Exception):
    pass
