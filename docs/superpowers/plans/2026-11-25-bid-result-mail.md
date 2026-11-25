# 북마크 공고 결과 메일 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 북마크한 일반공고의 개찰 결과(①)와 최종 결과(② 낙찰·유찰·재공고)를 나오자마자 메일로 보낸다.

**Architecture:** `backend/app/results/` 새 패키지. 5분 systemd 타이머가 `python -m app.results`를 돌려, 감시 행
(`bid_result_watch`) 중 확인할 때가 된 공고만 G2B에 묻고, 단계가 바뀌면 받을 사람에게 한 번씩 메일을 보낸다
(`bid_result_mails` UNIQUE로 중복 방지). 북마크·스위치 API와 화면 세 곳(팝업·보관함·계정)을 더한다.

**Tech Stack:** FastAPI·SQLAlchemy async·Alembic·PostgreSQL 16, httpx G2B 클라이언트, aiosmtplib(기존 `Mailer`), Vue 3·vue-query·vitest.

**Spec:** `docs/superpowers/specs/2026-11-25-bid-result-mail-design.md`

## Global Constraints
- 일반공고(`bids.source == 'regular'`)만. 사전규격 제외
- 메일 두 통: ① 개찰 직후(참가 업체 순위·투찰가·우리 순위·1순위) ② 최종(낙찰자·낙찰금액 또는 유찰·재공고). 개찰 없이 낙찰이 먼저 보이면 ②에 순위·투찰가를 넣어 1통
- 받는 조건: 북마크 `notify_result` 켬 ∧ `users.result_mail` 켬 ∧ `users.status == 'active'` ∧ 그 단계 감지 시각 > 북마크 `created_at` ∧ 미발송
- 확인 간격: 개찰 전 호출 없음 → 개찰 뒤 3시간 5분 → 24시간까지 30분 → 이후 3시간, 개찰 60일 뒤 `expired`(메일 없음). 개찰 7일 넘게 지난 공고는 감시 행을 만들지 않음
- 경쟁사 투찰가 상위 10곳 + '외 N곳'. 우리 순위는 `org_settings.our_bizno`, 없거나 목록에 없으면 '미참가'. 협상계약이면 기술·가격·총점
- G2B 호출은 source `result_watch`로 따로 센다(`G2B_RESULT_WATCH_DAILY_BUDGET`, 기본 500). 서비스키·URL 전체 로그 금지(규칙 4)
- DB 변경은 Alembic(`0013_result_mail.py`), UI 문구 한국어(`frontend/src/copy.ts`), 외부 호출은 fake로만 테스트(규칙 3)
- 운영 서버 명령은 실행하지 않는다 — 유닛·명령은 `deploy/`·`docs/ops/RUNBOOK.md`에 남긴다
- 단계 끝 검사: `CLAUDE.md`의 백엔드·프론트 명령 전부(통합 테스트는 `TEST_DATABASE_URL` 지정, 281 skipped면 무효)

## Review Focus
1. 한 공고에 분류(`bidClsfcNo`)·재입찰(`rbidNo`) 행이 여러 개 → 메일은 공고당 단계별 1통, 행은 분류별로 묶어 표시 (Task 5·6 테스트)
2. 북마크 뒤 정정공고로 차수(`raw.bidNtceOrd`)·개찰일시가 바뀜 → 최신 차수·새 개찰일시로 다시 일정 (Task 4 테스트)
3. `raw.opengDt` 없음·형식 깨짐 → 감시 행 없음, 북마크는 성공, 팝업 문구는 '개찰일이 없어 알림을 못 드려요' (Task 4·9 테스트)
4. 한 실행에서 받는 사람 셋 중 한 명 SMTP 실패 → 나머지는 발송·기록, 실패자만 다음 실행에 재시도, 중복 0 (Task 7 테스트)
5. 실행 중 `result_watch` 예산 소진 → 남은 공고는 `next_check_at` 그대로 두고 정상 종료(exit 0) (Task 5 테스트)

---

### Task 1: [미확인] 확인 — 최종 결과·유찰·재공고 표시와 반영 지연

**Files:**
- Create: `backend/scripts/probe_results.py`, `docs/decisions/2026-11-25-result-status-probe.md`

