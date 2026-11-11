"""가입·인증·로그인·잠금·재설정과 상태 전이 (SPEC §9.1~9.3).

열거 방지 원칙: 가입·재전송·재설정 요청은 계정 유무와 무관하게 같은 응답, 로그인 실패·잠금도
이메일 해시 기준이라 없는 이메일과 같은 응답이 나온다. 비밀번호가 맞은 뒤에만 계정 상태를 본다.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, case, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import Mail, Mailer, already_registered_mail, reset_mail, verify_mail
from app.auth.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password,
    verify_password,
)
from app.auth.tokens import create_access_token, hash_token, new_token
from app.config import Settings
from app.db.models.personal import EmailToken, LoginFailure, RefreshToken, User
from app.errors import ApiError

log = logging.getLogger(__name__)

STATUS_ERRORS = {
    "pending_verification": "email_not_verified",
    "pending_approval": "pending_approval",
    "disabled": "disabled",
}


def normalize_email(email: str) -> str:
    return email.strip().lower()


def invalid_token() -> ApiError:
    return ApiError(400, "invalid_token", "링크가 만료되었거나 이미 사용됐어요.")


def invalid_credentials() -> ApiError:
    return ApiError(401, "invalid_credentials", "이메일 또는 비밀번호가 맞지 않아요.")


def password_error(e: PasswordPolicyError, field: str = "password") -> ApiError:
    return ApiError(
        422,
        "validation_error",
        "비밀번호 조건을 확인해 주세요.",
        details=[{"field": field, "reason": e.reason}],
    )


@dataclass(frozen=True)
class AuthSession:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, s: AsyncSession, settings: Settings, mailer: Mailer, now: datetime) -> None:
        self.s = s
        self.settings = settings
        self.mailer = mailer
        self.now = now

    # ---------- 가입·인증 ----------

    async def register(self, email: str, password: str, display_name: str) -> None:
        email = normalize_email(email)
        domain = email.rsplit("@", 1)[-1]
        if self.settings.email_domains and domain not in self.settings.email_domains:
            raise ApiError(
                422,
                "validation_error",
                "가입할 수 없는 이메일 도메인이에요.",
                details=[{"field": "email", "reason": "domain_not_allowed"}],
            )
        try:
            validate_password(password, self.settings.password_min_length)
        except PasswordPolicyError as e:
            raise password_error(e) from e
        pw_hash = hash_password(password)  # 기존 계정이어도 계산해 응답 시간을 맞춘다
        uid = await self.s.scalar(
            insert(User)
            .values(email=email, password_hash=pw_hash, display_name=display_name.strip())
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User.id)
        )
        if uid is None:
            mail = already_registered_mail(self.settings, email)
        else:
            token = await self._issue_email_token(uid, "verify")
            mail = verify_mail(self.settings, email, token)
            log.info("auth.register user_id=%s", uid)
        await self.s.commit()
        await self._send(mail)

    async def verify_email(self, token: str) -> str:
        uid = await self._consume_email_token(token, "verify")
        user = await self.s.get_one(User, uid)
        if user.status == "pending_verification":
            user.email_verified_at = self.now
            user.status = "pending_approval" if self.settings.approval_required else "active"
        await self.s.commit()
        log.info("auth.verify user_id=%s status=%s", uid, user.status)
        return user.status

    async def resend_verification(self, email: str) -> None:
        user = await self._user_by_email(normalize_email(email))
        if user is None or user.status != "pending_verification":
            return
        token = await self._issue_email_token(user.id, "verify")
        await self.s.commit()
        await self._send(verify_mail(self.settings, user.email, token))

    # ---------- 로그인·세션 ----------

    async def login(self, email: str, password: str, user_agent: str | None) -> AuthSession:
        email = normalize_email(email)
        key = hash_token(email)
        failure = await self.s.get(LoginFailure, key)
        if failure and failure.locked_until and failure.locked_until > self.now:
            raise self._locked(failure.locked_until)

        user = await self._user_by_email(email)
        ok, new_hash = verify_password(password, user.password_hash if user else None)
        if not ok or user is None:
            await self._record_failure(key)
            raise invalid_credentials()

        if failure is not None:
            await self.s.delete(failure)
        if new_hash:
            user.password_hash = new_hash  # v1 bcrypt → argon2id (§9.2-5)
        if user.status != "active":
            await self.s.commit()
            raise ApiError(403, STATUS_ERRORS[user.status], _STATUS_MESSAGES[user.status])
        user.last_login_at = self.now
        session = await self._start_session(user, user_agent, family=None)
        await self.s.commit()
        log.info("auth.login user_id=%s", user.id)
        return session

    async def refresh(self, raw: str | None, user_agent: str | None) -> AuthSession:
        if not raw:
            raise ApiError(401, "unauthorized", "다시 로그인해 주세요.")
        row = await self.s.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)).with_for_update()
        )
        if row is None:
            raise ApiError(401, "unauthorized", "다시 로그인해 주세요.")
        if row.rotated_at is not None or row.revoked_at is not None:
            # 이미 교체·폐기된 토큰이 다시 왔다 = 탈취 의심. 같은 로그인 가족 전부 폐기 (§9.3)
            await self._revoke(RefreshToken.family_id == row.family_id)
            await self.s.commit()
            log.warning("auth.refresh_reuse user_id=%s family revoked", row.user_id)
            raise ApiError(401, "unauthorized", "다시 로그인해 주세요.")
        if row.expires_at <= self.now:
            raise ApiError(401, "unauthorized", "다시 로그인해 주세요.")
        user = await self.s.get_one(User, row.user_id)
        if user.status != "active":
            await self._revoke(RefreshToken.family_id == row.family_id)
            await self.s.commit()
            raise ApiError(401, "unauthorized", "다시 로그인해 주세요.")
        row.rotated_at = self.now
        session = await self._start_session(user, user_agent, family=row.family_id)
        await self.s.commit()
        return session

    async def logout(self, raw: str | None) -> None:
        if raw:
            await self._revoke(RefreshToken.token_hash == hash_token(raw))
            await self.s.commit()

    # ---------- 비밀번호 ----------

    async def forgot_password(self, email: str) -> None:
        user = await self._user_by_email(normalize_email(email))
        if user is None or user.status == "disabled":
            return
        token = await self._issue_email_token(user.id, "reset")
        await self.s.commit()
        await self._send(reset_mail(self.settings, user.email, token))

    async def reset_password(self, token: str, password: str) -> None:
        try:
            validate_password(password, self.settings.password_min_length)
        except PasswordPolicyError as e:
            raise password_error(e) from e
        uid = await self._consume_email_token(token, "reset")
        user = await self.s.get_one(User, uid)
        user.password_hash = hash_password(password)
        await self._revoke(RefreshToken.user_id == uid)
        failure = await self.s.get(LoginFailure, hash_token(user.email))
        if failure is not None:
            await self.s.delete(failure)
        await self.s.commit()
        log.info("auth.reset user_id=%s", uid)

    async def change_password(
        self, user: User, current: str, new: str, user_agent: str | None
    ) -> AuthSession:
        ok, _ = verify_password(current, user.password_hash)
        if not ok:
            raise ApiError(400, "invalid_password", "현재 비밀번호가 맞지 않아요.")
        try:
            validate_password(new, self.settings.password_min_length)
        except PasswordPolicyError as e:
            raise password_error(e, "new_password") from e
        user.password_hash = hash_password(new)
        await self._revoke(RefreshToken.user_id == user.id)  # 다른 기기 전부 로그아웃 (§9.2-7)
        session = await self._start_session(user, user_agent, family=None)
        await self.s.commit()
        log.info("auth.password_changed user_id=%s", user.id)
        return session

    # ---------- 내부 ----------

    async def _user_by_email(self, email: str) -> User | None:
        return await self.s.scalar(select(User).where(User.email == email))

    async def _issue_email_token(self, user_id: int, purpose: str) -> str:
        # 같은 용도의 이전 토큰은 무효 (§9.2-3)
        await self.s.execute(
            update(EmailToken)
            .where(
                EmailToken.user_id == user_id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
            .values(used_at=self.now)
        )
        raw, digest = new_token()
        ttl = (
            timedelta(hours=self.settings.verify_token_hours)
            if purpose == "verify"
            else timedelta(minutes=self.settings.reset_token_minutes)
        )
        self.s.add(
            EmailToken(
                user_id=user_id, purpose=purpose, token_hash=digest, expires_at=self.now + ttl
            )
        )
        await self.s.flush()
        return raw

    async def _consume_email_token(self, raw: str, purpose: str) -> int:
        row = await self.s.scalar(
            select(EmailToken)
            .where(EmailToken.token_hash == hash_token(raw), EmailToken.purpose == purpose)
            .with_for_update()
        )
        if row is None or row.used_at is not None or row.expires_at <= self.now:
            raise invalid_token()
        row.used_at = self.now
        return row.user_id

    async def _record_failure(self, key: str) -> None:
        t = LoginFailure.__table__
        base = insert(LoginFailure).values(
            email_hash=key, failures=1, locked_until=None, updated_at=self.now
        )
        expired = (t.c.locked_until.is_not(None)) & (t.c.locked_until <= self.now)
        stmt = base.on_conflict_do_update(
            index_elements=[t.c.email_hash],
            set_={
                "failures": case((expired, 1), else_=t.c.failures + 1),
                "locked_until": None,
                "updated_at": self.now,
            },
        ).returning(t.c.failures)
        failures = int((await self.s.execute(stmt)).scalar_one())
        if failures >= self.settings.login_max_failures:
            until = self.now + timedelta(minutes=self.settings.login_lock_minutes)
            await self.s.execute(
                update(LoginFailure)
                .where(LoginFailure.email_hash == key)
                .values(locked_until=until)
            )
        await self.s.commit()

    def _locked(self, until: datetime) -> ApiError:
        retry = max(1, int((until - self.now).total_seconds()))
        return ApiError(
            429, "account_locked", "로그인 시도가 많아 잠시 잠겼어요.", retry_after=retry
        )

    async def _start_session(
        self, user: User, user_agent: str | None, family: uuid.UUID | None
    ) -> AuthSession:
        raw, digest = new_token()
        self.s.add(
            RefreshToken(
                user_id=user.id,
                token_hash=digest,
                family_id=family or uuid.uuid4(),
                expires_at=self.now + timedelta(days=self.settings.refresh_token_days),
                user_agent=(user_agent or "")[:300] or None,
            )
        )
        access = create_access_token(
            user.id,
            user.role,
            self.now,
            self.settings.secret_key.get_secret_value(),
            self.settings.access_token_minutes,
        )
        return AuthSession(user=user, access_token=access, refresh_token=raw)

    async def _revoke(self, condition: ColumnElement[bool]) -> None:
        await self.s.execute(
            update(RefreshToken)
            .where(condition, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=self.now)
        )

    async def _send(self, mail: Mail) -> None:
        try:
            await self.mailer.send(mail)
        except Exception as e:  # 메일 실패가 응답(열거 방지)을 바꾸지 않게 한다
            log.warning("mail send failed: %s", type(e).__name__)


async def revoke_all_sessions(s: AsyncSession, user_id: int, now: datetime) -> None:
    await s.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


_STATUS_MESSAGES = {
    "pending_verification": "이메일 인증이 필요해요.",
    "pending_approval": "관리자 승인 후 사용할 수 있어요.",
    "disabled": "사용이 중지된 계정이에요.",
}
