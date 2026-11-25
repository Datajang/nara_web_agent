"""결과 메일 받는 사람·발송 대기열 (계획 Task 7 + 최종 검토 수정). 메모리 메일함으로 본다."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import insert, select, update

from app.auth.mail import Mail, MemoryMailer
from app.db.models import Bid, BidResultMail, BidResultWatch, Bookmark, User
from app.results.checker import Change
from app.results.dispatch import MAX_ATTEMPTS, deliver, enqueue, recipients
from tests.conftest import NOW
from tests.fakes.g2b import kst_str, regular_item
from tests.helpers import create_user, seed

NO = "R26BK92000001"


async def _final_bid(deps, no: str = NO) -> int:
    """낙찰 확정(감지 NOW)된 감시 행이 있는 공고."""
    it = regular_item(no, NOW - timedelta(days=9))
    it["opengDt"] = kst_str(NOW - timedelta(hours=3))
    (bid_id,) = await seed(deps, "regular", it)
    async with deps.db.transaction() as s:
        s.add(
            BidResultWatch(
                bid_id=bid_id,
                stage="final",
                notice_ord="000",
                opening_at=NOW - timedelta(hours=3),
                next_check_at=NOW,
                final_kind="awarded",
                final_at=NOW,
            )
        )
    return bid_id


async def _bookmark(deps, email: str, bid_id: int, *, ago=timedelta(days=1), **kw) -> int:
    uid = await create_user(deps.db, email, status=kw.pop("status", "active"))
    async with deps.db.transaction() as s:
        await s.execute(
            insert(Bookmark).values(user_id=uid, bid_id=bid_id, created_at=NOW - ago, **kw)
        )
    return uid


async def _send(deps, mailer, changes) -> int:
    async with deps.db.transaction() as s:
        await enqueue(s, changes)
    return await deliver(deps, mailer)


async def test_sends_once_per_stage(deps):
    bid_id = await _final_bid(deps)
    await _bookmark(deps, "a@corp.example", bid_id)
    mailer = MemoryMailer()
    assert await _send(deps, mailer, [Change(bid_id, "final")]) == 1
    assert await _send(deps, mailer, [Change(bid_id, "final")]) == 0
    assert [m.to for m in mailer.outbox] == ["a@corp.example"]
    assert mailer.outbox[0].subject.endswith("낙찰 결과: AI 기반 민원 분석 시스템 구축 용역")


async def test_bookmark_off_or_switch_off_or_inactive_skipped(deps):
    bid_id = await _final_bid(deps)
    await _bookmark(deps, "on@corp.example", bid_id)
    await _bookmark(deps, "bm-off@corp.example", bid_id, notify_result=False)
    off = await _bookmark(deps, "sw-off@corp.example", bid_id)
    await _bookmark(deps, "gone@corp.example", bid_id, status="disabled")
    async with deps.db.transaction() as s:
        await s.execute(update(User).where(User.id == off).values(result_mail=False))
    async with deps.db.session() as s:
        got = [u.email for u in await recipients(s, Change(bid_id, "final"))]
    assert got == ["on@corp.example"]


async def test_bookmarked_after_detection_skipped(deps):
    """결과가 감지된 뒤에 북마크한 사람에게는 그 단계 메일을 보내지 않는다."""
    bid_id = await _final_bid(deps)
    await _bookmark(deps, "late@corp.example", bid_id, ago=timedelta(minutes=-5))
    assert await _send(deps, MemoryMailer(), [Change(bid_id, "final")]) == 0


class FlakyMailer(MemoryMailer):
    def __init__(self, fail_to: str) -> None:
        super().__init__()
        self.fail_to = fail_to

    async def send(self, mail: Mail) -> None:
        if mail.to == self.fail_to:
            self.fail_to = ""  # 한 번만 실패
            raise OSError("SMTP 연결 끊김")
        await super().send(mail)


async def test_smtp_failure_retried_next_run(deps):
    """셋 중 하나 실패 → 2통, 다음 실행(대기열 재시도)에서 1통, 중복 없음(Review 4)."""
    bid_id = await _final_bid(deps)
    for e in ("a@corp.example", "b@corp.example", "c@corp.example"):
        await _bookmark(deps, e, bid_id)
    mailer = FlakyMailer("b@corp.example")
    assert await _send(deps, mailer, [Change(bid_id, "final")]) == 2
    assert await deliver(deps, mailer) == 1
    assert await deliver(deps, mailer) == 0
    assert sorted(m.to for m in mailer.outbox) == [
        "a@corp.example",
        "b@corp.example",
        "c@corp.example",
    ]


class DeadMailer(MemoryMailer):
    async def send(self, mail: Mail) -> None:
        raise OSError("550 mailbox unavailable")


async def test_permanent_failure_gives_up(deps):
    """계속 실패하는 주소는 MAX_ATTEMPTS번 시도하고 그만둔다(5분마다 끝없이 재시도하지 않음)."""
    bid_id = await _final_bid(deps)
    await _bookmark(deps, "dead@corp.example", bid_id)
    mailer = DeadMailer()
    async with deps.db.transaction() as s:
        await enqueue(s, [Change(bid_id, "final")])
    for _ in range(MAX_ATTEMPTS + 3):
        await deliver(deps, mailer)
    async with deps.db.session() as s:
        row = (await s.execute(select(BidResultMail))).scalar_one()
    assert (row.status, row.attempts) == ("failed", MAX_ATTEMPTS)


async def test_turned_on_after_detection_gets_no_stale_mail(deps):
    """감지 때 꺼 두었다가 나중에 켠 사람에게 지난 결과를 몰아 보내지 않는다."""
    bid_id = await _final_bid(deps)
    uid = await _bookmark(deps, "away@corp.example", bid_id)
    async with deps.db.transaction() as s:
        await s.execute(update(User).where(User.id == uid).values(result_mail=False))
    mailer = MemoryMailer()
    assert await _send(deps, mailer, [Change(bid_id, "final")]) == 0
    async with deps.db.transaction() as s:
        await s.execute(update(User).where(User.id == uid).values(result_mail=True))
    assert await deliver(deps, mailer) == 0
    assert mailer.outbox == []


async def test_turned_off_before_send_is_cancelled(deps):
    """대기열에 들어간 뒤 보내기 전에 끄면 보내지 않는다."""
    bid_id = await _final_bid(deps)
    uid = await _bookmark(deps, "a@corp.example", bid_id)
    async with deps.db.transaction() as s:
        await enqueue(s, [Change(bid_id, "final")])
        await s.execute(update(User).where(User.id == uid).values(result_mail=False))
    assert await deliver(deps, MemoryMailer()) == 0
    async with deps.db.session() as s:
        assert (await s.execute(select(BidResultMail.status))).scalar_one() == "cancelled"


async def test_queue_sends_in_detection_order(deps):
    """①이 먼저 감지됐으면 ①을 ②보다 먼저 보낸다(이름순이 아니라 대기열 순서)."""
    bid_id = await _final_bid(deps)
    await _bookmark(deps, "a@corp.example", bid_id)
    async with deps.db.transaction() as s:
        w = await s.get_one(BidResultWatch, bid_id)
        w.opened_at = NOW - timedelta(hours=1)
        await enqueue(s, [Change(bid_id, "opened")])
        await enqueue(s, [Change(bid_id, "final")])
    mailer = MemoryMailer()
    assert await deliver(deps, mailer) == 2
    assert ["개찰 결과" in m.subject for m in mailer.outbox] == [True, False]


async def test_other_users_bookmarks_not_leaked(deps):
    """메일은 그 공고를 북마크한 사람에게만, 한 사람에게 한 통씩(다른 수신자 주소가 보이지 않음)."""
    bid_id = await _final_bid(deps)
    other = await _final_bid(deps, "R26BK92000002")
    await _bookmark(deps, "mine@corp.example", bid_id)
    await _bookmark(deps, "theirs@corp.example", other)
    mailer = MemoryMailer()
    await _send(deps, mailer, [Change(bid_id, "final")])
    assert [m.to for m in mailer.outbox] == ["mine@corp.example"]
    assert "theirs@corp.example" not in mailer.outbox[0].body


async def test_mail_view_uses_our_rank_and_award(deps):
    """load_view: 우리 사업자번호의 순위·낙찰자·금액이 메일에 들어간다(Task 6 load_view)."""
    from app.db.models import BidAward, BidParticipant, Company, OrgSettings

    bid_id = await _final_bid(deps)
    await _bookmark(deps, "a@corp.example", bid_id)
    async with deps.db.transaction() as s:
        bid = await s.get_one(Bid, bid_id)
        s.add(OrgSettings(id=1, our_bizno="2222222222", our_name="우리"))
        s.add(
            Company(
                bizno="1111111111",
                name="(주)가온데이터",
                name_norm="가온데이터",
                first_seen_at=NOW,
                last_seen_at=NOW,
            )
        )
        await s.flush()
        for bizno, rank, amt in (("1111111111", 1, 90_000_000), ("2222222222", 2, 91_000_000)):
            s.add(
                BidParticipant(
                    bid_ntce_no=bid.bid_no,
                    bid_ntce_ord="000",
                    bid_clsfc_no="0",
                    rbid_no="000",
                    bizno=bizno,
                    name=f"업체{rank}",
                    rank=rank,
                    bid_amount=amt,
                )
            )
        s.add(
            BidAward(
                bid_ntce_no=bid.bid_no,
                bid_ntce_ord="000",
                bid_clsfc_no="0",
                rbid_no="000",
                bizno="1111111111",
                winner_name="(주)가온데이터",
                title=bid.title,
                award_amount=90_000_000,
                registered_at=NOW,
            )
        )
    mailer = MemoryMailer()
    await _send(deps, mailer, [Change(bid_id, "final")])
    body = mailer.outbox[0].body
    assert "낙찰자: (주)가온데이터 · 낙찰금액 90,000,000원" in body
    assert "우리 회사: 2위 / 2곳" in body


async def test_mail_view_multi_class_awards_and_our_ranks(deps):
    """분류가 여럿이면 분류마다 낙찰자, 우리 순위도 참가한 분류마다(첫 분류만이 아니라)."""
    from app.db.models import BidAward, BidParticipant, OrgSettings

    bid_id = await _final_bid(deps)
    await _bookmark(deps, "a@corp.example", bid_id)
    async with deps.db.transaction() as s:
        bid = await s.get_one(Bid, bid_id)
        s.add(OrgSettings(id=1, our_bizno="2222222222", our_name="우리"))
        for clsfc, bizno, rank in (
            ("1", "1111111111", 1),
            ("1", "2222222222", 2),
            ("2", "2222222222", 1),
            ("2", "3333333333", 2),
            ("2", "4444444444", 3),
        ):
            s.add(
                BidParticipant(
                    bid_ntce_no=bid.bid_no,
                    bid_ntce_ord="000",
                    bid_clsfc_no=clsfc,
                    rbid_no="000",
                    bizno=bizno,
                    name=f"업체{bizno[0]}",
                    rank=rank,
                    bid_amount=1000 * rank,
                )
            )
        for clsfc, rbid, winner, amt in (
            ("1", "000", "업체1", 90_000_000),
            ("2", "000", "옛 낙찰", 1),
            ("2", "001", "우리", 50_000_000),
        ):
            s.add(
                BidAward(
                    bid_ntce_no=bid.bid_no,
                    bid_ntce_ord="000",
                    bid_clsfc_no=clsfc,
                    rbid_no=rbid,
                    bizno=None,
                    winner_name=winner,
                    title=bid.title,
                    award_amount=amt,
                    registered_at=NOW,
                )
            )
    mailer = MemoryMailer()
    await _send(deps, mailer, [Change(bid_id, "final")])
    body = mailer.outbox[0].body
    assert "[분류 1] 낙찰자: 업체1 · 낙찰금액 90,000,000원" in body
    assert "[분류 2] 낙찰자: 우리 · 낙찰금액 50,000,000원" in body
    assert "옛 낙찰" not in body
    assert "우리 회사: 분류 1 2위 / 2곳 · 분류 2 1위 / 3곳" in body