**Interfaces:**
- Produces: 결정 문서에 (a) `getScsbidListSttusServc` `inqryDiv=4`+`bidNtceNo` 동작 여부 (b) 유찰·재입찰을 알리는 필드와 값(후보: `getOpengResultListInfoServc`의 `progrsDivCdNm`) (c) 재공고 판별법(같은 번호 새 차수 vs 새 공고번호) (d) 개찰 시각 대비 Open API 반영 지연(최근 개찰 공고 10건). Task 3·5가 이 값을 쓴다

- [ ] **Step 1:** 스크립트 작성 — 루트 `.env`의 `NARA_API_KEY`(없으면 사용자에게 추가 요청), 어제·오늘 개찰일시(`inqryDiv=3`)로 `getOpengResultListInfoServc`를 받아 `progrsDivCdNm` 값별 건수와 표본, 표본 공고마다 `inqryDiv=4` 낙찰·개찰완료 목록 유무와 `rlOpengDt`→첫 응답 시각 차를 출력. 호출 30회 이하, 키는 `G2BClient.mask` 방식으로 가림
- [ ] **Step 2:** 실행 → 결과를 결정 문서(템플릿 `docs/decisions/README.md`, 20줄 안쪽)에 기록
- [ ] **Step 3:** 결과가 설계 가정(유찰·재입찰이 응답 필드로 구분됨)과 다르면 **여기서 멈추고 사용자에게 보고**. 같으면 Task 3·5의 판별 규칙을 결정 문서 값으로 채운다
- [ ] **Step 4:** Commit `docs: 개찰·낙찰 결과 표시 확인(결과 메일 사전 확인)`

### Task 2: 마이그레이션·모델

**Files:**
- Create: `backend/alembic/versions/0013_result_mail.py`
- Modify: `backend/app/db/models/personal.py`(Bookmark·User 컬럼, `BidResultMail`), `backend/app/db/models/shared.py`(`BidResultWatch`), `backend/app/db/models/__init__.py`
- Test: `backend/tests/integration/test_result_models.py`

**Interfaces:**
- Produces: `Bookmark.notify_result: bool`(server_default true), `User.result_mail: bool`(true), `BidResultWatch`(bid_id PK FK bids CASCADE, stage text CHECK `waiting|opened|final|expired`, notice_ord text, opening_at, next_check_at, opened_at, final_kind text CHECK `awarded|failed|rebid` NULL, final_at, checks int, updated_at), `BidResultMail`(id, user_id FK CASCADE, bid_id FK CASCADE, stage CHECK `opened|final`, sent_at, UNIQUE(user_id,bid_id,stage)). 인덱스 `ix_bid_result_watch_due(next_check_at) WHERE stage IN ('waiting','opened')`

- [ ] **Step 1:** 실패 테스트 `test_existing_bookmark_defaults_on`(마이그레이션 전 행이 켬으로 읽힘), `test_result_mail_unique_per_stage`(같은 user·bid·stage 두 번 INSERT → IntegrityError)
- [ ] **Step 2:** 실행 → FAIL(컬럼 없음)
- [ ] **Step 3:** 마이그레이션(downgrade 포함, 이전 코드와 호환 §11.5)·모델 작성
- [ ] **Step 4:** `uv run alembic -x url=... upgrade head && ... downgrade -1 && ... upgrade head`, 테스트 PASS
- [ ] **Step 5:** Commit `feat: 결과 메일 테이블·컬럼(0013)`

### Task 3: G2B 호출 두 개 + 예산

**Files:**
- Modify: `backend/app/g2b/client.py`, `backend/app/config.py`, `backend/app/runtime.py`, `backend/tests/fakes/g2b.py`
- Test: `backend/tests/integration/test_g2b_client.py`

**Interfaces:**
- Produces: `ENDPOINTS["result_watch"]`(개찰완료 목록과 같은 오퍼레이션), `RESULT_WATCH_SOURCE = "result_watch"`, `G2BClient.award_by_notice(bid_ntce_no: str) -> list[dict[str, Any]]`(낙찰, Task 1 확인 파라미터, 그 번호 행만), `G2BClient.opening_status(bid_ntce_no: str, bid_ntce_ord: str) -> list[dict[str, Any]]`(Task 1이 정한 오퍼레이션·필드). 셋 다 source `result_watch` 예산. `Settings.g2b_result_watch_daily_budget: int = 500`. fake에 같은 메서드
- 기존 `opening_results(..., source="result_watch")` 그대로 재사용

