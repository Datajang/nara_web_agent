"""결과 메일 문안 (계획 Task 6). 순수 함수라 DB·SMTP 없이 본다."""

from __future__ import annotations

from app.results.mail import AwardLine, RankRow, ResultView, render

ORIGIN = "https://nara.example"
SERVICE = "나라장터 도우미"


def _rows(n: int, clsfc: str = "0") -> list[RankRow]:
    return [
        RankRow(
            rank=i,
            name=f"업체{i}",
            bid_amount=100_000_000 - i * 1000,
            scores=None,
            remark=None,
            clsfc=clsfc,
        )
        for i in range(1, n + 1)
    ]


def _view(**kw) -> ResultView:
    base = dict(
        title="데이터 정비 용역",
        bid_ref="b7",
        org="행정안전부",
        rows=_rows(3),
        our_rank="2위 / 3곳",
        awards=[],
        kind="opened",
        renotice_ref=None,
        negotiated=False,
    )
    base.update(kw)
    return ResultView(**base)


def test_opened_mail_has_rank_table():
    mail = render(_view(rows=_rows(12)), "a@corp.example", ORIGIN, SERVICE)
    assert mail.to == "a@corp.example"
    assert mail.subject == "[나라장터 도우미] 개찰 결과: 데이터 정비 용역"
    assert "1순위(낙찰 예정자): 업체1" in mail.body
    assert "업체10" in mail.body and "업체11" not in mail.body
    assert "외 2곳" in mail.body
    assert "우리 회사: 2위 / 3곳" in mail.body
    assert f"{ORIGIN}/bids/b7" in mail.body
    assert mail.body.rstrip().endswith(
        f"결과 메일은 설정 > 계정에서 끌 수 있어요. {ORIGIN}/settings/account"
    )
    assert mail.html is not None and "99,999,000원" in mail.html


def test_our_rank_missing_says_not_participated():
    mail = render(_view(our_rank="미참가"), "a@corp.example", ORIGIN, SERVICE)
    assert "우리 회사: 미참가" in mail.body


def test_awarded_mail_has_winner_amount():
    mail = render(
        _view(kind="awarded", awards=[AwardLine("0", "(주)가온데이터", 90_000_000)]),
        "a@corp.example",
        ORIGIN,
        SERVICE,
    )
    assert mail.subject == "[나라장터 도우미] 낙찰 결과: 데이터 정비 용역"
    assert "낙찰자: (주)가온데이터 · 낙찰금액 90,000,000원" in mail.body
    assert "업체1" in mail.body  # 순위·투찰가도 함께


def test_failed_mail_says_yuchal():
    mail = render(
        _view(kind="failed", rows=[], our_rank="미참가"), "a@corp.example", ORIGIN, SERVICE
    )
    assert mail.subject == "[나라장터 도우미] 유찰: 데이터 정비 용역"
    assert "유찰되었어요" in mail.body
    assert "재공고가 올라오면 다시 알려드려요" in mail.body


def test_renotice_mail_links_new_bid():
    mail = render(
        _view(kind="renotice", rows=[], renotice_ref="b42"), "a@corp.example", ORIGIN, SERVICE
    )
    assert mail.subject == "[나라장터 도우미] 재공고가 올라왔어요: 데이터 정비 용역"
    assert f"{ORIGIN}/bids/b42" in mail.body
    assert f"{ORIGIN}/bids/b7" not in mail.body


def test_negotiated_shows_scores():
    rows = [RankRow(1, "업체1", 90_000_000, (71.4167, 18.3206, 89.7373), None, "0")]
    mail = render(_view(rows=rows, negotiated=True), "a@corp.example", ORIGIN, SERVICE)
    assert "기술 71.42 · 가격 18.32 · 총점 89.74" in mail.body


def test_html_escapes_names():
    rows = [RankRow(1, "<b>악성</b>", 1, None, None, "0")]
    mail = render(_view(rows=rows, title="<script>x</script>"), "a@corp.example", ORIGIN, SERVICE)
    assert mail.html is not None
    assert "<b>악성</b>" not in mail.html and "&lt;b&gt;악성&lt;/b&gt;" in mail.html
    assert "<script>" not in mail.html


def test_classes_grouped():
    """분류가 여럿이면 분류별 소제목과 각자 상위 10곳(Review 1). 하나면 소제목 없음."""
    two = render(_view(rows=_rows(2, "1") + _rows(2, "2")), "a@corp.example", ORIGIN, SERVICE)
    assert "[분류 1]" in two.body and "[분류 2]" in two.body
    one = render(_view(), "a@corp.example", ORIGIN, SERVICE)
    assert "[분류" not in one.body


def test_subject_has_no_newlines():
    """G2B 사업명에 줄바꿈이 섞여도 메일 제목은 한 줄(EmailMessage는 제목의 줄바꿈을 거부한다)."""
    from email.message import EmailMessage

    mail = render(_view(title="데이터\r\n정비   용역"), "a@corp.example", ORIGIN, SERVICE)
    assert mail.subject == "[나라장터 도우미] 개찰 결과: 데이터 정비 용역"
    EmailMessage()["Subject"] = mail.subject  # 예외 없음


def test_awarded_mail_lists_every_class_winner():
    """분류가 여럿이면 분류마다 낙찰자·금액(첫 분류만 보이지 않게)."""
    awards = [AwardLine("1", "(주)가온데이터", 90_000_000), AwardLine("2", "(주)나래", 50_000_000)]
    rows = _rows(2, "1") + _rows(2, "2")
    mail = render(
        _view(kind="awarded", awards=awards, rows=rows), "a@corp.example", ORIGIN, SERVICE
    )
    assert "[분류 1] 낙찰자: (주)가온데이터 · 낙찰금액 90,000,000원" in mail.body
    assert "[분류 2] 낙찰자: (주)나래 · 낙찰금액 50,000,000원" in mail.body


def test_awarded_mail_without_award_row():
    mail = render(_view(kind="awarded"), "a@corp.example", ORIGIN, SERVICE)
    assert "낙찰자: - · 낙찰금액 -" in mail.body
