"""청킹 (SPEC §8.3): 번호 제목 경계, 겹침, 우선순위, 예산."""

from pathlib import Path

import pytest

from app.llm.tokens import CharCounter, load_counter
from app.pipeline.chunking import select_chunks, split_text


class OneTokenPerChar:
    def count(self, text: str) -> int:
        return len(text)


C = OneTokenPerChar()


def test_text_within_single_budget_is_one_chunk():
    text = "제1조 목적\n" + "가" * 500
    assert split_text(text, C, target=100, overlap=10, single_max=1000) == [text]


def test_splits_at_numbered_headings():
    sections = [f"제{i}조 항목{i}\n" + "나" * 50 for i in range(1, 7)]
    chunks = split_text("\n".join(sections), C, target=130, overlap=0, single_max=200)
    assert len(chunks) >= 3
    for ch in chunks:
        assert ch.startswith("제")  # 모든 청크가 제목에서 시작
        assert len(ch) <= 130


def test_overlap_repeats_tail_of_previous_chunk():
    sections = [f"{i}. 과업 {i}\n" + "\n".join(f"줄{i}-{j}" for j in range(8)) for i in range(1, 5)]
    chunks = split_text("\n".join(sections), C, target=80, overlap=12, single_max=100)
    assert len(chunks) >= 2
    overlap_part, _, _ = chunks[1].partition("\n2. 과업")
    assert overlap_part and chunks[0].endswith(overlap_part)  # 앞 청크 끝부분으로 시작
    assert len(overlap_part) <= 12


def test_unbreakable_text_is_hard_split_under_target():
    chunks = split_text("다" * 1000, C, target=300, overlap=0, single_max=400)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks) == "다" * 1000


def test_table_lines_stay_together():
    table = "\n".join(f"| 평가항목{i} | {i}점 |" for i in range(5))
    text = "1. 개요\n" + "라" * 60 + "\n\n" + table + "\n\n2. 일정\n" + "마" * 60
    chunks = split_text(text, C, target=110, overlap=0, single_max=160)
    assert len(chunks) >= 2
    holders = [c for c in chunks if "평가항목0" in c]
    assert len(holders) == 1 and "평가항목4" in holders[0]


def test_priority_keeps_keyword_rich_chunks_in_original_order():
    chunks = ["서론 일반", "평가 배점 기술평가", "부록", "제출 일정 사업기간", "참고"]
    selected, truncated = select_chunks(chunks, max_chunks=2)
    assert selected == [1, 3]
    assert truncated is True


def test_no_truncation_under_limit():
    assert select_chunks(["a", "b"], max_chunks=12) == ([0, 1], False)


def test_fallback_counter_is_chars_times_1_2():
    assert CharCounter().count("가나다라마") == 6
    assert isinstance(load_counter(""), CharCounter)
    assert isinstance(load_counter("/no/such/tokenizer.json"), CharCounter)


QWEN = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots"


@pytest.mark.skipif(not QWEN.exists(), reason="로컬 Qwen 토크나이저 없음(CI)")
def test_real_tokenizer_counts_korean():
    path = next(QWEN.glob("*/tokenizer.json"))
    counter = load_counter(str(path))
    assert not isinstance(counter, CharCounter)
    n = counter.count("제안요청서의 평가 기준과 배점을 확인합니다.")
    assert 5 < n < 40