- [ ] **Step 1:** 실패 테스트 `test_award_by_notice_filters_number`, `test_opening_status_parses_rows`, `test_result_watch_budget_separate`(result_watch 몫이 0이면 `G2BBudgetExceeded`, awards 몫은 그대로)
- [ ] **Step 2:** FAIL 확인 → 구현 → PASS → Commit `feat: 결과 확인용 G2B 호출과 예산`

### Task 4: 감시 일정과 등록 (`app/results/schedule.py`, `watch.py`)

**Files:**
- Create: `backend/app/results/__init__.py`, `schedule.py`, `watch.py`
- Test: `backend/tests/unit/test_result_schedule.py`, `backend/tests/integration/test_result_watch.py`

**Interfaces:**
- Produces: `next_check(opening_at: datetime, now: datetime) -> datetime | None`(None = 60일 지남 → expired; 개찰 전이면 opening_at), `opening_of(bid: Bid) -> tuple[str, datetime] | None`(`raw.bidNtceOrd` 기본 '000'·`parse_kst(raw.opengDt)`, 없거나 깨지면 None), `async ensure_watch(s, bid: Bid, now) -> BidResultWatch | None`(regular 아님·개찰 없음·개찰 7일 초과면 None, 있으면 차수·개찰이 바뀐 경우 갱신하고 stage `waiting`으로 되돌림), `async sync_watches(s, now) -> int`(notify 켠 일반공고 북마크 중 감시 행이 없는 것 만들기 + 진행 중 감시의 차수·개찰 재확인 — 기존 북마크와 수집기가 받은 정정공고를 여기서 맞춘다)

- [ ] **Step 1:** 단위 테스트 표: 개찰 1시간 전 → opening_at / 개찰+10분 → +5분 / +5시간 → +30분 / +30시간 → +3시간 / +61일 → None. 통합: `test_prespec_not_watched`, `test_missing_opening_not_watched`, `test_old_opening_not_watched`(8일 전), `test_revision_reschedules`(차수 001→002, 개찰일 변경 → notice_ord·opening_at·next_check_at 갱신, Review 2), `test_sync_creates_for_existing_bookmarks`
- [ ] **Step 2:** FAIL → 구현 → PASS → Commit `feat: 결과 감시 일정·등록`

### Task 5: 결과 확인기 (`app/results/checker.py`)

**Files:**
- Create: `backend/app/results/checker.py`
- Test: `backend/tests/integration/test_result_checker.py`

**Interfaces:**
- Consumes: Task 3 메서드, `participants.store(s, notice, items)`(행이 있을 때만 — 0행은 저장·표시하지 않음), `awards.collector.load_settings(deps)`·`award_store(keywords)`(낙찰 저장)
- Produces: `@dataclass Change(bid_id: int, stage: Literal['opened','final'])`, `async check_due(deps: Deps, now: datetime, limit: int = 200) -> list[Change]` — 확인할 때가 된 watch를 개찰 오래된 순으로; waiting이면 개찰완료 목록 → 있으면 `opened`; waiting·opened 모두 낙찰 → 있으면 `final/awarded`; Task 1 규칙으로 유찰 `final/failed`·재입찰·재공고 `final/rebid`; 같은 실행에서 opened와 final이 함께면 `Change(final)` 하나만. 바뀐 것 없으면 `next_check` 갱신·`checks+1`, None이면 `expired`. 예산 소진이면 거기서 멈추고 지금까지의 Change 반환

- [ ] **Step 1:** fake G2B로 실패 테스트: `test_opening_found_moves_to_opened`, `test_award_found_moves_to_final`, `test_award_before_opening_single_change`, `test_no_result_reschedules`, `test_expired_after_60_days`, `test_failed_and_rebid_kinds`(Task 1 값), `test_budget_exhausted_stops_cleanly`(Review 5), `test_multiple_classes_one_change`(분류 2·재입찰 1행 → Change 1개, Review 1)
- [ ] **Step 2:** FAIL → 구현 → PASS → Commit `feat: 북마크 공고 결과 확인기`

### Task 6: 메일 문안 (`app/results/mail.py`)

**Files:**
- Create: `backend/app/results/mail.py`
- Test: `backend/tests/unit/test_result_mail.py`

