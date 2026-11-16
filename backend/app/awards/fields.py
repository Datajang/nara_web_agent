"""분야 태그 분류 (SPEC §15.3 `fields`). org_settings.field_keywords 사전으로 공고명을 분류한다.

사전 모양: {"데이터 정비": ["데이터 정비", "DB 구축"], "AI 분석": ["인공지능", "AI"]}.
공고명과 키워드 모두 공백을 빼고 소문자로 비교한다. 결과는 태그 이름순(같은 입력 → 같은 출력).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SPACE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _SPACE.sub("", s).lower()


def clean_keywords(raw: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """jsonb 값을 {태그: [키워드]}로 정리. 빈 태그·빈 키워드·문자열이 아닌 값은 버린다."""
    out: dict[str, list[str]] = {}
    for tag, words in (raw or {}).items():
        if not isinstance(tag, str) or not tag.strip() or not isinstance(words, list):
            continue
        kept = [w.strip() for w in words if isinstance(w, str) and w.strip()]
        if kept:
            out[tag.strip()] = kept
    return out


def classify(title: str, keywords: Mapping[str, list[str]]) -> list[str]:
    t = _norm(title)
    return sorted(tag for tag, words in keywords.items() if any(_norm(w) in t for w in words))
