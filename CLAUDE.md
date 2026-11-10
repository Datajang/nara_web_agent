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

- 저장소 루트 `.env`는 v1용이다. v2 테스트는 `.env`를 읽지 않아야 한다.
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
| 배포·systemd·nginx | `docs/SPEC.md` §11 |
| v1 코드를 옮기거나 지울 때 | `docs/v1/OVERVIEW.md` |
| v1 → v2 서버 전환(P4) | `docs/v1/DEPLOY_CUTOVER.md` |
| 확인 결과·결정 기록 | `docs/decisions/README.md` |
