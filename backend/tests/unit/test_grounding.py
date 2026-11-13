"""AI 출력의 금액·날짜는 원문(첨부 텍스트+메타)에 있는 것만 남긴다
(docs/decisions/2026-11-13-official-facts.md, §8.8-2를 평가에서 서비스로 옮김)."""

from app.llm.schemas import (
    AnalysisResult,
    BidSummary,
    BudgetContract,
    Coverage,
    Evaluation,
    Fit,
    Requirement,
    Risk,
    ScheduleItem,
)
from app.pipeline.grounding import amounts, dates, ground

SRC = [
    "사업예산: 226,842,000원(부가가치세 포함). 제안서 평가위원회 개최 2026. 12. 8.(화) 14:00. "
    "계약방법 : 제한경쟁입찰(협상에의한계약). 하자보수 기간 1년. 착수보고 계약 후 14일 이내.",
    '{"deadline": "2026-11-24 10:00", "assigned_budget": "99,000,000원"}',  # 메타
]


def _summary(**kw) -> BidSummary:
    base = dict(
        headline="HPC 유지보수",
        overview=(
            "사업비는 226,842,000원입니다. 마감은 2026년 12월 30일입니다. "
            "하드웨어를 유지보수합니다."
        ),
        coverage=Coverage(files_read=1, files_total=1),
    )
    return BidSummary(**{**base, **kw})


def test_amount_and_date_parsing_matches_korean_notation():
    assert amounts("1,227,710천원 범위") == {1_227_710_000}
    assert amounts("총사업비 9,900만 원") == {99_000_000}
    assert dates("2026. 12. 8.(화) 14:00") == {"2026-12-08"}


def test_sentences_with_unverified_numbers_are_removed_from_free_text():
    s = _summary()
    removed = ground(s, SRC)
    assert s.overview == "사업비는 226,842,000원입니다. 하드웨어를 유지보수합니다."
    assert removed == 1


def test_optional_fields_are_emptied_and_list_items_dropped():
    s = _summary(
        budget_contract=BudgetContract(
            budget_text="206,220,000원",  # 원문에 없음(추정가격) → 비움
            payment_terms="선금 30%",  # 금액·날짜 없음 → 그대로
            period="2026. 12. 8.부터",
        ),
        schedule=[
            ScheduleItem(label="평가위원회", date="2026-12-08", raw="2026. 12. 8.(화) 14:00"),
            ScheduleItem(label="계약", date="2026-12-20", raw=None),  # 날짜가 원문에 없음 → 항목째
            ScheduleItem(label="착수보고", date=None, raw="계약 후 14일 이내"),  # 숫자만, 날짜 아님
        ],
        key_requirements=[
            Requirement(text="하자보수 1년"),
            Requirement(text="지체상금 5,000,000원 부과"),  # 원문에 없는 금액 → 빠짐
        ],
        eligibility=["2026년 11월 1일 이전 등록 업체"],  # 원문에 없는 날짜
    )
    removed = ground(s, SRC)
    assert s.budget_contract.budget_text is None
    assert s.budget_contract.payment_terms == "선금 30%"
    assert s.budget_contract.period == "2026. 12. 8.부터"
    assert [i.label for i in s.schedule] == ["평가위원회", "착수보고"]
    assert [r.text for r in s.key_requirements] == ["하자보수 1년"]
    assert s.eligibility == []
    assert removed == 5  # 개요 1 + 예산 1 + 일정 1 + 요구사항 1 + 자격 1


def test_contract_method_must_appear_in_the_source():
    ok = _summary(budget_contract=BudgetContract(contract_method="협상에 의한 계약"))
    bad = _summary(budget_contract=BudgetContract(contract_method="적격심사"))
    ground(ok, SRC)
    ground(bad, SRC)
    assert ok.budget_contract.contract_method == "협상에 의한 계약"  # 띄어쓰기 무시
    assert bad.budget_contract.contract_method is None


def test_meta_values_count_as_source():
    s = _summary(
        budget_contract=BudgetContract(budget_text="99,000,000원"),
        schedule=[ScheduleItem(label="입찰 마감", date="2026-11-24")],
    )
    assert ground(s, SRC) == 1  # 개요의 12월 30일만
    assert s.budget_contract.budget_text == "99,000,000원" and len(s.schedule) == 1


def test_analysis_result_is_grounded_too():
    a = AnalysisResult(
        overview="평가는 2026. 12. 8.에 열립니다. 계약금은 7억원입니다.",
        requirements=[],
        evaluation=Evaluation(method="협상에 의한 계약"),
        schedule=[],
        budget_contract=BudgetContract(),
        risks=[Risk(text="2027년 1월 5일까지 납품"), Risk(text="보안 서약 필요")],
        fit=Fit(
            score=70, verdict="possible", strengths=[], gaps=[], reasoning="예산 3억원 규모라 적합."
        ),
        next_actions=["2026-12-01까지 질의서 제출"],
    )
    assert ground(a, SRC) == 4
    assert a.overview == "평가는 2026. 12. 8.에 열립니다."
    assert [r.text for r in a.risks] == ["보안 서약 필요"]
    assert a.fit.reasoning == "" and a.next_actions == []


def test_evaluation_method_must_appear_in_the_source_too():
    """v5 g019: 평가 방식 칸의 잘못된 값. 보기 이름이 원문에 있어야 남긴다(가운뎃점 무시)."""
    src = SRC + ["낙찰자 결정방법: 규격가격 동시입찰"]
    ok = _summary(evaluation=Evaluation(method="규격·가격 동시입찰"))
    bad = _summary(evaluation=Evaluation(method="적격심사"))
    ground(ok, src)
    ground(bad, src)
    assert ok.evaluation.method == "규격·가격 동시입찰"
    assert bad.evaluation.method is None
