"""두 회사 낙찰 비교 · 강점/약점 판정 (SPEC §15.5). 순수 함수 — DB·LLM 없음.

입력은 두 회사의 낙찰 행(같은 기간)과 '두 회사가 모두 참가한 공고' 키 목록, 출력은 항목별 판정과
강점·약점. 같은 입력이면 항상 같은 출력이다(정렬·동점 처리를 모두 키로 고정).

규칙:
- 비율 규칙: rel = (우리 − 상대) / max(우리, 상대). 둘 다 0이면 '비슷', |rel| ≤ 0.2 '비슷',
  rel > 0.2 '앞섬', rel < −0.2 '뒤처짐'.
- 분야 규칙: 두 회사 건수 합이 3 미만이면 판정 없이 '표본 적음'. 아니면 큰 쪽이 작은 쪽의 2배 이상
  (작은 쪽이 0이면 큰 쪽이 2 이상)일 때만 앞섬·뒤처짐, 나머지는 '비슷'.
- 맞대결 규칙: 맞붙은 공고가 1건 이상이면 낙찰 수가 많은 쪽이 '앞섬', 같으면 '비슷',
  5건 미만이면 '표본 적음'을 함께 붙인다. 맞붙은 공고가 없으면 '참고'.
- 낙찰률(G2B)·낙찰금액/추정가격 중앙값, 공동수급 비중은 '참고'(판정 없음).
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Verdict = Literal["up", "same", "down", "info"]
AwardKey = tuple[str, str, str, str]  # (공고번호, 차수, 분류, 재입찰)

RATIO_THRESHOLD = 0.2
FIELD_MIN_TOTAL = 3
FIELD_FACTOR = 2
H2H_MIN = 5
MAX_CARDS = 5

LABELS = {
    "count": "낙찰 건수",
    "amount_sum": "낙찰금액 합계",
    "amount_avg": "건당 평균 낙찰금액",
    "org_count": "낙찰한 수요기관 수",
    "head_to_head": "직접 맞붙은 공고",
    "g2b_rate_median": "낙찰률(G2B) 중앙값",
    "ratio_median": "낙찰금액/추정가격 중앙값",
    "joint_share": "공동수급 비중",
}


@dataclass(frozen=True)
class AwardFact:
    """판정에 쓰는 낙찰 한 행의 사실만."""

    key: AwardKey
    amount: int | None
    dminstt_cd: str | None
    fields: tuple[str, ...] = ()
    g2b_rate: Decimal | None = None
    ratio: Decimal | None = None
    is_joint: bool = False


@dataclass(frozen=True)
class Metrics:
    count: int
    amount_sum: int
    amount_avg: int
    org_count: int
    by_field: dict[str, int]
    g2b_rate_median: float | None
    ratio_median: float | None
    joint_share: float | None


@dataclass(frozen=True)
class VerdictRow:
    key: str
    label: str
    us: float | None
    them: float | None
    verdict: Verdict
    rule: Literal["ratio_20", "field_2x", "head_to_head", "info"]
    small_sample: bool = False
    rel: float = 0.0  # 강점·약점 정렬용 (us − them) / max


@dataclass(frozen=True)
class HeadToHead:
    matched: int  # 두 회사가 모두 참가한(개찰 결과를 조회한) 공고 수
    us_wins: int
    them_wins: int


@dataclass(frozen=True)
class Comparison:
    us: Metrics
    them: Metrics
    head_to_head: HeadToHead
    verdicts: list[VerdictRow] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


def _median(values: Iterable[Decimal | None]) -> float | None:
    vs = sorted(float(v) for v in values if v is not None)
    return round(statistics.median(vs), 5) if vs else None


def metrics(rows: Sequence[AwardFact]) -> Metrics:
    count = len(rows)
    total = sum(r.amount or 0 for r in rows)
    by_field: dict[str, int] = {}
    for r in rows:
        for f in set(r.fields):
            by_field[f] = by_field.get(f, 0) + 1
    return Metrics(
        count=count,
        amount_sum=total,
        amount_avg=round(total / count) if count else 0,
        org_count=len({r.dminstt_cd for r in rows if r.dminstt_cd}),
        by_field=dict(sorted(by_field.items())),
        g2b_rate_median=_median(r.g2b_rate for r in rows),
        ratio_median=_median(r.ratio for r in rows),
        joint_share=round(sum(r.is_joint for r in rows) / count, 4) if count else None,
    )


def rel(us: float, them: float) -> float:
    big = max(us, them)
    return 0.0 if big <= 0 else (us - them) / big


def ratio_verdict(us: float, them: float) -> Verdict:
    r = rel(us, them)
    if r > RATIO_THRESHOLD:
        return "up"
    if r < -RATIO_THRESHOLD:
        return "down"
    return "same"


def field_verdict(us: int, them: int) -> tuple[Verdict, bool]:
    """(판정, 표본 적음). 표본이 적으면 판정하지 않는다('info')."""
    if us + them < FIELD_MIN_TOTAL:
        return "info", True
    big, small = max(us, them), min(us, them)
    decisive = big >= FIELD_FACTOR if small == 0 else big >= FIELD_FACTOR * small
    if not decisive or us == them:
        return "same", False
    return ("up" if us > them else "down"), False


def h2h_verdict(h: HeadToHead) -> tuple[Verdict, bool]:
    if h.matched < 1:
        return "info", True
    if h.us_wins == h.them_wins:
        v: Verdict = "same"
    else:
        v = "up" if h.us_wins > h.them_wins else "down"
    return v, h.matched < H2H_MIN


def head_to_head(
    us_rows: Sequence[AwardFact], them_rows: Sequence[AwardFact], shared: Iterable[AwardKey]
) -> HeadToHead:
    keys = set(shared)
    return HeadToHead(
        matched=len(keys),
        us_wins=sum(1 for r in us_rows if r.key in keys),
        them_wins=sum(1 for r in them_rows if r.key in keys),
    )


def compare(
    us_rows: Sequence[AwardFact],
    them_rows: Sequence[AwardFact],
    shared: Iterable[AwardKey] = (),
) -> Comparison:
    us, them = metrics(us_rows), metrics(them_rows)
    h = head_to_head(us_rows, them_rows, shared)
    rows: list[VerdictRow] = []
    for key in ("count", "amount_sum", "amount_avg", "org_count"):
        a, b = float(getattr(us, key)), float(getattr(them, key))
        rows.append(
            VerdictRow(key, LABELS[key], a, b, ratio_verdict(a, b), "ratio_20", rel=rel(a, b))
        )
    for tag in sorted(set(us.by_field) | set(them.by_field)):
        a_i, b_i = us.by_field.get(tag, 0), them.by_field.get(tag, 0)
        v, small = field_verdict(a_i, b_i)
        rows.append(VerdictRow(f"field:{tag}", tag, a_i, b_i, v, "field_2x", small, rel(a_i, b_i)))
    v, small = h2h_verdict(h)
    rows.append(
        VerdictRow(
            "head_to_head",
            LABELS["head_to_head"],
            h.us_wins,
            h.them_wins,
            v,
            "head_to_head",
            small,
            rel(h.us_wins, h.them_wins),
        )
    )
    for key in ("g2b_rate_median", "ratio_median", "joint_share"):
        rows.append(
            VerdictRow(key, LABELS[key], getattr(us, key), getattr(them, key), "info", "info")
        )

    def pick(verdict: Verdict) -> list[str]:
        hits = [r for r in rows if r.verdict == verdict]
        hits.sort(key=lambda r: (-abs(r.rel), r.key))
        return [r.key for r in hits[:MAX_CARDS]]

    return Comparison(us, them, h, rows, pick("up"), pick("down"))


# ---------- 경쟁사 레이더 겹침도 (§15.5) ----------

ORG_WEIGHT = 0.6
FIELD_WEIGHT = 0.4
MIN_CANDIDATE_AWARDS = 2


def overlap_score(org_overlap: float, field_overlap: float) -> float:
    """0~100. 수요기관 겹침·분야 겹침은 각각 0~1(우리 낙찰 중 겹치는 건의 비율)."""
    return round(100 * (ORG_WEIGHT * org_overlap + FIELD_WEIGHT * field_overlap), 1)