**Interfaces:**
- Produces: `@dataclass ResultView(title: str, bid_ref: str, org: str | None, rows: list[RankRow], our_rank: str, winner: str | None, amount: int | None, kind: Literal['opened','awarded','failed','rebid'], negotiated: bool)`, `RankRow(rank: int | None, name: str, bid_amount: int | None, scores: tuple[...] | None, remark: str | None, clsfc: str)`, `async load_view(s, bid_id, our_bizno) -> ResultView`, `render(view: ResultView, to: str, app_origin: str) -> Mail`(텍스트+HTML, 공고 상세 링크 `{APP_ORIGIN}/bids/b{id}`, 설정 링크 `{APP_ORIGIN}/settings/account`)
- 제목(정확한 문구): ① `[나라장터] 개찰 결과: {사업명}` ② `[나라장터] 낙찰 결과: {사업명}` / `[나라장터] 유찰: {사업명}` / `[나라장터] 재공고: {사업명}`. 본문 끝 `결과 메일은 설정 > 계정에서 끌 수 있어요.`

- [ ] **Step 1:** 실패 테스트: `test_opened_mail_has_rank_table`(1순위 업체 '낙찰 예정자' 표시, 12곳 → 10행 + '외 2곳'), `test_our_rank_missing_says_not_participated`, `test_awarded_mail_has_winner_amount`, `test_failed_mail_says_yuchal`, `test_negotiated_shows_scores`, `test_html_escapes_names`(업체명 `<b>`), `test_classes_grouped`(분류별 소제목, Review 1)
- [ ] **Step 2:** FAIL → 구현 → PASS → Commit `feat: 결과 메일 문안`

### Task 7: 받는 사람·발송 (`app/results/dispatch.py`) + CLI

**Files:**
- Create: `backend/app/results/dispatch.py`, `backend/app/results/__main__.py`
- Test: `backend/tests/integration/test_result_dispatch.py`

**Interfaces:**
- Consumes: Task 5 `Change`, Task 6 `load_view`·`render`, `build_mailer(settings)`
- Produces: `async recipients(s, change: Change) -> list[User]`(Global Constraints의 받는 조건, 감지 시각 = watch.opened_at/final_at), `async dispatch(deps, mailer: Mailer, changes: list[Change]) -> int`(사람마다 발송 성공 뒤 `BidResultMail` 기록, 실패는 로그만 남기고 다음 사람), `python -m app.results`(= `sync_watches` → `check_due` → `dispatch`, usage_logs event `collector`·cache.source `result_watch`)
- 재시도: 실행 시작 때 최근 7일 안에 감지됐는데 `BidResultMail`이 없는 (사람, 단계)도 다시 보낸다(SMTP 실패분)

- [ ] **Step 1:** 실패 테스트(MemoryMailer): `test_sends_once_per_stage`, `test_bookmark_off_or_switch_off_or_inactive_skipped`, `test_bookmarked_after_detection_skipped`, `test_smtp_failure_retried_next_run`(Review 4: 셋 중 하나 실패 → 2통, 다음 실행 1통, 총 3), `test_other_users_bookmarks_not_leaked`(메일 수신자 목록에 북마크 안 한 사람 없음)
- [ ] **Step 2:** FAIL → 구현 → PASS → Commit `feat: 결과 메일 발송과 CLI`

### Task 8: 유닛·런북

**Files:**
- Create: `deploy/systemd/nara-result-watch.service`(oneshot, `ExecStart=/opt/nara/venv/bin/python -m app.results`, 수집기 유닛과 같은 보안 옵션·EnvironmentFile), `deploy/systemd/nara-result-watch.timer`(`OnCalendar=*:0/5`, `Persistent=true`)
- Modify: `backend/tests/deploy/test_deploy_files.py`(유닛 목록), `deploy/nara.env.example`(`G2B_RESULT_WATCH_DAILY_BUDGET=500`), `docs/ops/RUNBOOK.md`(타이머 켜기 `sudo systemctl enable --now nara-result-watch.timer`, 확인 `journalctl -u nara-result-watch`)

- [ ] **Step 1:** 배포 테스트에 새 유닛 추가 → FAIL → 파일 작성 → `uv run pytest -q tests/deploy` PASS → Commit `feat: 결과 확인 타이머 유닛`

