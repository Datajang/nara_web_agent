import json
import dataclasses
from typing import AsyncIterator, Optional
from app.llm.client import chat_complete, chat_stream
from app.pipeline.g2b_search import search_bids_structured, BidResult
from app.pipeline.file_extract import extract_and_compress
from app.db.models import Message

SEARCH_TRIGGERS = ["찾아줘", "검색해줘", "조회해줘", "알아봐줘"]


def is_search_intent(message: str, current_step: Optional[str]) -> bool:
    if current_step == "chat":
        return False
    return any(t in message for t in SEARCH_TRIGGERS)


def _get_current_step(messages: list[Message]) -> Optional[str]:
    for m in reversed(messages):
        if m.role == "assistant":
            return m.step
    return None


async def _extract_search_params(message: str) -> dict:
    prompt = (
        f'다음 메시지에서 검색 키워드와 기간(일수)을 JSON으로 추출하세요.\n'
        f'메시지: {message}\n'
        f'형식: {{"keyword": "검색어", "days": 30}}\n'
        f'days가 명시되지 않으면 30을 사용하세요. JSON만 반환하세요.'
    )
    raw = await chat_complete(
        [{"role": "system", "content": "당신은 JSON 추출 어시스턴트입니다. 반드시 JSON만 반환하세요."},
         {"role": "user", "content": prompt}],
        max_tokens=100,
    )
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except Exception:
        words = message.split()
        keyword = next((w for w in words if len(w) > 1 and w not in SEARCH_TRIGGERS), words[0] if words else "")
        return {"keyword": keyword, "days": 30}


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
    current_step = _get_current_step(history)
    profile_text = department_profile or "부서 프로필 없음"

    # ── STEP 2: ANALYZE ───────────────────────────────────────────────────────
    if selected_bid:
        file_url = selected_bid.get("file_url", "")
        filename = selected_bid.get("filename", "document.hwp")
        bid_title = selected_bid.get("bid_title", "")

        yield f'data: {json.dumps({"type": "status", "content": "문서 다운로드 중..."}, ensure_ascii=False)}\n\n'
        compressed = await extract_and_compress(file_url, filename)

        sys_prompt = f"당신은 정부 조달 전문가입니다.\n부서 프로필: {profile_text}"
        user_prompt = (
            f"[공고 제목]: {bid_title}\n\n"
            f"[공고 내용]:\n{compressed}\n\n"
            f"위 입찰 공고를 분석해주세요:\n"
            f"1. 적합성 평가 (우리 부서에 얼마나 적합한지)\n"
            f"2. 주요 요구사항 정리\n"
            f"3. 리스크 요인\n"
            f"4. 전략적 제언"
        )
        messages_llm = [{"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt}]
        async for chunk in chat_stream(messages_llm):
            yield f'data: {json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)}\n\n'

        yield f'data: {json.dumps({"type": "action", "content": "bookmark_prompt"}, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'
        return

    # ── STEP 1: SEARCH ────────────────────────────────────────────────────────
    if is_search_intent(message, current_step):
        yield f'data: {json.dumps({"type": "status", "content": "검색 중..."}, ensure_ascii=False)}\n\n'
        params = await _extract_search_params(message)
        results = await search_bids_structured(params["keyword"], params.get("days", 30))
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
