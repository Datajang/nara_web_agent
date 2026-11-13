"""AI 출력의 금액·날짜 원문 대조 (docs/decisions/2026-11-13-official-facts.md, SPEC §8.4·§8.8-2).

원문(첨부 텍스트 + G2B 메타)에 문자열로 없는 금액·날짜는 화면에 내지 않는다.
- 선택 칸(`str | None`)은 비운다
- 목록 항목(문자열·요구사항·리스크·일정)은 뺀다. 일정은 날짜·원문 표기가 모두 없어지면 뺀다
- 필수 글(개요 등)은 그 문장만 뺀다
계약 방식은 보기 이름이 원문에 있어야 남긴다(띄어쓰기 무시).
평가(eval/run_eval.py)도 같은 함수를 쓴다.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel

_UNIT = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000, "만": 10_000, "천": 1_000}
_KR_AMOUNT = re.compile(r"((?:\d[\d,]*(?:\.\d+)?\s*(?:억|천만|백만|만|천)\s*)+)원")
_PLAIN_AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d{5,})\s*원")
_DATE = re.compile(r"(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")
# 문장 끝: 숫자 뒤의 점('2026. 12. 8.')은 날짜라 자르지 않는다
_SENTENCE = re.compile(r"(?<=[^\d\s][.!?])\s+")
# 원문에 이름이 있어야 남기는 칸 (모델명, 필드명)
_MUST_APPEAR = {("BudgetContract", "contract_method")}


def amounts(text: str) -> set[int]:
    """'100,000,000원', '1억 2천만원', '5,000만원' → 원 단위 정수. 원이 붙은 것만 금액으로 본다."""
    out: set[int] = set()
    for m in _KR_AMOUNT.finditer(text):
        total = 0.0
        for num, unit in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*(억|천만|백만|만|천)", m.group(1)):
            total += float(num.replace(",", "")) * _UNIT[unit]
        out.add(int(total))
    for m in _PLAIN_AMOUNT.finditer(text):
        out.add(int(m.group(1).replace(",", "")))
    return out


def dates(text: str) -> set[str]:
    out: set[str] = set()
    for y, mo, d in _DATE.findall(text):
        try:
            out.add(date(int(y), int(mo), int(d)).isoformat())
        except ValueError:
            continue
    return out


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


@dataclass(frozen=True)
class _Source:
    amounts: set[int]
    dates: set[str]
    squashed: str

    def ok(self, text: str) -> bool:
        return amounts(text) <= self.amounts and dates(text) <= self.dates


def _sentences(text: str, src: _Source) -> str:
    return " ".join(s for s in _SENTENCE.split(text.strip()) if src.ok(s))


def _optional(model: BaseModel, name: str) -> bool:
    f = type(model).model_fields[name]
    return not f.is_required() and f.default is None


def _useless(item: BaseModel) -> bool:
    """대조 뒤 쓸모가 없어진 목록 항목: 필수 글이 비었거나, 일정에 날짜·원문 표기가 모두 없음."""
    fields = type(item).model_fields
    if any(getattr(item, n) == "" for n, f in fields.items() if f.is_required()):
        return True
    return {"date", "raw"} <= fields.keys() and not item.date and not item.raw  # type: ignore[attr-defined]


def _walk(model: BaseModel, src: _Source) -> int:
    removed = 0
    for name in type(model).model_fields:
        v = getattr(model, name)
        if isinstance(v, str):
            must = (type(model).__name__, name) in _MUST_APPEAR
            if src.ok(v) and not (must and _squash(v) not in src.squashed):
                continue
            removed += 1
            setattr(model, name, None if _optional(model, name) else _sentences(v, src))
        elif isinstance(v, BaseModel):
            removed += _walk(v, src)
        elif isinstance(v, list):
            kept = []
            for x in v:
                if isinstance(x, str):
                    if not src.ok(x):
                        removed += 1
                        continue
                elif isinstance(x, BaseModel):
                    inner = _walk(x, src)
                    if _useless(x):
                        removed += max(inner, 1)
                        continue
                    removed += inner
                kept.append(x)
            setattr(model, name, kept)
    return removed


def unverified_warning(n: int) -> str:
    return f"원문에서 확인되지 않은 숫자·날짜 {n}개를 뺐어요"


def ground(model: BaseModel, sources: Iterable[str]) -> int:
    """원문에 없는 금액·날짜를 걷어 내고 걷어 낸 수를 돌려준다. model을 직접 고친다."""
    text = "\n".join(sources)
    return _walk(model, _Source(amounts(text), dates(text), _squash(text)))
