"""토큰 계산 (SPEC §8.3-1). Qwen 토크나이저(tokenizer.json)를 쓰고, 못 불러오면 글자 수 × 1.2."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class CharCounter:
    """대체 추정 [가정]: 한글 위주 문서에서 글자 수 × 1.2."""

    def count(self, text: str) -> int:
        return math.ceil(len(text) * 1.2)


class HFCounter:
    def __init__(self, tokenizer: Any) -> None:
        self._tok = tokenizer

    def count(self, text: str) -> int:
        return len(self._tok.encode(text, add_special_tokens=False).ids)


@lru_cache(maxsize=4)
def load_counter(path: str) -> TokenCounter:
    if not path or not Path(path).is_file():
        return CharCounter()
    try:
        from tokenizers import Tokenizer

        return HFCounter(Tokenizer.from_file(path))
    except Exception as e:  # 손상된 파일 등: 추정치로 계속
        log.warning("tokenizer load failed (%s), using chars*1.2", type(e).__name__)
        return CharCounter()
