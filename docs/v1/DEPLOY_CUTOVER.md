# v1 운영 서버 사실과 v2 전환 체크리스트

출처: v1 CLAUDE.md. P4(운영 전환) 때만 읽는다. v2 배포 구조는 `docs/SPEC.md` §11이 기준이다.

## v1 운영 서버 현황 [확인됨: v1 CLAUDE.md]

- systemd 서비스 2개, 위치 `/app/nara-web/`
  - `nara-api.service`: uvicorn, 포트 8001
  - `nara-vllm.service`: vLLM, 포트 8002 (유닛 파일은 저장소의 `deploy/nara-vllm.service`)
- 소스 원본: `/home/searching-doc-rag/AX_Team_Nara_bot/`
- 배포 방식: 원본에서 `/app/nara-web/`으로 복사·동기화한 뒤 서비스 재시작
- nginx: `frontend/`를 직접 서빙하고 `/api/`를 8001로 프록시
- DB: SQLite, 기본 경로 `/data/nara.db`

## v1과 v2 값 비교

| 항목 | v1 | v2 (SPEC §11) |
|---|---|---|
| API 포트 | 8001 | 8000 |
| vLLM 포트 | 8002 | 8001 |
| 배포 경로 | `/app/nara-web/` | `/opt/nara/app` |
| 설정 파일 | 저장소 `.env` | `/etc/nara/nara.env` |
| DB | SQLite 파일 | PostgreSQL |

포트와 경로가 다르므로 nginx 설정, 방화벽, 기존 사용자 북마크가 영향을 받는다. 포트를 v1 값에 맞출지 v2 값으로 바꿀지는 [미확인] 결정 사항이다. P4 시작 전에 `docs/decisions/`에 기록한다.

## 전환 체크리스트 [가정: 순서는 구현 시 조정]

1. 운영 서버에서 `/data/nara.db`를 백업하고 복사본으로 이전 스크립트를 먼저 시험한다.
2. 기존 `.env`에서 `NARA_API_KEY`, `NARA_PRESPEC_API_KEY`만 `/etc/nara/nara.env`로 옮긴다. 나머지 값은 새로 만든다. `SECRET_KEY`는 재사용하지 않는다(v1 토큰이 v2에서 통하면 안 된다).
3. v2를 다른 포트에 먼저 띄워 스모크 테스트(로그인, 검색, 분석 1건)를 한다.
4. 사용자에게 재가입이 아니라 계정 이전임을 공지한다. 비밀번호 해시 방식이 바뀌므로 첫 로그인 때 재설정이 필요한지 SPEC §4, §9에서 확인한다.
5. nginx 업스트림을 전환하고 v1 서비스는 지우지 말고 중지만 한다.
6. 롤백 방법: nginx를 되돌리고 `nara-api`, `nara-vllm`을 다시 시작한다. 이 절차를 전환 전에 한 번 실행해 본다.
7. L4 24GB 한 장에서 v1 vLLM(EXAONE)과 v2 vLLM(Qwen)을 동시에 띄우면 메모리가 모자랄 수 있다. 3번 스모크 테스트 전에 v1 `nara-vllm`을 멈출지, 같은 VM이 맞는지부터 확인한다 [가정].
