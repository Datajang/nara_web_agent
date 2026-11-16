"""낙찰·경쟁사 분석 테이블 (SPEC §15.3, docs/decisions/2026-11-16-awards-probe.md).

공유 계층: companies, bid_awards, bid_participants, bid_joint_members (공고·업체 단위, user_id 없음)
설정 계층: org_settings(한 행), watched_companies(서비스 전체 공유)

개인정보(대표자명·주소·전화·담당자)와 raw 컬럼은 두지 않는다 (§15.9).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pk, ts_now

BIZNO_CHECK = "~ '^[0-9]{10}$'"


class Company(Base):
    """업체. 사업자번호로 식별하고 이름은 표시용(가장 최근 낙찰의 상호)."""

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint(f"bizno {BIZNO_CHECK}", name="bizno"),
        Index(
            "ix_companies_name_norm_trgm",
            "name_norm",
            postgresql_using="gin",
            postgresql_ops={"name_norm": "gin_trgm_ops"},
        ),
    )

    bizno: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    name_norm: Mapped[str] = mapped_column(Text)
    # 이 업체 낙찰 중 가장 이른·늦은 시각(개찰, 없으면 등록). 이름은 늦은 쪽 기준으로 갱신
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = ts_now()


class BidAward(Base):
    """최종 낙찰 1행 = 공고·차수·분류·재입찰 하나. 공동수급이어도 주계약업체 1행 (probe 5번)."""

    __tablename__ = "bid_awards"
    __table_args__ = (
        UniqueConstraint("bid_ntce_no", "bid_ntce_ord", "bid_clsfc_no", "rbid_no"),
        Index("ix_bid_awards_bizno_registered_at", "bizno", "registered_at"),
        Index("ix_bid_awards_registered_at", "registered_at"),
        Index("ix_bid_awards_dminstt_cd", "dminstt_cd"),
        Index("ix_bid_awards_fields", "fields", postgresql_using="gin"),
    )

    id: Mapped[int] = pk()
    bid_ntce_no: Mapped[str] = mapped_column(Text)
    bid_ntce_ord: Mapped[str] = mapped_column(Text)
    bid_clsfc_no: Mapped[str] = mapped_column(Text)
    rbid_no: Mapped[str] = mapped_column(Text)
    # 사업자번호가 없거나 10자리가 아니면 NULL → 업체 통계에서 빼고 '식별 불가'로 센다 (§15.9)
    bizno: Mapped[str | None] = mapped_column(ForeignKey("companies.bizno"))
    winner_name: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    award_amount: Mapped[int | None] = mapped_column(BigInteger)
    g2b_award_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))  # 예정가격 대비(%)
    estimated_price: Mapped[int | None] = mapped_column(BigInteger)  # bids의 추정가격
    award_ratio: Mapped[Decimal | None] = mapped_column(Numeric(9, 5))  # 낙찰금액/추정가격
    participant_count: Mapped[int | None] = mapped_column(Integer)
    dminstt_cd: Mapped[str | None] = mapped_column(Text)
    dminstt_name: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # rlOpengDt
    awarded_on: Mapped[date | None] = mapped_column(Date)  # fnlSucsfDate
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # rgstDt(수집 창 기준)
    is_joint: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    fields: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'::text[]"))
    fetched_at: Mapped[datetime] = ts_now()
    updated_at: Mapped[datetime] = ts_now()


class BidParticipant(Base):
    """개찰완료 목록의 업체별 순위·투찰·점수. 공고 상세 '경쟁 구도'에서 채우는 캐시 (P11)."""

    __tablename__ = "bid_participants"
    __table_args__ = (
        UniqueConstraint("bid_ntce_no", "bid_ntce_ord", "bid_clsfc_no", "rbid_no", "bizno"),
        Index("ix_bid_participants_bizno", "bizno"),
    )

    id: Mapped[int] = pk()
    bid_ntce_no: Mapped[str] = mapped_column(Text)
    bid_ntce_ord: Mapped[str] = mapped_column(Text)
    bid_clsfc_no: Mapped[str] = mapped_column(Text)
    rbid_no: Mapped[str] = mapped_column(Text)
    bizno: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int | None] = mapped_column(Integer)
    bid_amount: Mapped[int | None] = mapped_column(BigInteger)
    bid_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    tech_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    price_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    fetched_at: Mapped[datetime] = ts_now()


class BidJointMember(Base):
    """공동수급 구성원(계약정보 corpList). P11에서 채운다."""

    __tablename__ = "bid_joint_members"
    __table_args__ = (UniqueConstraint("bid_ntce_no", "bid_ntce_ord", "member_bizno"),)

    id: Mapped[int] = pk()
    bid_ntce_no: Mapped[str] = mapped_column(Text)
    bid_ntce_ord: Mapped[str] = mapped_column(Text)
    bizno: Mapped[str | None] = mapped_column(Text)  # 주계약업체(낙찰 행의 bizno)
    member_bizno: Mapped[str] = mapped_column(Text)
    member_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)  # 주계약업체·도급업체
    joint_mode: Mapped[str | None] = mapped_column(Text)  # 공동·분담·혼합방식
    share: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # 지분율(%)
    fetched_at: Mapped[datetime] = ts_now()


class OrgSettings(Base):
    """우리 회사 설정. 서비스 전체에 한 행(id=1). 관리자만 수정 (§15.3)."""

    __tablename__ = "org_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint(f"our_bizno IS NULL OR our_bizno {BIZNO_CHECK}", name="our_bizno"),
        CheckConstraint("backfill_years BETWEEN 1 AND 10", name="backfill_years"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, server_default="1")
    our_bizno: Mapped[str | None] = mapped_column(Text)
    our_name: Mapped[str | None] = mapped_column(Text)
    # {"분야 이름": ["키워드", ...]}. 바꾸면 scripts/reclassify_awards.py로 fields를 다시 계산
    field_keywords: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    backfill_years: Mapped[int] = mapped_column(SmallInteger, server_default="5")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WatchedCompany(Base):
    """관심 경쟁사. 서비스 전체가 공유한다 (§15.3)."""

    __tablename__ = "watched_companies"

    bizno: Mapped[str] = mapped_column(
        ForeignKey("companies.bizno", ondelete="CASCADE"), primary_key=True
    )
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = ts_now()
