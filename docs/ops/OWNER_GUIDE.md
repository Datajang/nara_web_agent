# 운영자가 직접 할 일 — 순서와 방법 (2026-11-13)

저장소 작업은 끝났고, 아래는 권한·결정이 필요한 일이다. 위에서부터 순서대로 한다.
명령의 자세한 내용은 각 줄에 적힌 문서의 해당 절을 연다. 막히면 출력 그대로 Claude에게 붙여 넣는다.

## 0. 바로 할 일 (10분)
- **예전 GitHub 토큰 폐기**: GitHub → Settings → Developer settings → Personal access tokens에서
  예전 저장소 주소에 박혀 있던 토큰을 Delete. (지금 push는 `gh` 로그인으로 하므로 영향 없음)
- **개발 서버 임시 계정**: `ui-check@example.com`은 개발 DB에만 있다. 테스트가 끝나면 Claude에게 "지워 줘".

## 1. 메일(SMTP) 정하기 — 가입 인증·비밀번호 재설정에 필요
| 선택지 | 값 | 비고 |
|---|---|---|
| 회사 메일 서버 | IT팀에 SMTP 주소·포트(587)·계정 요청 | 가장 권장 |
| Google Workspace | `SMTP_HOST=smtp-relay.gmail.com`, 관리 콘솔에서 릴레이 허용 | 회사가 Workspace일 때 |
| 개인 Gmail(시범용) | `smtp.gmail.com:587`, 2단계 인증 후 **앱 비밀번호** | 하루 발송 한도 있음 |
- GCP는 25번 포트를 막지만 587은 된다. 정해지면 `/etc/nara/nara.env`의 `SMTP_*`, `MAIL_FROM`에 넣는다(3단계).
- 가입 정책도 같이 정한다: `ALLOWED_EMAIL_DOMAINS`(예: `corp.co.kr`)에 맞는 주소는 바로 가입,
  아니면 `REQUIRE_ADMIN_APPROVAL=true`로 관리자 승인.

## 2. 서버 준비 — `docs/ops/INSTALL.md` §1~§5 (약 1시간, sudo)
1. §1 사용자·디렉터리 → §2 PostgreSQL 16(5434) → §4 vLLM 설치 → §5 백업 키(개인키는 내 PC에만).
2. 각 절 끝에서 오류가 없는지 확인. `pg_lsclusters`에 `16 main 5434 online`이면 §2 완료.

## 3. 설정 파일 — INSTALL §3
- `SECRET_KEY`는 `openssl rand -hex 32`로 **새로** 만든다(v1 값 재사용 금지, CUTOVER §2).
- G2B 서비스키·LLM 키·DB 비번·SMTP·`ALERT_EMAIL`을 채운다. 이 파일은 절대 커밋·공유하지 않는다.

## 4. 외부 접속 — INSTALL §6 (gcloud 권한 있는 PC + 서버)
1. 외부 IP 고정 → 방화벽 80·443(사내 전용이면 사내 IP 대역만).
2. 서버에서 `set-host.sh <IP를-로>.sslip.io` → 브라우저로 `https://<주소>` 접속, 자물쇠 확인.

## 5. 첫 배포 — INSTALL §7, `DEPLOY.md`
1. 배포할 태그를 정한다(지금 기준 `v2` 브랜치 최신. 필요하면 Claude에게 "태그 만들어 줘").
2. `deploy.sh <태그>` → 서비스 5개 enable → `create-admin` → `collector backfill --days 90`(G2B 호출 약 180회).
3. 확인: DEPLOY "배포 후 확인" 목록(`/readyz` 200, 로그인, 검색, 분석 1건).

## 6. v1에서 넘어가기 — `CUTOVER.md`
- v1을 이름만 바꿔 보존(§1) → 키 옮기기(§2) → 공지·전환(§4).
- **전환 전에 롤백(§5)을 한 번 연습**하고 결과를 RUNBOOK 기록란에 적는다.

## 7. 백업 복원 리허설 — `RUNBOOK.md` "복원 리허설"
- 새벽 백업 파일 하나를 임시 DB로 복원 → 공고 수·회원 수가 맞는지 확인 → 기록란에 날짜·소요 시간.
- 분기마다 반복. 경보 메일(`ALERT_EMAIL`)이 오는지도 이때 한 번 확인.

## 8. 골든셋 정답 확정 — `eval/golden/README.md` (공고당 5~10분)
1. `eval/golden/items/g001.json`을 열고, 원문 `eval/golden/texts/g001.txt`(개발 서버에만 있음)와 대조.
2. `expect.budget_won`: 원문의 사업 예산(원). 지금 초안은 G2B 추정가격이라 틀린 것이 많다.
3. `expect.deadline`: 제안서 마감일 `YYYY-MM-DD`. `expect.method`: 원문의 계약·평가 방식.
4. `fit`: AI 플랫폼 개발팀 기준 high·mid·low. 다 보면 `"verified": true`.
5. 19건을 끝내면 Claude에게 "골든셋 다시 평가해 줘". 이후 운영 공고로 50건까지 채운다.

## 9. 파일럿 2주
- 대상 5~10명(입찰 담당 위주). 첫날 10분 안내: 관심 키워드 3개 → 홈 → 공고 분석 → 👍/👎.
- 매주 관리자 화면 "사용량"에서 👎 사유 상위 3개를 확인 → Claude에게 원인 분석·수정 요청.
- 2주 뒤 계속 쓸지, 무엇을 고칠지 결정.
