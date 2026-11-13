"""요약에 읽을 첨부 고르기 (2026-11-13, 사용자 승인: 공고서 대체·같은 문서 하나만).

일반공고 35,975건 중 11,717건이 제안요청서·과업지시서 이름의 첨부가 없어 첨부를 하나도 안 읽었다.
"""

from dataclasses import dataclass

from app.pipeline.summarize import pick_files


@dataclass
class F:
    name: str
    kind: str = "other"
    status: str = "ok"


def names(files):
    return [f.name for f in files]


def test_rfp_and_spec_are_read_first_and_notice_is_ignored_then():
    files = [F("제안요청서.hwp", "rfp"), F("입찰공고문.hwp"), F("과업지시서.pdf", "rfp")]
    assert names(pick_files(files)) == ["제안요청서.hwp", "과업지시서.pdf"]


def test_notice_is_read_when_there_is_no_rfp_but_forms_are_not():
    files = [
        F("공고서(국가SW,중기간,20억미만).hwpx"),
        F("나. 입찰참가신청서.pdf"),
        F("[입찰공고문] 다소비(변경).pdf"),
        F("청렴서약서 양식.hwp"),
        F("산출내역서.xlsx"),
    ]
    assert names(pick_files(files)) == [
        "공고서(국가SW,중기간,20억미만).hwpx",
        "[입찰공고문] 다소비(변경).pdf",
    ]


def test_notice_is_read_when_every_rfp_failed():
    files = [F("제안요청서.hwp", "rfp", "failed"), F("공고문.pdf")]
    assert names(pick_files(files)) == ["제안요청서.hwp", "공고문.pdf"]


def test_same_document_in_two_formats_is_read_once():
    files = [
        F("공고서(용역).pdf"),
        F("공고서(용역).hwpx"),
        F("제안요청서.pdf", "rfp", "failed"),
        F("제안요청서.hwp", "rfp"),
    ]
    assert names(pick_files(files)) == ["제안요청서.hwp"]
    assert names(pick_files(files[:2])) == ["공고서(용역).hwpx"]  # 한글 원본을 PDF보다 먼저


def test_nothing_to_read():
    assert pick_files([F("입찰참가신청서.hwp"), F("현장 사진.jpg")]) == []
