# 운영 진행 기록

운영 서버: 이 GCP VM(`searching-doc-rag`), 접속 `https://34-135-176-205.sslip.io`. 서버 맞춤 값은 `docs/ops/THIS_SERVER.local.md`(git 제외).

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
