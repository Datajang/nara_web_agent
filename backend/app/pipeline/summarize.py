"""공통 요약 (SPEC §5.7 캐시 계약, §8.3 map→reduce). 프로필과 무관하며 모든 사용자가 공유한다.

읽을 첨부(pick_files): rfp·spec. 그중 읽은 게 없으면 공고서·공고문도(서식 제외), 같은 문서의
hwpx·pdf는 하나만 (2026-11-13, 사용자 승인).
source_hash = 읽을 첨부 중 ok 파일 sha256을 정렬해 이어 붙인 값의 sha256.
읽을 파일이 없으면 `meta-only:{bids.content_hash}` (정정공고면 해시가 바뀌어 새 요약).

map: 파일 청크마다 FileFacts. 형식 오류는 repair 1회 뒤 그 청크만 건너뛰고, 컨텍스트 초과는
청크를 절반으로 나눠 1회 재시도 (§8.7). reduce: 메타 + FileFacts → BidSummary 하나.
coverage는 서버가 센 값으로 덮어쓰고, evidence는 원문에 실제로 있는 문자열만 남긴다 (§8.4).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.bids.meta import bid_meta
from app.db.models import Bid, BidFile, BidSummary, FileText
from app.deps import Deps
from app.files.store import ensure_bid_files, needs_work
from app.llm import usage
from app.llm.base import LLMClient, LLMContextTooLong, LLMInvalidOutput, LLMUnavailable
from app.llm.prompts import render
from app.llm.schemas import BidSummary as BidSummaryOut
from app.llm.schemas import Coverage, FileFacts, Requirement
from app.llm.structured import generate
from app.llm.tokens import TokenCounter, load_counter
from app.llm.versions import SUMMARY_PROMPT, prompt_version
from app.pipeline import chunking
from app.pipeline.grounding import ground, unverified_warning
from app.pipeline.singleflight import single_flight

SCANNED_THRESHOLD = 200  # §5.6-8: 이보다 짧으면 스캔본일 가능성
CHUNK_TARGET = chunking.TARGET_TOKENS
CHUNK_OVERLAP = chunking.OVERLAP_TOKENS
SINGLE_MAX = chunking.SINGLE_MAX
NO_FILES = "첨부 문서를 읽지 못함"  # 읽을 첨부는 있었는데 실패
NO_DOCS = "요약할 제안요청서·과업 문서가 없음"  # 읽을 첨부가 처음부터 없음
_NOTICE_WORDS = ("공고서", "공고문", "입찰공고")
_FORM_WORDS = ("신청서", "서약서", "확약서", "위임장", "양식", "서식", "내역서")
_EXT_ORDER = (".hwpx", ".hwp", ".docx", ".doc", ".pdf")  # 같은 문서면 한글 원본 먼저


class _FileLike(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def status(self) -> str: ...


_F = TypeVar("_F", bound=_FileLike)


def _flat(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def _stem_ext(name: str) -> tuple[str, str]:
    stem, dot, ext = name.rpartition(".")
    return (_flat(stem), "." + ext.lower()) if dot else (_flat(name), "")


def _is_notice(name: str) -> bool:
    flat = _flat(name)
    return any(w in flat for w in _NOTICE_WORDS) and not any(w in flat for w in _FORM_WORDS)


def _one_per_document(files: list[_F]) -> list[_F]:
    """같은 이름의 hwpx·pdf 등은 하나만: 받은 것 먼저, 그다음 한글 원본."""
    best: dict[str, tuple[tuple[bool, int], _F]] = {}
    for f in files:
        stem, ext = _stem_ext(f.name)
        rank = (f.status != "ok", _EXT_ORDER.index(ext) if ext in _EXT_ORDER else len(_EXT_ORDER))
        if stem not in best or rank < best[stem][0]:
            best[stem] = (rank, f)
    return [f for _, f in best.values()]


def pick_files(files: Sequence[_F]) -> list[_F]:
    """요약에 읽을 첨부. rfp·spec 중 받은 게 없으면 공고서·공고문(서식 제외)도 읽는다."""
    picked = [f for f in files if f.kind in ("rfp", "spec")]
    if not any(f.status == "ok" for f in picked):
        picked += [f for f in files if f.kind == "other" and _is_notice(f.name)]
    return _one_per_document(picked)


def known_source(source: str | None, names: Sequence[str]) -> str | None:
    """모델이 적은 근거가 실제로 읽은 파일이면 그 파일명, 아니면 None ('summary' 등)."""
    if not source:
        return None
    s = _flat(source)
    for n in names:
        if s in (_flat(n), _stem_ext(n)[0]) or (len(s) >= 4 and s in _flat(n)):
            return n
    return None


def _llm(deps: Deps) -> LLMClient:
    if deps.llm is None:
        raise LLMUnavailable("LLM 클라이언트가 없습니다")
    return deps.llm


@dataclass
class SourceDoc:
    sha: str
    name: str
    kind: str
    text: str


async def source_inputs(deps: Deps, bid: Bid) -> tuple[str, list[SourceDoc], list[BidFile]]:
    """(source_hash, 읽을 문서, 읽을 첨부 전체 — pick_files)."""
    async with deps.db.session() as s:
        files = pick_files(
            list(
                (
                    await s.execute(
                        select(BidFile).where(BidFile.bid_id == bid.id).order_by(BidFile.id)
                    )
                ).scalars()
            )
        )
        by_sha: dict[str, BidFile] = {}
        for f in files:
            if f.status == "ok" and f.sha256:
                by_sha.setdefault(f.sha256, f)
        shas = sorted(by_sha)
        if not shas:
            return f"meta-only:{bid.content_hash}", [], files
        texts = dict(
            (
                await s.execute(
                    select(FileText.sha256, FileText.text).where(FileText.sha256.in_(shas))
                )
            ).all()
        )
    docs = [SourceDoc(x, by_sha[x].name, by_sha[x].kind, texts.get(x, "")) for x in shas]
    return hashlib.sha256("".join(shas).encode()).hexdigest(), docs, files


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_evidence(reqs: list[Requirement], sources: list[str], default_source: str | None) -> None:
    """evidence가 원문에 그대로 있지 않으면 null (환각 방지, §8.4)."""
    normed = [_norm(t) for t in sources]
    for r in reqs:
        if r.evidence and not any(_norm(r.evidence) in t for t in normed):
            r.evidence = None
        if r.source is None and default_source:
            r.source = default_source


def attach_sources(reqs: list[Requirement], docs: Sequence[SourceDoc]) -> None:
    """근거 파일명은 서버가 정한다: 원문에 있는 evidence의 파일, 아니면 실제 파일명일 때만 모델 값.
    (2026-11-13 실모델 b546: 'bid_meta'·'other'·절 제목을 적음)"""
    normed = [(d.name, _norm(d.text)) for d in docs]
    names = [d.name for d in docs]
    for r in reqs:
        ev = _norm(r.evidence) if r.evidence else ""
        found = next((n for n, t in normed if ev and ev in t), None)
        r.source = found or known_source(r.source, names)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(x for x in items if x))


async def _map_chunk(
    llm: LLMClient, doc: SourceDoc, text: str, i: int, n: int, counter: TokenCounter
) -> tuple[list[FileFacts], list[str]]:
    async def one(t: str, label: str) -> FileFacts:
        msgs = render(
            "summarize_file", file_name=doc.name, kind=doc.kind, i=label, n=n, chunk_text=t
        )
        facts = await generate(llm, "summarize_file", msgs, FileFacts)
        check_evidence(facts.requirements, [doc.text], doc.name)
        for r in facts.requirements:  # 어느 파일 청크인지는 서버가 안다 (모델은 절 제목 등을 적음)
            r.source = doc.name
        return facts

    try:
        return [await one(text, str(i))], []
    except LLMInvalidOutput:
        return [], [f"형식 오류로 건너뜀: {doc.name} {i}/{n}"]
    except LLMContextTooLong:
        pass
    halves = chunking.split_text(
        text, counter, target=max(1, counter.count(text) // 2 + 1), overlap=0, single_max=0
    )
    out: list[FileFacts] = []
    warns: list[str] = []
    for k, half in enumerate(halves, start=1):
        try:
            out.append(await one(half, f"{i}-{k}"))
        except (LLMInvalidOutput, LLMContextTooLong):
            warns.append(f"길이·형식 문제로 건너뜀: {doc.name} {i}-{k}/{n}")
    return out, warns


async def _summarize(
    deps: Deps, llm: LLMClient, bid: Bid, docs: list[SourceDoc], files: list[BidFile]
) -> BidSummaryOut:
    counter = load_counter(deps.settings.llm_tokenizer_path)
    warnings = [f"읽지 못한 첨부: {f.name}" for f in files if f.status in ("failed", "unsupported")]
    readable: list[SourceDoc] = []
    for d in docs:
        if not d.text.strip():
            warnings.append(f"본문이 비어 읽지 못함: {d.name}")
            continue
        if len(d.text.strip()) < SCANNED_THRESHOLD:
            warnings.append(f"글자가 적어 스캔본일 수 있음: {d.name}")
        readable.append(d)

    pieces: list[tuple[SourceDoc, str, int, int]] = []
    for d in readable:
        parts = chunking.split_text(
            d.text, counter, target=CHUNK_TARGET, overlap=CHUNK_OVERLAP, single_max=SINGLE_MAX
        )
        pieces += [(d, t, i, len(parts)) for i, t in enumerate(parts, start=1)]
    picked, truncated = chunking.select_chunks(
        [p[1] for p in pieces], deps.settings.summary_max_chunks
    )
    if truncated:
        warnings.append(f"문서가 길어 {len(pieces)}개 부분 중 {len(picked)}개만 읽음")
    results = await asyncio.gather(*(_map_chunk(llm, *pieces[k], counter) for k in picked))
    facts: list[FileFacts] = []
    read: set[str] = set()
    for k, (got, warns) in zip(picked, results, strict=True):
        warnings += warns
        if got:
            facts += got
            read.add(pieces[k][0].sha)

    async def reduce(items: list[FileFacts]) -> BidSummaryOut:
        msgs = render(
            "summarize_bid",
            meta=json.dumps(bid_meta(bid), ensure_ascii=False),
            facts_list=json.dumps(
                [f.model_dump(exclude_defaults=True) for f in items], ensure_ascii=False
            ),
            n_read=len(read),
            n_total=len(files),
            truncated=truncated,
        )
        return await generate(llm, "summarize_bid", msgs, BidSummaryOut)

    try:
        out = await reduce(facts)
    except LLMContextTooLong:
        if len(facts) <= 1:
            raise
        warnings.append("요약 입력이 길어 일부 사실만 합침")
        out = await reduce(facts[: len(facts) // 2])

    if not read:
        warnings.append(NO_FILES if files else NO_DOCS)
    check_evidence(out.key_requirements, [d.text for d in readable], None)
    attach_sources(out.key_requirements, readable)
    removed = ground(
        out, [*(d.text for d in readable), json.dumps(bid_meta(bid), ensure_ascii=False)]
    )
    if removed:
        warnings.append(unverified_warning(removed))
    out.headline = (out.headline or bid.title)[:80]
    out.coverage = Coverage(
        files_read=len(read),
        files_total=len(files),
        truncated=truncated,
        # 첨부를 읽었는지는 서버가 정한다: 모델이 쓴 같은 경고는 버린다
        warnings=_dedupe(
            warnings + [w for w in out.coverage.warnings if w not in (NO_FILES, NO_DOCS)]
        ),
    )
    return out


async def get_or_create_summary(deps: Deps, bid_id: int) -> tuple[BidSummary, bool]:
    llm = _llm(deps)
    async with deps.db.session() as s:
        bid = await s.get(Bid, bid_id)
        files = list((await s.execute(select(BidFile).where(BidFile.bid_id == bid_id))).scalars())
    if bid is None:
        raise LookupError(f"공고 없음: {bid_id}")
    pending = [f for f in files if needs_work(f, deps)]
    if pending:
        usage.status("files", "첨부 파일을 내려받고 있어요", cache=False)
        await ensure_bid_files(deps, bid_id)
        usage.status("extract", "첨부 문서에서 글자를 뽑았어요", cache=False)
    usage.set_cache("file_text", not pending)

    source_hash, docs, rfp_files = await source_inputs(deps, bid)
    pv = prompt_version(SUMMARY_PROMPT, llm.model_id)
    where = (
        BidSummary.bid_id == bid_id,
        BidSummary.source_hash == source_hash,
        BidSummary.prompt_version == pv,
    )

    async def check() -> BidSummary | None:
        async with deps.db.session() as s:
            return (await s.execute(select(BidSummary).where(*where))).scalar_one_or_none()

    if (cached := await check()) is not None:
        usage.set_cache("summary", True)
        return cached, True
    if not pending:
        usage.status("files", "첨부 파일은 이미 받아 두었어요", cache=True)
        usage.status("extract", "추출한 본문을 재사용해요", cache=True)
    usage.status("summarize", "문서를 요약하고 있어요", cache=False)

    async def compute() -> BidSummary:
        with usage.track() as sub:
            out = await _summarize(deps, llm, bid, docs, rfp_files)
        async with deps.db.transaction() as s:
            await s.execute(
                insert(BidSummary)
                .values(
                    bid_id=bid_id,
                    source_hash=source_hash,
                    prompt_version=pv,
                    model_id=llm.model_id,
                    summary=out.model_dump(mode="json"),
                    input_tokens=sub.prompt_tokens,
                    output_tokens=sub.completion_tokens,
                )
                .on_conflict_do_nothing(
                    constraint="uq_bid_summaries_bid_id_source_hash_prompt_version"
                )
            )
        row = await check()
        assert row is not None
        return row

    row, hit = await single_flight(
        deps.db,
        f"summary:{bid_id}:{source_hash}:{pv}",
        check,
        compute,
        wait_s=deps.settings.llm_lock_wait_s,
    )
    usage.set_cache("summary", hit)
    return row, hit
