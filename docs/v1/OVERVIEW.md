# v1 구조와 v2 변경점

출처: v1 CLAUDE.md. v1 코드를 옮기거나 지울 때만 읽는다. 새 구현의 기준은 `docs/SPEC.md`다.

## 항목별 비교

| 항목 | v1 | v2 |
|---|---|---|
| 패키지 | `app/`(웹·DB·파이프라인) + `nara_server/`(G2B 클라이언트, 파일 추출) | `backend/app` 하나로 정리 (SPEC §3) |
| DB | SQLite + aiosqlite, 시작 시 테이블 자동 생성 | PostgreSQL + Alembic (SPEC §4) |
| 스키마 | User → Project → Conversation → Message, BookmarkedBid는 Project 소속 | 공유 계층 / 개인 계층 분리 (SPEC §4) |
| 인증 | JWT bearer (`python-jose`) | 쿠키 JWT + rotating refresh, argon2id (SPEC §9) |
| 대화 처리 | 키워드(찾아줘, 검색해줘 등)로 search / analyze / chat 분기 | 워크플로 + 읽기 전용 도구 호출 어시스턴트 (SPEC §6, §8) |
| LLM | EXAONE-3.5-7.8B-Instruct, vLLM | Qwen3.5-9B 기본, 프로파일로 교체 (SPEC §8) |
| 프론트 | `frontend/` 정적 HTML/CSS/JS, FastAPI StaticFiles | 빌드하는 프론트 + nginx 서빙 (SPEC §3, §11) |
| SSE 이벤트 | `status`, `token`, `cards`, `action`, `done` | SPEC §6.4 (이벤트 유형이 늘어남) |

## 옮길 것과 버릴 것

P0-a(2026-11-11)에서 v2 브랜치의 v1 실행 코드를 지웠다. 원본은 `git show 61519ad:<경로>`로 본다(예: `git show 61519ad:nara_server/g2b_api.py`). 무엇을 어디로 옮겼는지는 `docs/decisions/2026-11-11-p0a-repo-layout.md`에 있다.

- 옮긴다: `nara_server/g2b_api.py`(엔드포인트·파라미터 지식), `file_extractor.py`(HWP 대체 경로 등). 먼저 `docs/g2b/`를 읽고, 테스트를 붙인 뒤 `backend/app`으로 이동한다.
- 버린다: `app/pipeline/orchestrator.py`의 키워드 분기, bearer 인증 코드, SQLite 자동 생성 코드.
- v1 데이터 이전 방법은 SPEC §4 "v1 데이터 이전" 절을 따른다.

## v1 설정의 알려진 불일치

`vllm_base_url` 기본값은 `http://localhost:8000/v1`인데 실제 vLLM 서비스는 8002번 포트다. v1은 배포 시 환경변수로 덮어써서 쓴 것으로 보인다 [가정]. v2에서는 `LLM_BASE_URL`을 기본값 없이 필수로 두는 편이 안전하다.

## v1 환경변수

`VLLM_BASE_URL`, `VLLM_MODEL_NAME`, `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DB_PATH`(기본 `/data/nara.db`), `NARA_API_KEY`, `NARA_PRESPEC_API_KEY`.
v2 이름 대응은 SPEC 부록 A. 서비스키 두 개만 이름이 그대로다.
