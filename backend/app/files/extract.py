"""텍스트 추출 (SPEC §5.6-5). v1 추출기(extractor.py)를 별도 프로세스에서 60초 제한으로 실행한다.

손상·악성 문서가 API 프로세스를 멈추지 못하게 하려는 것. 시간 초과면 작업 프로세스를 죽이고 새로
만든다.
형식은 파일명 확장자 → 없으면 매직 바이트로 판별한다.
"""

from __future__ import annotations

import asyncio
import io
import multiprocessing
import zipfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

EXTRACTOR_VERSION = "v1-extractor-1"
TIMEOUT_S = 60.0
SUPPORTED = {".hwp", ".hwpx", ".pdf", ".docx", ".xlsx", ".xls", ".zip"}
# v1 추출기는 실패를 예외 대신 문자열로 돌려준다
_FAIL_PREFIXES = (
    "Unsupported file format",
    "PDF extraction failed",
    "HWP extraction failed",
    "HWP Protected",
    "HWP: Could not extract",
    "HWPX extraction failed",
    "HWPX: Invalid",
    "DOCX extraction failed",
    "XLSX extraction failed",
    "ZIP extraction failed",
    "ZIP: Invalid",
    "ZIP: No suitable",
    "ZIP: Unsupported",
)
_EMPTY_PREFIXES = ("PDF: No extractable", "DOCX: No text", "XLSX: No data", "HWPX: No text")
_pool: ProcessPoolExecutor | None = None


@dataclass
class ExtractOutcome:
    status: str  # ok | failed | unsupported
    text: str = ""
    error: str | None = None


def sniff_extension(content: bytes, filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in SUPPORTED:
        return ext
    if content.startswith(b"%PDF"):
        return ".pdf"
    if content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        return ".hwp"  # OLE 복합 문서. 나라장터 첨부에서는 대부분 HWP
    if content.startswith(b"PK"):
        try:
            names = zipfile.ZipFile(io.BytesIO(content)).namelist()
        except zipfile.BadZipFile:
            return ext
        if any(n.startswith("word/") for n in names):
            return ".docx"
        if any(n.startswith("xl/") for n in names):
            return ".xlsx"
        if any(n.startswith("Contents/") for n in names):
            return ".hwpx"
        return ".zip"
    return ext


def _run(content: bytes, filename: str) -> str:
    from app.files.extractor import extract_text_from_bytes

    return extract_text_from_bytes(content, filename)


def _get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"))
    return _pool


def _kill_pool() -> None:
    global _pool
    if _pool is not None:
        for p in list(getattr(_pool, "_processes", {}).values()):
            p.kill()
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


async def extract_text(
    content: bytes, filename: str | None, timeout_s: float = TIMEOUT_S
) -> ExtractOutcome:
    ext = sniff_extension(content, filename)
    if ext not in SUPPORTED:
        return ExtractOutcome("unsupported", error=f"지원하지 않는 형식: {ext or '(확장자 없음)'}")
    name = f"file{ext}"
    loop = asyncio.get_running_loop()
    try:
        raw = await asyncio.wait_for(
            loop.run_in_executor(_get_pool(), _run, content, name), timeout_s
        )
    except TimeoutError:
        _kill_pool()
        return ExtractOutcome("failed", error=f"추출 시간 초과({timeout_s:.0f}초)")
    except Exception as e:  # 작업 프로세스 비정상 종료 등
        _kill_pool()
        return ExtractOutcome("failed", error=f"추출 프로세스 오류: {type(e).__name__}")
    if raw.startswith(_FAIL_PREFIXES) or "requires" in raw[:80] and "library" in raw[:120]:
        return ExtractOutcome("failed", error=raw[:300])
    if raw.startswith(_EMPTY_PREFIXES):
        return ExtractOutcome(
            "ok", text=""
        )  # 스캔본 등. 요약 단계에서 '본문을 읽지 못함' 경고(§5.6-8)
    return ExtractOutcome("ok", text=raw)
