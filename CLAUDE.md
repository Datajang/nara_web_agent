# nara-web v2 — 작업 지침

사내 직원용 나라장터(G2B) 입찰 검색·요약·분석 웹 서비스. 공유 DB 캐시(DB-first) + 로컬 sLLM(vLLM) 구조.
전체 설계는 `docs/SPEC.md`. **이 저장소만 수정한다.** `narajangteo_mcp_server`는 읽기 전용 참고용이며 수정하지 않는다.

## 작업 규칙

1. 한 번에 로드맵 한 단계만 구현한다. 단계가 끝나면 완료 조건을 체크하고 멈춰서 보고한다.
2. 테스트를 같이 쓴다. 단계 종료 전 `ruff`, `pytest`, 프론트 `typecheck`·`build`가 모두 통과해야 한다.
3. 외부 호출(G2B API, LLM, 파일 다운로드)은 항상 인터페이스 뒤에 둔다. 테스트는 fixture나 fake만 쓴다.
4. 비밀값을 커밋하지 않는다. G2B 서비스키가 쿼리스트링에 실리므로 요청 URL 전체를 로그에 남기지 않는다.
5. DB 변경은 Alembic 마이그레이션으로만 한다.
6. LLM에는 파일 URL이나 경로를 주지 않는다. 항상 짧은 bid_id(예: b123)로 참조시킨다.
7. [미확인] 항목은 추측 구현 금지. 먼저 확인용 스크립트를 쓰고 결과를 `docs/decisions/`에 남긴다.
8. 명세와 현실이 다르면 임의로 고치지 말고 사용자에게 묻거나 명세 수정을 제안한다.
9. UI 문구는 한국어, 코드 식별자는 영어, 주석은 한국어 허용.
10. `docs/SPEC.md`는 길다. 전체를 읽지 말고 `grep -n '^## ' docs/SPEC.md`로 목차를 본 뒤 필요한 § 만 읽는다.
11. `docs/` 문서는 파일당 약 80줄 이하로 유지한다. 넘으면 역할별로 나눠 아래 문서 지도에 추가한다.

## 명령 (P0-a에서 확정, CI `.github/workflows/ci.yml`과 같음)

```bash
cd backend && uv sync && uv run ruff check . ../eval && uv run ruff format --check . ../eval \
  && uv run mypy app ../eval && uv run pytest -q                                    # 백엔드 + eval
cd frontend && npm ci && npm run lint && npm run typecheck && npm run test && npm run build  # 프론트
```

- pytest는 PostgreSQL 16이 필요하다: 로컬은 Docker `nara-pg16`(127.0.0.1:5433, `docker start nara-pg16`), 접속 정보는 `backend/.env`의 `TEST_DATABASE_URL`(gitignore).
- 저장소 루트 `.env`(서비스키)는 테스트가 읽지 않는다. CLI는 `NARA_ENV_FILE=../.env,.env uv run python -m app.collector incremental` 처럼 명시한다.
- 마이그레이션: `uv run alembic -x url=$DATABASE_URL upgrade head`
- API 스키마를 바꾸면: `cd backend && uv run python -m scripts.export_openapi && cd ../frontend && npm run gen:api` (pytest·CI가 최신 여부를 검사)
- 개발 실행: 백엔드 `NARA_ENV_FILE=.env ENV=development MAIL_BACKEND=memory LLM_BACKEND=fake APP_ORIGIN=http://localhost:5173 COOKIE_SECURE=false uv run uvicorn app.main:app --port 8020`(실제 vLLM은 `LLM_BACKEND=vllm`), 프론트 `VITE_API_TARGET=http://127.0.0.1:8020 npm run dev`. 메일은 `GET /api/v1/_dev/mail`. 첫 관리자는 `uv run python -m app.cli create-admin --email <주소>`
- E2E 스모크(§12.8): `uv run python -m scripts.seed_e2e`(E2E_ADMIN·E2E_ADMIN_PW, 초대 흐름용 E2E_MEMBER·E2E_MEMBER_PW, 별도 DB) → 백엔드(가짜 LLM, APP_ORIGIN=http://localhost:4173) → `npm run build && npx vite preview --port 4173` → `npx playwright test`. 순서는 CI `e2e` 잡과 같다.
- 운영 서버 명령은 실행하지 않는다(사용자가 직접). 서버 작업은 `docs/ops/`에 명령으로 남긴다.
- v1 코드 참조: `git show 61519ad:<경로>` (v2 브랜치에서는 삭제됨).

## 문서 지도 — 해당 작업을 할 때만 읽는다

| 하는 일 | 읽을 파일 |
|---|---|
| 지금 할 단계·완료 조건 | `docs/SPEC.md` §13 |
| 어디까지 했는지 이어받기 | `docs/PROGRESS.md` |
| 테이블·마이그레이션 | `docs/SPEC.md` §4 |
| 수집기·캐시·G2B 호출 코드 | `docs/SPEC.md` §5 + `docs/g2b/API.md` |
| 첨부파일 다운로드·텍스트 추출 | `docs/SPEC.md` §5.6 + `docs/g2b/FILES.md` |
| API·SSE 규약 | `docs/SPEC.md` §6 |
| 화면·탭 기능 | `docs/SPEC.md` §7 |
| LLM 호출·프롬프트·모델 설정 | `docs/SPEC.md` §8 |
| vLLM 실행 명령·플래그·측정치 | `docs/LLM_SETUP.md` |
| 회원가입·로그인·권한·보안 | `docs/SPEC.md` §9 |
| 프론트엔드 구현·디자인 시스템 | `docs/SPEC.md` §10 |
| 테스트 작성 | `docs/SPEC.md` §12 + `docs/v1/TESTING.md` |
| 배포·systemd·nginx | `docs/SPEC.md` §11 + `docs/ops/DEPLOY.md` |
| 운영 서버 설치·런북·보안 점검 | `docs/ops/INSTALL.md`, `RUNBOOK.md`, `SECURITY.md` |
| 운영자가 직접 할 일의 순서(SMTP·설치·전환·골든셋·파일럿) | `docs/ops/OWNER_GUIDE.md` |
| v1 코드를 옮기거나 지울 때 | `docs/v1/OVERVIEW.md` |
| v1 → v2 서버 전환(P4) | `docs/ops/CUTOVER.md` (+ `docs/v1/DEPLOY_CUTOVER.md`) |
| 확인 결과·결정 기록 | `docs/decisions/README.md` |
