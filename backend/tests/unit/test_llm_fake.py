"""가짜 LLM (SPEC §8.8-6): 기본 출력이 §8.4 스키마를 만족하고 결정적이다."""

import json

from app.llm.fake import FakeLLM
from app.llm.prompts import render
from app.llm.schemas import AnalysisResult, BidSummary, FileFacts, KeywordSuggestion, ScoreBatch
from app.llm.structured import generate


async def test_default_outputs_validate_against_schemas():
    llm = FakeLLM()
    facts = await generate(
        llm,
        "summarize_file",
        render("summarize_file", file_name="f", kind="rfp", i=1, n=1, chunk_text="과업 범위"),
        FileFacts,
    )
    meta = json.dumps({"title": "AI 플랫폼 구축"}, ensure_ascii=False)
    summary = await generate(
        llm,
        "summarize_bid",
        render(
            "summarize_bid",
            meta=meta,
            facts_list=json.dumps([facts.model_dump()], ensure_ascii=False),
            n_read=1,
            n_total=1,
            truncated=False,
        ),
        BidSummary,
    )
    scores = await generate(
        llm,
        "score_bids",
        render("score_bids", profile_description="AI 개발", bids="[b1] 제목: AI\n[b2] 제목: 도로"),
        ScoreBatch,
    )
    analysis = await generate(
        llm,
        "analyze_bid",
        render(
            "analyze_bid",
            profile_description="AI 개발",
            meta=meta,
            bid_summary_json=summary.model_dump_json(),
        ),
        AnalysisResult,
    )
    kw = await generate(
        llm,
        "suggest_keywords",
        render("suggest_keywords", profile_description="인공지능 검색 플랫폼 개발"),
        KeywordSuggestion,
    )
    assert summary.headline.startswith("AI 플랫폼")
    assert [s.bid_id for s in scores.scores] == ["b1", "b2"]
    assert scores.scores[0].score > scores.scores[1].score  # 프로필과 겹치는 제목이 높다
    assert analysis.overview and 1 <= len(kw.keywords) <= 10
    assert llm.calls["summarize_file"] == 1
