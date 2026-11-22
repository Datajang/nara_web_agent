# 가입 정책 — 회사 도메인 자동 승인, 다른 도메인은 관리자 승인

- 명세 위치: §9.1 가입 정책, §9.7 환경변수
- 질문: 기존 정책은 둘 중 하나뿐이었다. `ALLOWED_EMAIL_DOMAINS`를 채우면 그 도메인만 가입(승인 없음),
  비우면 누구나 가입(전원 승인). "회사 메일은 바로, 외부 메일도 가입은 되지만 승인 후"를 표현할 수 없었다.
- 결정(사용자, 2026-11-22): `@cslee.co.kr`은 메일 인증만으로 사용, 다른 도메인은 메일 인증 + 관리자 승인.
- 구현: 새 설정 `AUTO_APPROVE_EMAIL_DOMAINS`(쉼표 구분). 이 도메인은 가입 허용 목록과 관계없이 가입되고,
  인증 뒤 `active`. 그 밖의 주소는 기존 정책(`approval_required`) 그대로 — 기존 설정의 뜻은 바꾸지 않았다.
  `Settings.signup_allowed(email)`, `Settings.approval_required_for(email)`.
- 운영 값: `ALLOWED_EMAIL_DOMAINS=`(비움) · `REQUIRE_ADMIN_APPROVAL=true` · `AUTO_APPROVE_EMAIL_DOMAINS=cslee.co.kr`.
- 테스트: `tests/unit/test_config_startup.py`, `tests/integration/test_auth_flow.py`(자동 승인·승인 대기·허용 목록).
