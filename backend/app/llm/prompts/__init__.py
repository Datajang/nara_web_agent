"""프롬프트 템플릿 로더 (SPEC §8.5). `[시스템]`·`[사용자]` 절로 나눈 .md 파일을 읽는다.

데이터는 구분자(<document> 등)로 감싸고, 값 안의 구분자 태그는 전각 괄호로 바꿔 무력화한다
(데이터가 구분자를 닫고 지시문을 끼워 넣지 못하게, §8.1-3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.base import Message

_DIR = Path(__file__).resolve().parent
_TAGS = re.compile(
    r"<(/?)(document|profile|bids|bid_meta|summary|file_facts|coverage|tool_result)>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str


def _load(path: Path) -> Prompt:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"\s*\[시스템\]\n(.*?)(?:\n\[사용자\]\n(.*))?\Z", raw, re.DOTALL)
    if m is None:
        raise ValueError(f"프롬프트 형식 오류: {path.name}")
    return Prompt(system=m.group(1).strip(), user=(m.group(2) or "").strip())


PROMPTS: dict[str, Prompt] = {p.stem: _load(p) for p in sorted(_DIR.glob("*.md"))}


def fence(value: Any) -> str:
    """데이터 값 안의 구분자 태그를 무력화한다."""
    return _TAGS.sub(lambda m: f"＜{m.group(1)}{m.group(2)}＞", str(value))


def system_text(name: str, **values: Any) -> str:
    return PROMPTS[name].system.format_map({k: fence(v) for k, v in values.items()})


def render(name: str, **values: Any) -> list[Message]:
    p = PROMPTS[name]
    safe = {k: fence(v) for k, v in values.items()}
    return [
        {"role": "system", "content": p.system.format_map(safe)},
        {"role": "user", "content": p.user.format_map(safe)},
    ]
