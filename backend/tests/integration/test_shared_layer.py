"""공유 계층 인수 테스트 (SPEC §12.3, §5.9-1·2·3·8). 이 프로젝트의 핵심 가치.

LLM·다운로더는 호출 수를 세는 가짜. P1은 캐시 계약만 검증하고 실제 프롬프트는 P3(§8).
"""

import asyncio
import re
from datetime import timedelta

from sqlalchemy import func, select

from app.db.models import Analysis, Bid, BidSummary, FileText
from app.pipeline.analyze import get_or_create_analysis
from app.pipeline.scoring import get_or_create_scores
from app.pipeline.summarize import get_or_create_summary
from app.profiles.hashing import profile_hash
from tests.conftest import NOW
from tests.fakes.downloader import docx_bytes
from tests.fakes.g2b import regular_item
from tests.helpers import seed

RFP_URL = "https://www.g2b.go.kr/files/rfp-001.docx"
PROFILE_A = "AI 플랫폼 개발팀. 자연어처리·검색 시스템 구축 경험."
PROFILE_B = "클라우드 인프라팀. 공공 클라우드 전환 사업 수행."


async def _until(cond, timeout_s: float = 10.0) -> None:
    for _ in range(int(timeout_s / 0.02)):
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("조건이 시간 안에 충족되지 않음")


async def _bid_with_rfp(deps, no="R26BK00000001"):
    deps.downloader.files[RFP_URL] = (
        docx_bytes("제안요청서 본문: 과업 범위와 요구사항"),
        "제안요청서.docx",
    )
    item = regular_item(no, NOW - timedelta(hours=3), files=[(RFP_URL, "제안요청서.docx")])
    (bid_id,) = await seed(deps, "regular", item)
    return bid_id, item


async def test_second_user_same_bid_reuses_download_extract_and_summary(
    deps, fake_llm, fake_downloader
):
    """R4: A가 처리한 공고를 B가 열면 다운로드·추출·요약 LLM 호출이 0회."""
    bid_id, _ = await _bid_with_rfp(deps)

    first, hit1 = await get_or_create_summary(deps, bid_id)  # 사용자 A
    second, hit2 = await get_or_create_summary(deps, bid_id)  # 사용자 B

    assert (hit1, hit2) == (False, True)
    assert first.id == second.id
    assert fake_llm.calls["summarize_bid"] == 1
    assert len(fake_downloader.calls) == 1
    async with deps.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(FileText)) == 1


async def test_same_profile_text_shares_analysis(deps, fake_llm):
    """§5.9-1: 같은 프로필 텍스트의 사용자 B는 LLM 호출 0회."""
    bid_id, _ = await _bid_with_rfp(deps)
    a, hit_a = await get_or_create_analysis(deps, bid_id, PROFILE_A)
    b, hit_b = await get_or_create_analysis(
        deps, bid_id, "  " + PROFILE_A.replace(" ", "  ") + "\n"
    )
    assert (hit_a, hit_b) == (False, True)
    assert a.id == b.id
    assert fake_llm.calls == {"summarize_file": 1, "summarize_bid": 1, "analyze_bid": 1}


async def test_different_profile_reuses_summary_but_new_analysis(deps, fake_llm):
    """§5.9-2: 프로필이 다르면 요약은 재사용(0회), 분석만 새로(1회)."""
    bid_id, _ = await _bid_with_rfp(deps)
    await get_or_create_analysis(deps, bid_id, PROFILE_A)
    _, hit = await get_or_create_analysis(deps, bid_id, PROFILE_B)
    assert hit is False
    assert fake_llm.calls == {"summarize_file": 1, "summarize_bid": 1, "analyze_bid": 2}


async def test_ten_concurrent_analyses_call_llm_once(deps, fake_llm, fake_downloader):
    """§5.9-3, §12.3: 같은 공고 분석 10개를 동시에 보내도 요약·분석 LLM 호출은 각 1회."""
    fake_llm.delay_s = 0.2
    bid_id, _ = await _bid_with_rfp(deps)
    results = await asyncio.gather(
        *(get_or_create_analysis(deps, bid_id, PROFILE_A) for _ in range(10))
    )
    assert {r.id for r, _ in results} == {results[0][0].id}
    assert fake_llm.calls == {"summarize_file": 1, "summarize_bid": 1, "analyze_bid": 1}
    assert len(fake_downloader.calls) == 1


