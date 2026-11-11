# 진행 기록

단계마다 '한 일 / 달라진 결정 / 남은 문제'를 3~5줄로 남긴다 (SPEC §13).

## P0-a — 저장소 정리·CI·테스트 골격 (2026-11-11, 태그 전 확인 대기)

- **한 일**: v1 재사용 모듈(extractor, section_extractor, g2b 순수 함수)을 `backend/app`으로 옮겼다. 나머지 v1 코드는 삭제(참조는 `61519ad`). Vite+Vue3+TS 프론트 골격, `.github/workflows/ci.yml` PR 게이트, `eval/smoke_llm.py`(5항목, 미실행)를 만들었다. pytest 31개 통과.
- **달라진 결정**: Python 3.12로 실행, `uv.lock` 추적, vitest ^5(npm peer 오류 회피), oxlint 제거. 실패 테스트 8개는 고침 2 / 버림 6. `is_bid_open`이 `YYYYMMDD`를 잘못 읽던 v1 버그를 고쳤다 (`docs/decisions/2026-11-11-*`).
- **남은 문제**: SPEC 수정 제안 대기(§2 docx 원인, §5.2 날짜 4종, vLLM 포트 8001이 v1 API 포트와 겹침). 첨부 다운로드의 curl `--insecure`는 P1에서 확인. gitleaks pre-commit 미도입. CI가 GitHub에서 실제로 초록인지는 push 후 확인해야 함. P0-b(vLLM 실측)는 GPU 서버에서 진행.

## P0-b — LLM 서버 검증 (2026-11-11, 태그 전 확인 대기)

- **한 일**: v1 vLLM을 중지(사용자 지시)하고, vLLM 0.19.1로 Qwen3.5-9B를 BF16과 FP8로 띄워 `smoke_llm.py` 5항목과 동시 8요청을 측정했다. 둘 다 전 항목 통과했다. 기록은 `docs/LLM_SETUP.md`와 `docs/decisions/2026-11-11-bf16-vs-fp8.md`.
- **달라진 결정**: 드라이버 550 때문에 vLLM은 0.19.1이 상한(0.20 이상은 CUDA 13). BF16 + 32K는 `--gpu-memory-utilization 0.95`가 필요(0.90에서 KV 부족). `qwen3_coder` 파서가 정상이라 `qwen3_xml` 폴백은 쓰지 않음.
- **남은 문제**: FP8 채택(사용자 결정). 품질 손실은 §12 골든셋에서 확인. v1 `nara-vllm`은 stop·disable 완료. 운영 포트(8000·8001 사용 중)와 `/opt/nara` 유닛은 P4에서.

## P1 — 데이터와 수집기 (2026-11-11, 태그 전 확인 대기)

- **한 일**: §4 전 테이블을 Alembic 2개(공유·개인)로 만들고, G2B 클라이언트(페이지네이션·재시도·예산·키 마스킹), 수집기 backfill/incremental/fill, DB-first 검색, single-flight, 첨부 파이프라인, 요약·분석·점수 캐시 계약(가짜 LLM)을 구현했다. 테스트 먼저(55개 실패 확인) → pytest 92개 통과. 실제 G2B로 90일 backfill(181회 호출, 52,177건).
- **달라진 결정**: Docker PG 16(5433), numOfRows 999, 정정공고는 최대 차수만 반영, `bid_files.attempts` 추가, 커버리지 1시간 여유, 점수에는 single-flight 미적용. httpx 로그가 서비스키를 찍던 문제를 발견해 고침 (`docs/decisions/2026-11-11-p1-implementation.md`, `-g2b-probe.md`).
- **남은 문제**: 사용자 결정 반영 — 취소공고는 검색에 남기고 "취소공고" 배지로 표시(P3), 커버리지 밖 fill은 "수집 중" 상태로(P3), 일일 예산 1000회. CI의 PG 서비스는 push 후 확인. collector timer는 파일만(설치는 P4).

## P2 — 회원과 프런트 골격 (2026-11-11, 태그 전 확인 대기)

