# 운영 진행 기록

운영 서버: 이 GCP VM(`ai-project-server`, 2026-11-24 이전), 접속 `https://34-124-126-84.sslip.io`. 옛 VM은 `searching-doc-rag`(`34-135-176-205`).
서버 맞춤 값은 `docs/ops/THIS_SERVER.local.md`(git 제외).

## 운영 준비 지원 (2026-11-13)

- **한 일**: 운영자 안내 `docs/ops/OWNER_GUIDE.md`·`PILOT.md`, 메일 시험 `app.cli send-test-mail`, 주간 피드백 보고 `app.ops.feedback_report`, 서버 사전 점검(디스크 69GB 남음 → 모델 19GB만 복사로 INSTALL 수정, v1 유닛 이름 바꾸기를 첫 배포 앞으로), 개발 DB 백업·복원 사전 리허설(행 수 일치, 암호화는 대역).
- **남은 문제(운영자)**: OWNER_GUIDE 0~9단계. 서버 맞춤 명령은 `docs/ops/THIS_SERVER.local.md`(git 제외).

## 첫 운영 배포 (2026-11-19~22, 완료)

- **한 일**: INSTALL §1~§7을 Claude가 sudo로 실행(사용자 허락). PG16(5434, Debian 11 지원 종료로 PGDG 아카이브), vLLM 0.19.1·Qwen3.5-9B,
  nginx·certbot(sslip.io 인증서), 서비스·타이머 6개, 90일 공고 백필(57,098건), 서비스 전용 Gmail SMTP.
- **v1**: 전환 대신 중지(사용자 결정: v1은 쓰지 않음). 유닛은 `nara-v1-api`로 보존, DB는 `/var/backups/nara-v1-2026-11-22.db`.
- **개발 → 운영 이전**: 낙찰·계약·개찰·업체 테이블과 낙찰 수집 범위(coverage)를 그대로 복사(같은 회사 씨에스리 105-87-86298).
- **설치 중 발견**: GCP 방화벽과 별개로 VM의 ufw → 80·443 허용, `/opt/nara` 0751(nginx 통과), `/var/backups` 0755 유지(백업 실패 원인).
  `docs/ops/INSTALL.md`에 반영.
- **릴리스**: rc2(첫 배포) → rc3(회사 도메인 자동 승인, `docs/decisions/2026-11-22-auto-approve-domains.md`).

## 운영 피드백 1차 (2026-11-22)

- 승인 대기 알림: 외부 도메인 가입자가 메일 인증을 마치면 활성 관리자 전원에게 메일(`approval_request_mail`).
- 북마크 표시: 켜지면 관인 주홍으로 꽉 채움(`BookmarkIcon`, 4곳 공통).
- 사이드바 접기: 1024 이상에서 로고 옆 `<`로 아이콘만, `>`로 펼침, 브라우저마다 기억(`ui.sidebarCollapsed`, §10.3).
- 관심 경쟁사 버튼: 누르자마자 별이 바뀌고(낙관적 갱신, 실패하면 되돌림), 무거운 레이더는 다시 부르지 않음.
- 입찰공고 목록 다운로드: 관심 공고·공고 검색·맞춤 추천의 '목록 다운로드' → 13열 엑셀 (`docs/decisions/2026-11-22-bid-export.md`).
## 운영 피드백 2차 (2026-11-23)

- 관심 경쟁사 계정별 + [팀] 목록(0012), 둘러보기 검색 기록 제외, 비밀번호 확인 칸, 비밀번호 찾기 위치 (`docs/decisions/2026-11-23-watch-per-user.md`).
- 디스크: EXAONE·Qwen2.5-VL 캐시 삭제, nara uv 캐시 정리 → 81%. 탈락 결과 부족은 API 한계(개찰 조회 몫) — 대안 A·B·C 제안 중.
- **남은 문제**: 없음. 개발 vLLM은 운영과 GPU를 같이 못 쓴다(개발은 `LLM_BACKEND=fake`로).

