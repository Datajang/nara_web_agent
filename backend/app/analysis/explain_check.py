"""AI 해설 숫자 검증 (SPEC §15.8, §15.11 수용 기준 6). LLM 없이 정규식으로만.

해설의 모든 숫자는 입력(GET /compare 응답 JSON)에 있는 값이어야 한다.
- 글의 숫자를 값·정밀도로 읽는다: '7억' = 7×10⁸ ± 0.5×10⁸, '5.9억' ± 0.05×10⁸, '1억 2천만원'은 합,
  '700,000,000원' ± 0.5. 표시 자릿수 안에서 입력 값과 같으면 통과(반올림한 표기 허용)
- '%'가 붙은 숫자는 입력 값 그대로이거나 비율(0~1) × 100과 같아야 한다
- 입력의 숫자: JSON의 수 전부 + 문자열 속 숫자(날짜 '2026-11-10'의 2026·11·10 등)
- 영문·밑줄에 붙은 숫자('G2B', 'ratio_20')는 숫자로 보지 않는다
- 권유·예측 표현(투찰하세요, 가능성 등)도 함께 막는다(§15.8 '권유를 하지 않고')
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_UNITS = {"조": 10**12, "억": 10**8, "천만": 10**7, "백만": 10**6, "만": 10**4, "천": 10**3}
_TERM = re.compile(
    r"(?<![0-9A-Za-z_.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![0-9A-Za-z_])"
    r"\s*(조|억|천만|백만|만|천)?"
)
_PCT = re.compile(r"\s*(%|퍼센트|프로)")
BANNED = ("투찰하", "투찰가", "투찰 가격", "가능성", "확률", "권합니다", "추천")


@dataclass(frozen=True)
class Num:
    text: str
    value: Decimal
    precision: Decimal  # 표시한 마지막 자리의 크기('5.9억' → 0.1억)
    pct: bool


def numbers(text: str) -> list[Num]:
    """글 속 숫자. '1억 2천만'처럼 단위가 작아지며 이어지면 하나로 합친다."""
    out: list[Num] = []
    ms = list(_TERM.finditer(text))
    i = 0
    while i < len(ms):
        m = ms[i]
        start, value, prec, last_unit = m.start(), Decimal(0), Decimal(1), None
        j = i
        while j < len(ms):
            mm = ms[j]
            unit = _UNITS.get(mm.group(3) or "", 1)
            if j > i and (
                last_unit is None
                or not mm.group(3)
                or unit >= last_unit
                or text[ms[j - 1].end() : mm.start()].strip()
            ):
                break
            frac = mm.group(2) or ""
            n = Decimal(mm.group(1).replace(",", "") + (f".{frac}" if frac else ""))
            value += n * unit
            prec = Decimal(unit) / (Decimal(10) ** len(frac))
            last_unit = unit if mm.group(3) else None
            j += 1
            if last_unit is None:
                break
        end = ms[j - 1].end()
        pct = bool(_PCT.match(text, end))
        out.append(Num(text[start:end].strip(), value, prec, pct))
        i = j
    return out


def _walk(v: Any, out: set[Decimal]) -> None:
    if isinstance(v, bool) or v is None:
        return
    if isinstance(v, int | float):
        out.add(Decimal(str(v)))
    elif isinstance(v, str):
        out.update(n.value for n in numbers(v))
    elif isinstance(v, dict):
        for x in v.values():
            _walk(x, out)
    elif isinstance(v, list | tuple):
        for x in v:
            _walk(x, out)


def allowed_values(payload: Any) -> set[Decimal]:
    out: set[Decimal] = set()
    _walk(payload, out)
    return out


def _ok(n: Num, allowed: Iterable[Decimal]) -> bool:
    half = n.precision / 2
    for v in allowed:
        if abs(n.value - v) <= half:
            return True
        if n.pct and abs(n.value - v * 100) <= half:
            return True
    return False


def unsupported(texts: Iterable[str], payload: Any) -> list[str]:
    """입력에 없는 숫자(표기 그대로). 비어 있으면 통과."""
    allowed = allowed_values(payload)
    bad: list[str] = []
    for t in texts:
        for n in numbers(t):
            if not _ok(n, allowed) and n.text not in bad:
                bad.append(n.text)
    return bad


def banned_phrases(texts: Iterable[str]) -> list[str]:
    joined = "\n".join(texts)
    return [w for w in BANNED if w in joined]
