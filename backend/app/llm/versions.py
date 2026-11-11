"""PROMPT_VERSION (SPEC §4·§12.3). 모델 접미사를 붙여, 모델이나 프롬프트가 바뀌면 캐시가 자연히
분리된다.

P1 값은 캐시 계약 검증용 자리표시. 실제 프롬프트·스키마는 P3(§8)에서 정하고 이 값을 올린다.
"""

SUMMARY_PROMPT = "summary-p1"
ANALYSIS_PROMPT = "analysis-p1"
SCORE_PROMPT = "score-p1"


def prompt_version(base: str, model_id: str) -> str:
    return f"{base}+{model_id}"


def bid_ref(bid_id: int) -> str:
    """LLM에는 URL·경로 대신 짧은 ID만 준다 (규칙 6)."""
    return f"b{bid_id}"


def parse_bid_ref(ref: object) -> int | None:
    s = str(ref).strip()
    return int(s[1:]) if s.startswith("b") and s[1:].isdigit() else None
