"""녹화한 실제 응답으로 필드 매핑 확인 (SPEC §5.2 BidRecord, §4 bids)."""

import json
from datetime import UTC, datetime

from app.g2b.mapper import file_kind, parse_kst, to_record
from tests.fakes.g2b import FIXTURES


def _items(name):
    body = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["response"]["body"]
    its = body["items"]
    return its if isinstance(its, list) else its["item"]


def test_regular_record_from_real_response():
    item = _items("regular_page1.json")[1]
    rec = to_record("regular", item)
    assert rec.bid_key == f"regular:{item['bidNtceNo']}"
    assert (
        rec.source == "regular"
        and rec.bid_no == item["bidNtceNo"]
        and rec.ord == item["bidNtceOrd"]
    )
    assert rec.title == item["bidNtceNm"]
    expected_budget = int(float(item.get("bdgtAmt") or item.get("presmptPrce")))
    assert rec.budget == expected_budget
    assert rec.notice_at is not None and rec.notice_at.tzinfo is not None
    assert rec.detail_url == item["bidNtceDtlUrl"]
    assert rec.raw == item


def test_prespec_record_from_real_response():
    item = _items("prespec_page1.json")[0]
    rec = to_record("prespec", item)
    assert rec.bid_key == f"prespec:{item['bfSpecRgstNo']}"
    assert rec.title == item["prdctClsfcNoNm"]
    assert rec.budget == (int(float(item["asignBdgtAmt"])) if item.get("asignBdgtAmt") else None)
    assert all(f.kind == "spec" and f.origin == "prespec" for f in rec.files)


def test_revised_samples_keep_order():
    for item in _items("regular_revised_sample.json"):
        assert to_record("regular", item).ord == item["bidNtceOrd"]


def test_parse_kst_converts_to_utc_all_formats():
    want = datetime(2026, 11, 17, 1, 0, tzinfo=UTC)  # KST 10:00
    for s in ("2026-11-17 10:00:00", "2026-11-17 10:00", "202611171000"):
        assert parse_kst(s) == want
    assert parse_kst("20261117") == datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
    assert parse_kst("") is None and parse_kst(None) is None and parse_kst("미정") is None


def test_empty_deadline_is_null_and_bad_budget_is_null():
    item = dict(_items("regular_page1.json")[0], bidClseDt="", bdgtAmt="", presmptPrce="비공개")
    rec = to_record("regular", item)
    assert rec.deadline_at is None and rec.budget is None


def test_zero_budget_kept():
    item = dict(_items("regular_page1.json")[0], bdgtAmt="0", presmptPrce="")
    assert to_record("regular", item).budget == 0


def test_file_kind_rules():
    assert file_kind("2026 제안요청서(최종).hwp", "regular") == "rfp"
    assert file_kind("과업지시서.pdf", "regular") == "rfp"
    assert file_kind("입찰공고문.hwp", "regular") == "other"
    # 2026-11-13: 일반공고 1/3이 이런 이름이라 첨부를 안 읽고 있었다 (띄어쓰기 무시)
    for name in (
        "2. 과업내용서.hwpx",
        "과업 설명서.pdf",
        "과업명세서.hwp",
        "[수행지침서] 감리용역.hwp",
    ):
        assert file_kind(name, "regular") == "rfp", name
    for name in ("5. 과업설명참가신청서.hwp", "과업설명회 개최 안내.hwp", "과업내용서 양식.hwp"):
        assert file_kind(name, "regular") == "other", name  # 서식·설명회 안내는 과업 문서가 아님
    assert file_kind("규격문서 1", "prespec") == "spec"


def test_content_hash_ignores_raw_noise_but_tracks_meta():
    item = _items("regular_page1.json")[1]
    a = to_record("regular", item)
    b = to_record("regular", dict(item, rgstDt="2099-01-01 00:00:00"))  # 메타 아닌 필드
    c = to_record("regular", dict(item, bidNtceNm=item["bidNtceNm"] + " (변경)"))
    assert a.content_hash() == b.content_hash() != c.content_hash()
