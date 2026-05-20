import re
import json
import dataclasses
from typing import AsyncIterator, Optional
from app.llm.client import chat_stream
from app.pipeline.g2b_search import search_bids_structured, BidResult
from app.pipeline.file_extract import extract_and_compress
from app.db.models import Message

SEARCH_TRIGGERS = ["찾아줘", "검색해줘", "조회해줘", "알아봐줘", "분석해줘"]
_TRAILING_PARTICLES = re.compile(r'[을를이가은는의도에서로부터까지]\s*$')
_NOISE_SUFFIX = re.compile(r'\s+(RFP|제안요청서|제안서|계획서|사업의?|용역)\s*$', re.IGNORECASE)


def is_search_intent(message: str) -> bool:
    return any(t in message for t in SEARCH_TRIGGERS)


def _strip_keyword_noise(keyword: str) -> str:
    prev = None
    while keyword != prev:
        prev = keyword
        keyword = _NOISE_SUFFIX.sub('', keyword)
        keyword = _TRAILING_PARTICLES.sub('', keyword).strip()
    return keyword


def _extract_search_params(message: str) -> dict:
    keyword = message
    for t in SEARCH_TRIGGERS:
        keyword = keyword.replace(t, '')
    days = 90
    m = re.search(r'(\d+)\s*일', keyword)
    if m:
        days = int(m.group(1))
        keyword = keyword[:m.start()] + keyword[m.end():]
    keyword = _strip_keyword_noise(keyword)
    return {"keyword": keyword or message, "days": days}


def _build_history(messages: list[Message]) -> list[dict]:
    result = []
    for m in messages[-10:]:
        if m.step in ("search",):
            continue
        result.append({"role": m.role, "content": m.content})
    return result


async def run_pipeline(
    message: str,
    history: list[Message],
    selected_bid: Optional[dict],
    department_profile: Optional[str],
) -> AsyncIterator[str]:
    profile_text = department_profile or "부서 프로필 없음"

    # ── STEP 2: ANALYZE ───────────────────────────────────────────────────────
    if selected_bid:
        file_url = selected_bid.get("file_url", "")
        filename = selected_bid.get("filename", "document.hwp")
        bid_title = selected_bid.get("bid_title", "")
        bid_page_url = selected_bid.get("bid_page_url", "")

        _EXTRACT_FAIL = ("Text extraction unavailable", "Download failed",
                         "Unsupported file format", "PDF extraction failed",
                         "HWP extraction failed", "HWP Protected")

        compressed = None
        if file_url:
            yield f'data: {json.dumps({"type": "status", "content": "문서 다운로드 중..."}, ensure_ascii=False)}\n\n'
            compressed = await extract_and_compress(file_url, filename)
            if any(compressed.startswith(p) for p in _EXTRACT_FAIL):
                compressed = None

        sys_prompt = f"당신은 정부 조달 전문가입니다.\n부서 프로필: {profile_text}"
        if compressed:
            user_prompt = (
                f"[공고 제목]: {bid_title}\n\n"
                f"[공고 내용]:\n{compressed}\n\n"
                f"위 입찰 공고를 분석해주세요:\n"
                f"1. 적합성 평가 (우리 부서에 얼마나 적합한지)\n"
                f"2. 주요 요구사항 정리\n"
                f"3. 리스크 요인\n"
                f"4. 전략적 제언"
            )
        else:
            budget = selected_bid.get("budget", "")
            deadline = selected_bid.get("deadline", "")
            bid_number = selected_bid.get("bid_number", "")
            source = selected_bid.get("source", "")
            source_label = "사전규격" if source == "prespec" else "입찰공고"
            meta_lines = []
            if bid_number:
                meta_lines.append(f"공고번호: {bid_number}")
            if budget:
                try:
                    meta_lines.append(f"예산금액: {int(float(budget)):,}원")
                except (ValueError, TypeError):
                    meta_lines.append(f"예산금액: {budget}원")
            if deadline:
                meta_lines.append(f"마감일시: {deadline}")
            meta_lines.append(f"공고유형: {source_label}")
            if bid_page_url:
                meta_lines.append(f"나라장터 공고 페이지: {bid_page_url}")
            meta_block = "\n".join(meta_lines)
            user_prompt = (
                f"[공고 제목]: {bid_title}\n"
                f"[공고 정보]\n{meta_block}\n\n"
                f"※ 공고 원문 문서를 서버에서 자동 다운로드할 수 없었습니다. "
                f"아래 정보와 공고명을 바탕으로 분석하되, 원문 미확인 분석임을 답변 첫머리에 한 줄로 명시해주세요.\n\n"
                f"1. 적합성 평가 (공고명·예산 기준 예상)\n"
                f"2. 예상 주요 요구사항\n"
                f"3. 예산·일정 관련 주의사항\n"
                f"4. 입찰 전략 제언 및 나라장터에서 직접 문서 확인 권장"
            )

        messages_llm = [{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt}]
        async for chunk in chat_stream(messages_llm):
            yield f'data: {json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)}\n\n'

        yield f'data: {json.dumps({"type": "action", "content": "bookmark_prompt"}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
        return

    # ── STEP 1: SEARCH ────────────────────────────────────────────────────────
    if is_search_intent(message):
        yield f'data: {json.dumps({"type": "status", "content": "검색 중..."}, ensure_ascii=False)}\n\n'
        params = _extract_search_params(message)
        keyword = params["keyword"]
        days = params.get("days", 90)
        results = await search_bids_structured(keyword, days)
        if not results:
            words = keyword.split()
            for i in range(len(words) - 1, 0, -1):
                shorter = ' '.join(words[:i])
                results = await search_bids_structured(shorter, days)
                if results:
                    break
        cards = [dataclasses.asdict(r) for r in results]
        yield f'data: {json.dumps({"type": "cards", "content": cards}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
        return

    # ── STEP 3: CHAT ──────────────────────────────────────────────────────────
    last_analysis = next(
        (m.content for m in reversed(history) if m.step == "analyze"), None
    )
    analysis_ctx = f"\n[최근 분석 내용]:\n{last_analysis[:500]}" if last_analysis else ""
    sys_prompt = f"당신은 정부 조달 전문가입니다.\n부서 프로필: {profile_text}{analysis_ctx}"
    chat_history = _build_history(history)
    chat_history.append({"role": "user", "content": message})

    messages_llm = [{"role": "system", "content": sys_prompt}] + chat_history
    async for chunk in chat_stream(messages_llm):
        yield f'data: {json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)}\n\n'
    yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
