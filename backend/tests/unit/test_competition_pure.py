"""P11 순수 함수: 계약 corpList 파싱(공동수급), 공고명 비슷함, 분포 (SPEC §15.4·§15.7)."""

import json
from decimal import Decimal
from pathlib import Path

from app.awards.competition import similarity, spread
from app.awards.contracts import is_joint, notice_key, parse_corp_list, to_member_rows
from app.awards.participants import to_participant

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "g2b"


def _items(name):
    body = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["response"]["body"]
    items = body["items"]
    return items if isinstance(items, list) else items["item"]


def test_corp_list_fields_follow_probe_order():
    joint = next(c for c in _items("contracts_page1.json") if "공동" in c["corpList"])
    ms = parse_corp_list(joint["corpList"])
    assert [(m.seq, m.role, m.mode, m.share, m.bizno) for m in ms] == [
        (1, "주계약업체", "공동", Decimal(60), "3178123292"),
        (2, "도급업체", "공동", Decimal(40), "3288802700"),
    ]
    assert is_joint(ms)


def test_corp_list_ignores_malformed_entries_and_solo_is_not_joint():
    ms = parse_corp_list("[1^주계약업체^단독^가^^대한민국^100^^^1234567890],[깨진^칸]")
    assert len(ms) == 1 and not is_joint(ms)
    assert parse_corp_list(None) == [] and parse_corp_list("") == []


def test_notice_key_new_old_and_blank():
    assert notice_key("R25BK01246318") == ("R25BK01246318", "")  # 신체계: 차수 없음
    assert notice_key("2021091815501") == ("20210918155", "001")  # 구체계 11+2 → 3자리 차수
    assert notice_key("") is None and notice_key(None) is None and notice_key("ABC") is None


def test_member_rows_whitelist_no_personal_fields():
    rows = [r for c in _items("contracts_page1.json") for r in to_member_rows(c)]
    assert rows and all(r["bizno"] == "3178123292" for r in rows)  # 주계약업체
    assert set(rows[0]) == {
        "bid_ntce_no",
        "bid_ntce_ord",
        "bizno",
        "member_bizno",
        "member_name",
        "role",
        "joint_mode",
        "share",
    }
    # 단독 계약·공고번호 없는 계약은 행이 없다
    assert sum(1 for c in _items("contracts_page1.json") if to_member_rows(c)) == 1


def test_participant_whitelist_and_numbers():
    r = to_participant(_items("opening_compt_page1.json")[0])
    assert r is not None
    assert (r["rank"], r["bid_amount"], r["bizno"]) == (1, 393000000, "8628600042")
    assert (r["tech_score"], r["price_score"], r["total_score"]) == (
        Decimal("71.4167"),
        Decimal("18.3206"),
        Decimal("89.7373"),
    )
    assert "drwtNo1" not in r and "rmrk" not in r
    assert to_participant({"bidNtceNo": "R1", "prcbdrBizno": "12"}) is None  # 사업자번호 없음


def test_similarity_ignores_spacing_years_and_common_words():
    a = "2026년 보은군 정보화시스템 통합 유지관리 용역"
    assert similarity(a, "2027년 보은군 정보화시스템 통합유지관리 용역(2차분)") == 1.0
    assert similarity(a, "보은군 청사 청소 용역") < 0.2
    assert similarity(a, "") == 0.0
    assert similarity(a, "보은군 정보화시스템 유지관리") == similarity(
        "보은군 정보화시스템 유지관리", a
    )


def test_spread_min_median_max():
    sp = spread([87.5, 90.1, 85.0, 88.0])
    assert sp is not None and (sp.n, sp.min, sp.median, sp.max) == (4, 85.0, 87.75, 90.1)
    assert spread([]) is None