- **한 일**: §9 가입(도메인·승인 정책)·메일 인증·로그인·쿠키 JWT·회전 refresh(재사용 감지)·잠금·재설정·관리자 승인 API와 `app.cli create-admin`, 개인 자원 예시로 프로필 CRUD. 프런트는 토큰·Tailwind 4·UI 프리미티브·앱 셸(반응형)·가드·401 단일 refresh 클라이언트·`useSse`·인증 화면 7개·관리자 사용자 화면. 테스트 먼저(백엔드 67개, 프런트 8파일 실패 확인) → pytest 161개, vitest 64개 통과, 브라우저 흐름 22항목 통과.
- **달라진 결정**: 로그인 실패는 이메일 해시 기준 `login_failures`(마이그레이션 0003), resend 엔드포인트 추가, logout은 refresh 쿠키만으로, `MAIL_BACKEND=memory`와 개발 전용 메일함, 폰트는 npm `pretendard` 묶음 (`docs/decisions/2026-11-11-p2-auth.md`).
- **남은 문제**: SPEC 수정 제안(§4·§6.2·§9.7·§10.2), SSE 형식과 사이드바 메뉴는 P3에서 §6.4·§7.1과 대조, e2e의 CI 편입·전 화면 axe·스크린샷 테스트는 P4, 회사 도메인·SMTP 미정(§14).

## P3a — 요약·분석·추천·어시스턴트 백엔드 (2026-11-11, 태그 전 확인 대기)

- **한 일**: §8.4 스키마·§8.5 프롬프트 5개·vLLM 클라이언트(재시도·repair·컨텍스트 초과)·토큰 계산·청킹, map→reduce 요약과 분석·점수(누락 ID 재요청), 추천·키워드 제안, b-ID 검증 어시스턴트, SSE 규약(§6.4)과 §6.2 엔드포인트 전부(35경로). 가짜 LLM만으로 테스트 먼저 → pytest 279개, 프런트 게이트(타입 재생성 포함) 통과.
- **달라진 결정**: '수집 중'(5초 대기 후 `collecting`), 취소공고 `cancelled` 표시, §6.3 검색 형식으로 정렬, usage는 done 전에 기록, lookup은 DB만, `LLM_BACKEND=fake` 개발용 (`docs/decisions/2026-11-11-p3a-llm-api.md`).
- **남은 문제**: P3a-2(사용자 결정) — vLLM 재기동·실제 클라이언트 스모크·골든셋 20건 라벨링·§8.8-1·2·4·5 실측. G2B 단건 조회 확인 스크립트. SPEC 수정 제안(§6.1·§6.2·§6.3·§8.3·부록 A).

## P3b — 탭 화면 (2026-11-11, 태그 전 확인 대기)

- **한 일**: §7 검색(URL 동기화·최근 검색·더 보기·카드/표), 상세·분석(SSE 단계·§7.5 순서·첨부 미리보기·피드백·공고번호로 열기), 추천(진행 막대·점수 카드), 어시스턴트(스트리밍·인라인 카드·중지·다시 시도), 내 기록, 프로필·계정 설정, 관리자 사용량·수집기, 403 화면. 테스트 먼저 → vitest 121개, 브라우저 e2e 46항목(§7.11, axe·375/768/1280px) 통과.
- **달라진 결정**: 대화 프로필 변경 API(사용자 승인 예외), SSE 이벤트 타입 매핑, action은 버튼, 403은 주소 유지 (`docs/decisions/2026-11-11-p3b-screens.md`).
- **남은 문제**: P3a-2(실제 vLLM·골든셋), e2e의 CI 편입과 스크린샷 비교는 P4, SPEC 수정 제안(§6.2·§7.6·§7.9).

## P4a — 운영 마감(저장소 작업) (2026-11-11, 태그 전 확인 대기)

- **한 일**: v2 systemd 유닛 7개(vLLM FP8·API·수집·백업·경보)·nginx(보안 헤더 snippet, SSE, 점검 경로 차단)·`deploy.sh`(자동 롤백)·`backup.sh`·`restore.sh`, JSON 로그·요청 ID, XFF 신뢰(127.0.0.1만), `/readyz` 수집 시각, 경보 점검, 피드백 사유(0004)와 관리자 집계, CI `audit`·`e2e`(Playwright) 잡, 부하 스크립트, `docs/ops/` 5개. 테스트 먼저 → pytest·vitest·배포 스크립트 시험·로컬 E2E·10명 부하(가짜 LLM) 통과.
- **달라진 결정**: 포트 8010/8011, PG16 5434, XFF는 덮어쓰기+마지막 값, 사유 집계는 usage 응답에, 자동 배포 미룸, v1 유닛 `nara-v1-*` 보존 (`docs/decisions/2026-11-11-p4-ops.md`).
- **남은 문제(P4b, 운영자)**: 도메인·SMTP·서버 설치·복원 리허설·전환/롤백 연습·Uptime Check, P3a-2 후 골든셋 50·모델 A/B·실제 부하, 파일럿 2주와 👎 상위 3개 조치. pip-audit langchain 18건 처리 결정. SPEC 수정 제안(§4·§6.2·§11).
