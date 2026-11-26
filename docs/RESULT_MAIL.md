# 북마크 공고 결과 메일 (2026-11-25)

설계 `docs/superpowers/specs/2026-11-25-bid-result-mail-design.md`, 계획 `docs/superpowers/plans/2026-11-25-bid-result-mail.md`,
G2B 확인 `docs/decisions/2026-11-25-result-status-probe.md`. 코드 `backend/app/results/`.

## 무엇
북마크한 **일반공고**(사전규격 제외)의 결과가 G2B에 나오면 그 사람에게 메일. 개찰 결과 입력 지연은 p50 22분·p90 4시간,
입력되면 Open API에 바로 보인다 → 5분 타이머로 확인.

| 메일 | 언제 | 내용 |
|---|---|---|
| ① 개찰 결과 | 개찰결과 상태 '개찰완료' + 개찰완료 목록 있음 | 1순위(낙찰 예정자)·우리 순위·분류별 상위 10곳 투찰가(+외 N곳)·협상계약이면 점수 |
| ② 낙찰 결과 / 유찰 | 낙찰 행이 보임 / 모든 분류가 '유찰' | 낙찰자·낙찰금액(분류가 여럿이면 분류마다, +순위표) / 유찰 사실 |
| ③ 재공고가 올라왔어요 | 유찰 뒤 30일 안에 같은 수요기관·같은 사업명·`reNtceYn=Y` 공고가 수집됨(DB만) | 새 공고 링크 |

- 재입찰·재시담은 최종이 아니다(같은 공고에서 다시 개찰). 한 실행에서 개찰과 낙찰이 함께 보이면 ②만(순위표 포함)
- ② 때 그 실행에서 순위표를 받지 않았으면 한 번 더 받는다(① 뒤 한 분류만 재입찰된 경우). 우리 순위는 참가한 분류마다
- 받는 사람은 **감지한 실행에서** 정한다: 북마크 `notify_result` ∧ `users.result_mail` ∧ 활성 계정 ∧ 그 단계가 북마크
  **뒤에** 감지. `bid_result_mails`(UNIQUE)에 pending으로 넣고 감지 순서대로 보낸다. 보내기 직전에 꺼졌으면 cancelled,
  실패는 다음 실행(5분)에서 다시, 5번이면 failed. 감지 때 꺼 두었던 사람은 나중에 켜도 지난 결과를 받지 않는다
- 제목 `[{SERVICE_NAME}] 개찰 결과·낙찰 결과·유찰·재공고가 올라왔어요: {사업명}`, 끝에 '결과 메일은 설정 > 계정에서 끌 수 있어요.'

## 확인 간격 (`app/results/schedule.py`)
개찰 전 호출 없음. 개찰 결과 대기(waiting)는 개찰 뒤 7일까지 **5분**·그 뒤 3시간(2026-11-26, 운영 요청).
낙찰 대기(opened)는 개찰 뒤 3시간 5분 → 24시간까지 30분 → 3시간. 개찰 60일 뒤 `expired`(메일 없음).
개찰이 7일 넘게 지났거나 개찰일이 없는 북마크는 감시를 만들지 않고 매 실행 다시 읽지도 않는다(SQL에서 거름).
정정공고로 차수·개찰일이 바뀌면(① 뒤라도) 다시 기다린다. 감시 행은 `ON CONFLICT DO NOTHING`(북마크·타이머 동시 생성).
알림 켠 북마크가 없는 감시는 부르지 않는다. 최근 개찰한 공고부터 보고, 개찰 결과를 받은 뒤에는 낙찰만 묻는다(1회).
한 실행은 G2B 확인 150초까지(유닛 240초 안에 발송까지). 순서: 지난 대기열 발송 → 감시 맞추기 → 확인 → 대기열 → 발송.

## 데이터 (0013)
`bookmarks.notify_result`·`users.result_mail`(기본 true), `bid_result_watch`(공고별 단계 waiting·opened·final·expired,
final_kind awarded·failed, renotice_bid_id), `bid_result_mails`(user·bid·stage UNIQUE).

## API
- `PUT /bookmarks/{bid_id}` → 200 `{notify_result, watching, opening_at}`(전에는 204)
- `PATCH /bookmarks/{bid_id}` `{notify_result}` → 같은 모양. 내 북마크가 아니면 404
- `GET·PATCH /me`에 `result_mail`

## 화면
- 일반공고 북마크 직후 팝업 '결과가 나오면 메일로 알려드려요'(계정 스위치 켬일 때, '다시 보지 않기'는 이 브라우저
  `nara.resultMailNotice.hide`). 개찰일이 없으면 '개찰일 정보가 없어 결과 메일을 보내드릴 수 없어요.'
- 내 기록 > 북마크: 일반공고 카드마다 '결과 메일' 켜기/끄기. 설정 > 계정: '결과 메일 받기'(저장 실패 시 체크박스를 되돌림)

## 운영
`nara-result-watch.timer`(5분) → `python -m app.results`. 처음 한 번 `systemctl enable --now`(`docs/ops/RUNBOOK.md`).
G2B 몫 `G2B_RESULT_WATCH_DAILY_BUDGET`(3000, 낙찰정보서비스 — 낙찰 15,000 + 개찰 80,000과 합쳐 10만 아래). 결과 대기 공고 하나가 하루 288회(7일까지) → 동시에 10건 넘게 밀리면 그날 몫이 바닥나 최근 개찰 공고부터 본다.
