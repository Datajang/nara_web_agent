"""PROMPT_VERSION (SPEC §4·§8.1-5). 모델 접미사를 붙여, 모델이나 프롬프트가 바뀌면 캐시가 자연히
분리된다 (예: v1+q35-9b). 프롬프트(llm/prompts/*.md)를 고치면 해당 값을 올린다.
"""

# v5: G2B 공고 정보 메타·원문 대조·계약 방식 보기, v4: 일정 날짜 형식 (2026-11-13)
# v3: 출력 길이 상한(CAPS), v2: 모든 필드 required (2026-11-12)
PROMPT_VERSION = "v5"
SUMMARY_PROMPT = PROMPT_VERSION
ANALYSIS_PROMPT = PROMPT_VERSION
SCORE_PROMPT = PROMPT_VERSION


def prompt_version(base: str, model_id: str) -> str:
    return f"{base}+{model_id}"


def bid_ref(bid_id: int) -> str:
    """LLM과 API에는 URL·경로 대신 짧은 ID만 준다 (규칙 6)."""
    return f"b{bid_id}"


def parse_bid_ref(ref: object) -> int | None:
    s = str(ref).strip()
    return int(s[1:]) if s.startswith("b") and s[1:].isdigit() and len(s) < 19 else None
