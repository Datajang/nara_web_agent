"""AI 해설 숫자 검증 (SPEC §15.8, §15.11 수용 기준 6). LLM 없이 정규식으로만.

해설의 모든 숫자는 입력(GET /compare 응답 JSON)에 있는 값이어야 한다.
- 글의 숫자를 값·표시 자릿수로 읽는다: '7억', '5.9억', '1억 2천만원'·'169억 2,088만 9,000원'은 합.
  입력 값을 그 자릿수로 반올림하거나 버린 값이면 통과(x − 자릿수/2 ≤ 입력 < x + 자릿수).
  '7억'은 6.5억~8억 미만이라 '8억'은 7억과 다르다 (실제 모델은 '약 4억 7,963만'처럼 버림이 흔함)
- '%'가 붙은 숫자는 입력 값 그대로이거나 비율(0~1) × 100과 같아야 한다
- 입력의 숫자: JSON의 수 전부 + 문자열 속 숫자(날짜 '2026-11-10'·'2026-11-10T09:00'의 2026·11·10 등)
- 영문·밑줄에 붙은 숫자('G2B', 'ratio_20')는 숫자로 보지 않는다
- 권유·예측 표현(투찰하세요, 가능성 등)과 글로 쓴 배수('두 배', '배 가까이')도 함께 막는다
  (§15.8 '권유를 하지 않고', 숫자를 새로 만들지 않음)
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
_WON = re.compile(r"\s*원")
_LIST_MARK = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")  # 마크다운 번호 목록 '3. …'은 숫자가 아니다
_ISO_T = re.compile(r"(?<=\d)T(?=\d)")  # 2026-11-12T03:00 → 날짜·시각을 나눠 읽는다
BANNED = ("투찰하", "투찰가", "투찰 가격", "가능성", "확률", "권합니다", "추천")
_BANNED_RE = re.compile(r"(두|세|네|다섯|여러)\s?배|배\s?(가까이|이상|넘게|많|적|차이)")


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
            # 단위 없는 끝자리('…만 9,000원')는 바로 뒤에 '원'이 있을 때만 앞 금액에 붙인다
            tail = not mm.group(3) and bool(_WON.match(text, mm.end()))
            if j > i and (
                last_unit is None
                or (not mm.group(3) and not tail)
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
        out.update(n.value for n in numbers(_ISO_T.sub(" ", v)))
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


def _near(x: Decimal, p: Decimal, v: Decimal) -> bool:
    """x(자릿수 p)가 v를 반올림하거나 버린 표기인가."""
    return x - p / 2 <= v < x + p


def _ok(n: Num, allowed: Iterable[Decimal]) -> bool:
    for v in allowed:
        if _near(n.value, n.precision, v) or (n.pct and _near(n.value, n.precision, v * 100)):
            return True
    return False


def unsupported(texts: Iterable[str], payload: Any) -> list[str]:
    """입력에 없는 숫자(표기 그대로). 비어 있으면 통과."""
    allowed = allowed_values(payload)
    bad: list[str] = []
    for t in texts:
        for n in numbers(_LIST_MARK.sub("", t)):
            if not _ok(n, allowed) and n.text not in bad:
                bad.append(n.text)
    return bad


def multipliers(texts: Iterable[str]) -> list[str]:
    """글로 쓴 배수('두 배', '배 가까이'). 숫자를 새로 만든 표현."""
    return [m.group(0) for m in _BANNED_RE.finditer("\n".join(texts))]


def banned_phrases(texts: Iterable[str]) -> list[str]:
    joined = "\n".join(texts)
    return [w for w in BANNED if w in joined] + [m.group(0) for m in _BANNED_RE.finditer(joined)]


# 문장 끝: 숫자가 아닌 글자 뒤의 . ! ? ('1.5'·'3. ' 목록 번호는 자르지 않는다)
_SENT_END = re.compile(r"(?<=[^\d\s][.!?])\s+")


def keep_supported(text: str, payload: Any) -> tuple[str, int]:
    """입력에 없는 숫자나 글로 쓴 배수가 든 문장만 뺀 글과 뺀 문장 수 (어시스턴트 답용).

    줄 단위로 나눈 뒤 문장으로 나눈다. 표·목록의 한 줄도 한 문장으로 본다.
    """
    lines: list[str] = []
    dropped = 0
    for line in text.split("\n"):
        parts = [p for p in _SENT_END.split(line) if p.strip()]
        kept = [p for p in parts if not unsupported([p], payload) and not multipliers([p])]
        dropped += len(parts) - len(kept)
        if kept or not parts:
            lines.append(" ".join(kept) if kept else line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip(), dropped


_UNIT_GAP = re.compile(r"(\d)\s+(?=(?:건|곳|개|원|년|월|일|회|억|천만|백만|만|천|%))")
# tool_choice='none' 라운드에서 실제 모델이 도구 호출을 글로 쓴 것 (Qwen XML 형식)
_TOOL_TEXT = re.compile(r"<tool_call>.*?(?:</tool_call>|\Z)", re.S)


def tidy(text: str) -> str:
    """'14 건', '2026 년' → '14건', '2026년'. 숫자 값은 바꾸지 않는다(실제 모델이 띄어 씀)."""
    return _UNIT_GAP.sub(r"\1", text)


def strip_tool_text(text: str) -> str:
    """답에 글로 섞인 도구 호출(<tool_call>…)을 지운다."""
    return _TOOL_TEXT.sub("", text).strip()