### Task 9: API

**Files:**
- Modify: `backend/app/api/schemas/history.py`(`BookmarkOut.notify_result`, `BookmarkPatch{notify_result: bool}`, PUT 응답을 `BookmarkPutOut{notify_result: bool, watching: bool, opening_at: datetime | None}` 200으로), `backend/app/api/routers/history.py`(PUT 때 `ensure_watch`, `PATCH /bookmarks/{bid_id}` 켤 때 `ensure_watch`), `backend/app/api/schemas/auth.py`(`MeOut.result_mail`, `MePatch.result_mail`), `backend/app/api/routers/me.py`, `frontend/src/api/openapi.json`·`schema.d.ts`(재생성)
- Test: `backend/tests/integration/test_api_history.py`, 계정 API 테스트 파일

- [ ] **Step 1:** 실패 테스트: `test_put_bookmark_returns_watching`(일반공고 개찰 미래 → watching true), `test_put_bookmark_prespec_not_watching`, `test_patch_bookmark_notify_off_on`, `test_patch_other_users_bookmark_404`, `test_me_result_mail_toggle`
- [ ] **Step 2:** FAIL → 구현 → `uv run python -m scripts.export_openapi && cd ../frontend && npm run gen:api` → PASS → Commit `feat: 결과 메일 켜기·끄기 API`

### Task 10: 화면 — 팝업·보관함·계정

**Files:**
- Create: `frontend/src/components/bid/ResultMailNotice.vue`(UiModal 사용)
- Modify: `frontend/src/composables/useBookmarkToggle.ts`, `frontend/src/views/BidDetailView.vue`, `frontend/src/views/LibraryView.vue`, `frontend/src/views/settings/AccountView.vue`, `frontend/src/api/bids.ts`·`library.ts`·`auth`(updateMe), `frontend/src/copy.ts`
- Test: `frontend/tests/resultMail.test.ts`

**Interfaces:**
- Consumes: Task 9 `BookmarkPutOut`, `PATCH /bookmarks/{bid_id}`, `MePatch.result_mail`
- 팝업 조건: 북마크 성공 ∧ `source === 'regular'` ∧ `me.result_mail` ∧ `localStorage['nara.resultMailNotice.hide'] !== '1'`(try/catch). 문구: 제목 `결과가 나오면 메일로 알려드려요`, 본문 `개찰 직후와 최종 결과(낙찰·유찰·재공고) 때 {이메일}로 보내드려요. 보관함에서 공고마다, 설정 > 계정에서 전체를 끌 수 있어요.`, `watching === false`면 본문 대신 `이 공고는 개찰일 정보가 없어 결과 메일을 보내드릴 수 없어요.`, 체크박스 `다시 보지 않기`, 버튼 `확인`
- 보관함: 북마크 카드마다 `결과 메일` 켜기/끄기(일반공고만, 사전규격은 숨김). 계정: `결과 메일 받기` 스위치(설명 `북마크한 공고의 개찰·낙찰 결과를 메일로 받아요`)

- [ ] **Step 1:** 실패 테스트: `shows notice after bookmarking regular bid`, `no notice for prespec`, `no notice when switch off`, `hide forever persists`, `library toggle calls patch`, `account switch calls updateMe`, `watching false shows no-opening text`(Review 3)
- [ ] **Step 2:** FAIL → 구현 → `npm run lint && npm run typecheck && npm run test && npm run build` PASS → Commit `feat: 결과 메일 팝업·보관함·계정 스위치`

### Task 11: 명세·진행 기록·전체 검사

**Files:**
- Modify: `docs/SPEC.md`(§4 테이블, §6.2 API, §7 화면, §9.6 메일 문안 — 각 §에 짧게, 길면 `docs/` 새 문서로 빼고 문서 지도에 추가), `docs/PROGRESS_ops_feedback.md`(한 줄)

- [ ] **Step 1:** 문서 반영(파일당 80줄 규칙)
- [ ] **Step 2:** `CLAUDE.md` 백엔드·프론트 명령 전부 실행 → 모두 통과(pytest 통과 수가 281 skip 없이 늘어난 값인지 확인)
- [ ] **Step 3:** Commit `docs: 결과 메일 명세 반영` — 배포(rc)는 사용자 요청 때
