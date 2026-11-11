from datetime import UTC, datetime, timedelta

from app.collector.windows import split_windows
from app.profiles.hashing import normalize_profile, profile_hash

T0 = datetime(2026, 11, 1, tzinfo=UTC)


def test_windows_cover_range_without_shared_boundaries():
    """알려진 문제 #2: 다음 창의 시작이 이전 창의 끝과 겹치지 않는다(끝은 배타적)."""
    ws = split_windows(T0, T0 + timedelta(days=2, hours=5), timedelta(days=1))
    assert ws[0][0] == T0 and ws[-1][1] == T0 + timedelta(days=2, hours=5)
    assert all(a[1] == b[0] for a, b in zip(ws, ws[1:], strict=False))
    assert len(ws) == 3


def test_windows_newest_first():
    ws = split_windows(T0, T0 + timedelta(days=3), timedelta(days=1), newest_first=True)
    assert ws[0][1] == T0 + timedelta(days=3)


def test_empty_range():
    assert split_windows(T0, T0, timedelta(days=1)) == []


def test_profile_hash_normalizes_nfkc_and_whitespace():
    assert normalize_profile("  AI　팀 \n 개발 ") == "AI 팀 개발"
    assert profile_hash("ＡＩ 팀") == profile_hash("AI   팀")
    assert profile_hash("AI 팀") != profile_hash("클라우드 팀")