## 서버 이전 준비 (2026-11-23)

- 사용자: searching-doc-rag 인스턴스를 지우고 새 VM으로 옮길 예정. `deploy/migrate/`(export·bootstrap·import)와
  `docs/ops/MIGRATE.md`. export→import 왕복 시험 통과(운영 건수·nara.env 동일, 한글 파일 이름, 개발 파일만 풀기).
  bootstrap은 빈 VM에서 아직 실제로 돌려 보지 못했다(이 VM에서는 시험 불가)

## 할 일 (사용자 결정 대기, 2026-11-23)

1. **'우리 수주 현황' 탈락 결과**: 탈락은 공고마다 개찰 결과를 열어야 알 수 있는데(API 한계), 하루 몫 300회를
   최근 공고가 다 써서 과거는 27건만 열어 봄. 방법을 정한다 —
   A. 공공데이터포털 운영계정 신청(한도 상향, 사용자) / B. 과거 공고에 하루 몫 일부 배정(코드 작음) /
   C. 화면에서 '투찰함' 표시 → 그 공고만 정확히 조회(기능 추가). 추천: B 먼저 + A 신청
2. **디스크 81%**(경보 기준 80%): `/var/tmp/tmp`의 2025-07 임시 파일 11.7GB 삭제 여부 확인 → 지우면 약 78%
3. **VM 중지 전**: 외부 IP 34.135.176.205가 고정(예약)됐는지 Cloud Shell에서 확인
   (`gcloud compute addresses list --filter="address=34.135.176.205"` → STATUS가 IN_USE/RESERVED면 고정).
   고정이 아니면 중지 때 IP가 바뀌어 접속 주소·인증서를 다시 설정해야 한다(`set-host.sh <새IP>.sslip.io`)


## 새 VM 이전 (2026-11-24)

- **한 일**: 새 VM `ai-project-server`(L4, 디스크 394GB → 사용 11%)로 이전. 새 IP라 주소가 `34-124-126-84.sslip.io`로 바뀜.
  이전 뒤 점검에서 `/etc/nara/nara.env` 두 가지를 고침(백업 `nara.env.before-fix-20261124T044801Z`, API 재시작 없음):
  `APP_ORIGIN`이 옛 주소로 되돌아가 있었음(import가 set-host 뒤에 덮어씀 — 실행 중 API는 새 값이라 재시작 때 로그인 403이 될 뻔함),
  값이 든 `ALERT_EMAIL` 뒤의 빈 `ALERT_EMAIL=`이 덮어써 **옛 서버에서도 경보 메일이 나가지 않았음** → 빈 줄 삭제.
- **확인**: 첫 수집 05:04 성공(일반 1,230건·사전규격 508건 새로, G2B 5회) → `/readyz` 전부 ok, 경보 해소.
  `send-test-mail`로 `ALERT_EMAIL` 수신 확인, 새 주소 로그인 확인.
- **남은 문제**: 백업(18:31)·낙찰 수집(04:34) 첫 실행 확인 뒤 옛 VM 삭제. 개발 환경(MIGRATE §6: `.env`·로컬 문서·개발 DB)은 아직 안 풀림.

## 운영 피드백 3차 (2026-11-24)

- 로그인 '이메일 기억하기': 기본 꺼짐, 로그인 성공 때만 이 브라우저에 이메일만 저장(`nara.login.email`, 비밀번호·토큰 저장 안 함 §9),
  체크를 풀면 바로 지움, 기억한 이메일이 있으면 비밀번호 칸에 커서. E2E 선택자 `getByLabel('이메일', { exact: true })`로.
- 개발 환경: 이 VM의 Node 22.14는 `engines`(22.18+)보다 낮고 Debian 11이라 Playwright chromium 미지원 →
  `~/.local/opt/node22`(22.23.5)와 Docker `mcr.microsoft.com/playwright:v1.65.0-noble`로 E2E 3개 통과.
