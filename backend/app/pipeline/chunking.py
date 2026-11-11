"""문서 청킹 (SPEC §8.3). 문서를 모두 읽되, 길면 중요한 부분을 먼저 읽는다.

- 한 파일이 single_max 이하이면 나누지 않는다 (§8.3-2).
- 경계 우선순위: '제N조'·'N.' 같은 번호 제목 → 빈 줄 → 줄 → 글자. 표 줄(|로 시작)은 묶어 둔다.
- 겹침: 다음 청크 앞에 이전 청크 끝 줄들을 overlap 토큰 이내로 다시 넣는다.
- 우선순위: 청크가 max_chunks를 넘으면 키워드 점수 상위만 읽고 원래 순서를 유지한다 [가정].
"""

from __future__ import annotations

import re

from app.llm.tokens import TokenCounter

TARGET_TOKENS = 12_000
OVERLAP_TOKENS = 500
INPUT_BUDGET = 24_000
PROMPT_OVERHEAD = 1_000  # 시스템 프롬프트·스키마 몫 [가정]
SINGLE_MAX = INPUT_BUDGET - PROMPT_OVERHEAD

PRIORITY_WORDS = (
    "평가",
    "배점",
    "제안요청",
    "과업",
    "사업기간",
    "추정금액",
    "사업비",
    "계약",
    "입찰참가자격",
    "제출",
    "일정",
    "기술평가",
    "가격평가",
)

_HEADING = re.compile(
    r"^\s*(제\s*\d+\s*[조장절관]|\d+(?:\.\d+)*\.\s|\d+\)\s|[IVX]+\.\s|[가-하]\.\s|【)"
)


def _is_table(line: str) -> bool:
    return line.lstrip().startswith("|")


def _sections(lines: list[str]) -> list[list[str]]:
    out: list[list[str]] = []
    for line in lines:
        if not out or (_HEADING.match(line) and any(x.strip() for x in out[-1])):
            out.append([])
        out[-1].append(line)
    return out


def _paragraphs(lines: list[str]) -> list[list[str]]:
    """빈 줄로 나누되 연속된 표 줄은 한 덩어리로 둔다."""
    out: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if not line.strip():
            if cur:
                out.append(cur)
            cur = []
            continue
        if cur and _is_table(line) != _is_table(cur[-1]):
            out.append(cur)
            cur = []
        cur.append(line)
    if cur:
        out.append(cur)
    return out


def _hard_split(line: str, counter: TokenCounter, target: int) -> list[str]:
    pieces: list[str] = []
    rest = line
    while rest:
        n = counter.count(rest)
        if n <= target:
            pieces.append(rest)
            break
        size = max(1, int(len(rest) * target / n))
        while size > 1 and counter.count(rest[:size]) > target:
            size = int(size * 0.9)
        pieces.append(rest[:size])
        rest = rest[size:]
    return pieces


def _pieces(text: str, counter: TokenCounter, target: int) -> list[str]:
    """target 이하 조각 목록. 큰 단위부터 작은 단위로 내려가며 나눈다."""
    out: list[str] = []
    for sec in _sections(text.split("\n")):
        sec_text = "\n".join(sec)
        if counter.count(sec_text) <= target:
            out.append(sec_text)
            continue
        for para in _paragraphs(sec):
            para_text = "\n".join(para)
            if counter.count(para_text) <= target:
                out.append(para_text)
                continue
            for line in para:
                out.extend(_hard_split(line, counter, target))
    return [p for p in out if p.strip()]


def _tail(chunk: str, counter: TokenCounter, overlap: int) -> str:
    lines: list[str] = []
    for line in reversed(chunk.split("\n")):
        candidate = "\n".join([line, *lines])
        if counter.count(candidate) > overlap:
            break
        lines.insert(0, line)
    return "\n".join(lines)


def split_text(
    text: str,
    counter: TokenCounter,
    *,
    target: int = TARGET_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    single_max: int = SINGLE_MAX,
) -> list[str]:
    if counter.count(text) <= single_max:
        return [text]
    chunks: list[str] = []
    cur = ""
    fresh = True  # cur가 겹침 부분만 담고 있는지
    for piece in _pieces(text, counter, target):
        candidate = f"{cur}\n{piece}" if cur else piece
        if counter.count(candidate) <= target:
            cur, fresh = candidate, False
            continue
        if cur and not fresh:
            chunks.append(cur)
        tail = _tail(cur, counter, overlap) if overlap and cur and not fresh else ""
        cur = f"{tail}\n{piece}" if tail and counter.count(f"{tail}\n{piece}") <= target else piece
        fresh = False
    if cur and not fresh:
        chunks.append(cur)
    return chunks


def chunk_score(text: str) -> int:
    return sum(text.count(w) for w in PRIORITY_WORDS)


def select_chunks(chunks: list[str], max_chunks: int) -> tuple[list[int], bool]:
    """(읽을 청크 인덱스(원래 순서), 잘렸는지)."""
    if len(chunks) <= max_chunks:
        return list(range(len(chunks))), False
    ranked = sorted(range(len(chunks)), key=lambda i: (-chunk_score(chunks[i]), i))
    return sorted(ranked[:max_chunks]), True
