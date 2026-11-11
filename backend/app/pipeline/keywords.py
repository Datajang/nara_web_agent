"""프로필 설명 → 검색 키워드 제안 (SPEC §8.5 suggest_keywords). 저장하지 않는다."""

from __future__ import annotations

from app.deps import Deps
from app.llm.prompts import render
from app.llm.schemas import KeywordSuggestion
from app.llm.structured import generate
from app.pipeline.summarize import _llm
from app.profiles.hashing import normalize_profile


async def suggest_keywords(deps: Deps, description: str) -> list[str]:
    msgs = render("suggest_keywords", profile_description=normalize_profile(description))
    out = await generate(_llm(deps), "suggest_keywords", msgs, KeywordSuggestion)
    cleaned = [k.strip()[:50] for k in out.keywords if k.strip()]
    return list(dict.fromkeys(cleaned))[:10]
