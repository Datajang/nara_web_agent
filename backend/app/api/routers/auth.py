"""/api/v1/auth (SPEC §6.2, §9.2). 속도 제한은 §6.1 표."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import Ctx, DbSession, client_ip
from app.api.schemas import (
    AcceptedOut,
    EmailIn,
    LoginIn,
    MeOut,
    RegisterIn,
    ResetIn,
    TokenIn,
    VerifyOut,
)
from app.api.security import REFRESH_COOKIE, clear_auth_cookies, set_auth_cookies
from app.auth.service import AuthService, normalize_email

router = APIRouter(prefix="/auth", tags=["auth"])

HOUR = 3600


def _svc(s: DbSession, ctx: Ctx) -> AuthService:
    return AuthService(s, ctx.deps.settings, ctx.mailer, ctx.deps.clock())


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, s: DbSession, ctx: Ctx) -> AcceptedOut:
    ctx.limiter.hit(f"register:ip:{client_ip(request)}", 5, HOUR)
    await _svc(s, ctx).register(body.email, body.password, body.display_name)
    return AcceptedOut()


@router.post("/verify-email")
async def verify_email(body: TokenIn, s: DbSession, ctx: Ctx) -> VerifyOut:
    return VerifyOut(status=await _svc(s, ctx).verify_email(body.token))  # type: ignore[arg-type]


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    body: EmailIn, request: Request, s: DbSession, ctx: Ctx
) -> AcceptedOut:
    ctx.limiter.hit(f"resend:ip:{client_ip(request)}", 5, HOUR)
    await _svc(s, ctx).resend_verification(body.email)
    return AcceptedOut()


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, s: DbSession, ctx: Ctx
) -> MeOut:
    ctx.limiter.hit(f"login:ip:{client_ip(request)}", 5, 60)
    ctx.limiter.hit(f"login:email:{normalize_email(body.email)}", 5, 60)
    session = await _svc(s, ctx).login(body.email, body.password, request.headers.get("user-agent"))
    set_auth_cookies(response, session, ctx.deps.settings)
    return MeOut.model_validate(session.user)


@router.post("/refresh")
async def refresh(request: Request, response: Response, s: DbSession, ctx: Ctx) -> MeOut:
    session = await _svc(s, ctx).refresh(
        request.cookies.get(REFRESH_COOKIE), request.headers.get("user-agent")
    )
    set_auth_cookies(response, session, ctx.deps.settings)
    return MeOut.model_validate(session.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, s: DbSession, ctx: Ctx) -> Response:
    """refresh 쿠키만으로 동작한다(access가 만료된 뒤에도 로그아웃할 수 있게)."""
    await _svc(s, ctx).logout(request.cookies.get(REFRESH_COOKIE))
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(resp, ctx.deps.settings)
    return resp


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: EmailIn, request: Request, s: DbSession, ctx: Ctx) -> AcceptedOut:
    ctx.limiter.hit(f"forgot:ip:{client_ip(request)}", 5, HOUR)
    await _svc(s, ctx).forgot_password(body.email)
    return AcceptedOut()


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(body: ResetIn, s: DbSession, ctx: Ctx) -> Response:
    await _svc(s, ctx).reset_password(body.token, body.password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
