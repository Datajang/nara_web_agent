"""공고 첨부 확보: bid_files 상태 전이 new → ok | failed | unsupported (SPEC §5.6).

- 같은 파일(sha256)은 file_texts에 한 번만 추출해 여러 공고가 공유한다.
- failed는 24시간 뒤 최대 3회 재시도.
- 허용 호스트 검사는 다운로더와 별개로 여기서도 먼저 한다(어떤 다운로더를 주입해도 SSRF 방지).
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.models import BidFile, FileText
from app.deps import Deps
from app.files.download import DownloadRejected, host_allowed
from app.files.extract import EXTRACTOR_VERSION, extract_text
from app.pipeline.singleflight import single_flight

RETRY_AFTER = timedelta(hours=24)
MAX_ATTEMPTS = 3


def _needs_work(f: BidFile, deps: Deps) -> bool:
    if f.status == "new":
        return True
    if f.status != "failed" or f.attempts >= MAX_ATTEMPTS:
        return False
    return f.downloaded_at is None or deps.clock() - f.downloaded_at >= RETRY_AFTER


async def _load(deps: Deps, file_id: int) -> BidFile:
    async with deps.db.session() as s:
        row = await s.get(BidFile, file_id)
        assert row is not None
        return row


async def _mark(deps: Deps, file_id: int, **values: object) -> None:
    async with deps.db.transaction() as s:
        await s.execute(
            update(BidFile)
            .where(BidFile.id == file_id)
            .values(downloaded_at=deps.clock(), **values)
        )


async def _process(deps: Deps, f: BidFile) -> BidFile:
    attempts = f.attempts + 1
    if not host_allowed(f.url, deps.settings.file_hosts):
        await _mark(
            deps,
            f.id,
            status="failed",
            attempts=attempts,
            error=f"허용되지 않은 호스트: {urlparse(f.url).hostname}",
        )
        return await _load(deps, f.id)
    if deps.downloader is None:
        raise RuntimeError("다운로더가 없습니다")
    try:
        got = await deps.downloader.fetch(f.url)
    except DownloadRejected as e:
        await _mark(deps, f.id, status="failed", attempts=attempts, error=str(e)[:300])
        return await _load(deps, f.id)

    sha = hashlib.sha256(got.content).hexdigest()
    async with deps.db.session() as s:
        cached = await s.get(FileText, sha)
    if cached is None:
        out = await extract_text(got.content, got.filename or f.name)
        if out.status != "ok":
            await _mark(
                deps,
                f.id,
                status=out.status,
                attempts=attempts,
                error=out.error,
                sha256=sha,
                size_bytes=len(got.content),
            )
            return await _load(deps, f.id)
        async with deps.db.transaction() as s:
            await s.execute(
                insert(FileText)
                .values(
                    sha256=sha,
                    text=out.text,
                    char_count=len(out.text),
                    extractor_version=EXTRACTOR_VERSION,
                )
                .on_conflict_do_nothing(index_elements=["sha256"])
            )
    await _mark(
        deps,
        f.id,
        status="ok",
        attempts=attempts,
        error=None,
        sha256=sha,
        size_bytes=len(got.content),
    )
    return await _load(deps, f.id)


async def ensure_bid_files(deps: Deps, bid_id: int) -> list[BidFile]:
    async with deps.db.session() as s:
        files = (
            (await s.execute(select(BidFile).where(BidFile.bid_id == bid_id).order_by(BidFile.id)))
            .scalars()
            .all()
        )
    out: list[BidFile] = []
    for f in files:
        if not _needs_work(f, deps):
            out.append(f)
            continue

        async def check(file_id: int = f.id) -> BidFile | None:
            row = await _load(deps, file_id)
            return None if _needs_work(row, deps) else row

        async def compute(row: BidFile = f) -> BidFile:
            return await _process(deps, await _load(deps, row.id))

        done, _ = await single_flight(deps.db, f"file:{bid_id}:{f.url_hash}", check, compute)
        out.append(done)
    return out