async def test_cancelled_caller_does_not_stop_work(deps, fake_llm):
    """§12.3: 호출자가 끊겨도(SSE 연결 끊김) 작업은 끝까지 진행돼 DB에 저장된다 (asyncio.shield)."""
    fake_llm.delay_s = 0.3
    bid_id, _ = await _bid_with_rfp(deps)
    task = asyncio.create_task(get_or_create_summary(deps, bid_id))
    # 고정 대기 대신 LLM 호출이 시작된 뒤 끊는다. 추출 워커 기동(HWPLoader 임포트)이
    # 1초 넘게 걸릴 수 있어, 그 전에 끊으면 요약 단계에 도달하지 않는다.
    await _until(lambda: sum(fake_llm.calls.values()) > 0)
    task.cancel()

    async def saved() -> bool:
        async with deps.db.session() as s:
            n = await s.scalar(
                select(func.count()).select_from(BidSummary).where(BidSummary.bid_id == bid_id)
            )
        return n == 1

    for _ in range(100):  # 최대 5초
        if await saved():
            break
        await asyncio.sleep(0.05)
    assert task.cancelled()
    assert await saved()


async def test_changed_content_bumps_revision_and_resummarizes(deps, fake_llm):
    """§5.9-8, §12.3: content_hash가 같으면 재요약 안 함, 바뀐 정정공고는 revision+1 후 새 요약."""
    item = regular_item("R26BK00000002", NOW - timedelta(hours=3))  # 첨부 없음 → meta-only 요약
    (bid_id,) = await seed(deps, "regular", item)
    await get_or_create_summary(deps, bid_id)

    await seed(deps, "regular", item)  # 같은 내용 재수집
    _, hit = await get_or_create_summary(deps, bid_id)
    assert hit is True and fake_llm.calls["summarize_bid"] == 1

    changed = regular_item(
        "R26BK00000002",
        NOW - timedelta(hours=1),
        ord="001",
        title="[변경] AI 기반 민원 분석",
        kind="변경공고",
    )
    await seed(deps, "regular", changed)
    async with deps.db.session() as s:
        assert (await s.get(Bid, bid_id)).revision == 2
    _, hit = await get_or_create_summary(deps, bid_id)
    assert hit is False and fake_llm.calls["summarize_bid"] == 2


async def test_prompt_version_change_does_not_reuse_cache(deps, fake_llm):
    """§12.3: PROMPT_VERSION(모델 접미사 포함)이 바뀌면 이전 캐시를 재사용하지 않는다."""
    bid_id, _ = await _bid_with_rfp(deps)
    await get_or_create_summary(deps, bid_id)
    fake_llm.model_id = "fake-2"
    _, hit = await get_or_create_summary(deps, bid_id)
    assert hit is False
    async with deps.db.session() as s:
        versions = set((await s.execute(select(BidSummary.prompt_version))).scalars())
    assert len(versions) == 2


async def test_scores_shared_by_profile_hash_and_keywords_excluded(deps, fake_llm):
    """§12.3: profile_hash가 같은 두 사용자는 점수를 공유하고, keywords만 다르면 해시가 같다."""
    assert profile_hash(PROFILE_A) == profile_hash(PROFILE_A + "  ")
    ids = await seed(
        deps,
        "regular",
        *(regular_item(f"R26BK0000010{i}", NOW - timedelta(hours=i)) for i in range(3)),
    )

    first = await get_or_create_scores(deps, ids, PROFILE_A)
    second = await get_or_create_scores(deps, ids, PROFILE_A)
    assert set(first) == set(second) == set(ids)
    assert fake_llm.calls["score_bids"] == 1

    # 공고 내용이 바뀌면 그 공고만 stale로 재평가
    await seed(deps, "regular", regular_item("R26BK00000100", NOW, ord="001", title="변경됨"))
    await get_or_create_scores(deps, ids, PROFILE_A)
    assert fake_llm.calls["score_bids"] == 2
    # LLM에는 짧은 ID(b123)만 간다 (규칙 6)
    sent = fake_llm.payloads[-1][1][1]["content"]
    assert re.findall(r"\[(b\d+)\]", sent) == [f"b{ids[0]}"]
    assert "http" not in sent


async def test_shared_rows_carry_no_user_identity(deps):
    """§4: 공유 계층 행은 누가 만들었는지 기록하지 않는다."""
    bid_id, _ = await _bid_with_rfp(deps)
    await get_or_create_analysis(deps, bid_id, PROFILE_A)
    for model in (Bid, BidSummary, Analysis, FileText):
        assert not any("user" in c.name for c in model.__table__.columns)
