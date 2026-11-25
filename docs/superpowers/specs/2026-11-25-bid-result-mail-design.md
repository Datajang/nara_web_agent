# 북마크 공고 결과 메일 — 설계 (2026-11-25)

## 왜·무엇
직원은 북마크한 공고의 결과를 **바로** 알고 싶다(다음 날이면 쓸모없음, 사용자). 북마크한 **일반공고**의 결과가 G2B에
나오면 그 사람에게 메일을 보낸다. 사전규격은 제외(낙찰 없음).

- 목표: 개찰 뒤 수 분~수십 분 안에 1통, 최종 결과(낙찰 확정·유찰·재공고) 때 1통 (A 방식, 사용자 선택)
- 비목표: 사전규격, Teams·SMS 알림, 결과의 AI 해설, 북마크 안 한 공고 알림
- 실패로 보는 것: 같은 단계 메일 중복, 끈 사람에게 발송, 하루 늦은 발송, 남의 북마크가 드러남

## 사용자가 정한 것
- 메일 내용: 북마크한 사업명, 낙찰자와 금액, 우리 순위, 경쟁사 투찰가. 유찰·재공고면 그 사실
- 메일: ① 개찰 직후 — 참가 업체 순위·투찰가·우리 순위·1순위(낙찰 예정자) ② 최종 — 낙찰자·낙찰금액 또는 유찰 ③ 유찰 뒤 재공고가 올라오면(B 방식, 2026-11-25)
- 받는 사람: 일반공고 북마크 = 자동 켜짐, 북마크마다 끌 수 있음 + 계정 설정 '결과 메일 받기' 전체 스위치
- 북마크하면 '결과가 나오면 메일로 알려드려요' 팝업
- 방법: 결과 확인 전용 타이머(5분), 수집기와 분리

## 접근 (고려한 것)
1. **전용 타이머(채택)** — 수집기 실패·야간 1시간 간격과 무관, 호출 몫을 따로 셈. 유닛 하나 추가
2. 기존 수집기에 단계 추가 — 야간·주말 1시간 간격만큼 늦고 수집 실패에 같이 멈춤
3. 화면 열 때만 확인 — '바로'를 못 지켜 제외

## 설계
**데이터(Alembic)**: `bookmarks.notify_result bool default true`, `users.result_mail bool default true`,
`bid_result_watch`(bid_id PK, stage `waiting|opened|final|expired`, next_check_at, opened_at, final_kind
`awarded|failed`, final_at, renotice_bid_id, checks), `bid_result_mails`(user_id, bid_id, stage `opened|final|renotice`, sent_at, UNIQUE(user,bid,stage)).
기존 북마크도 켜짐 상태로 들어간다.

**감시 대상**: 북마크(notify on)가 하나라도 있는 일반공고 중 개찰 예정(`raw.opengDt`)이 있고 final이 아닌 것.
북마크·켜기 때 watch 행을 만든다(없으면). 개찰이 7일 넘게 지난 공고는 만들지 않는다.

**타이머 `nara-result-watch`(5분)**: `next_check_at <= now`인 watch만 G2B를 부른다. 간격(Claude 결정):
개찰 전엔 부르지 않음 → 개찰 뒤 3시간 5분마다 → 24시간까지 30분 → 이후 3시간마다, 개찰 60일 뒤 `expired`(메일 없음).
- ①: `getOpengResultListInfoOpengCompt`(공고번호·차수). 행이 있으면 저장(참가 업체 캐시 재사용) → stage `opened`, 메일①
- 상태: `getOpengResultListInfoServc`의 `progrsDivCdNm`(2026-11-25 확인, `docs/decisions/2026-11-25-result-status-probe.md`).
  개찰완료 → ①, 유찰 → ② 유찰, 재입찰·재시담 → 최종 아님(계속 감시)
- ②: `getScsbidListSttusServc`(inqryDiv=4) 낙찰 행 → `awarded`, 메일②
- 재공고(B 방식, 사용자 선택): 원공고와 직접 연결이 없어, 유찰 뒤 30일 동안 수집된 일반공고 중 `reNtceYn=Y` ∧ 같은
  수요기관 ∧ 같은 사업명(공백·'재공고' 표기 무시)을 DB에서 찾는다(G2B 호출 없음) → 메일③ '재공고가 올라왔어요'+링크.
  사업명이 바뀐 재공고는 놓칠 수 있다
- ①을 건너뛰고 바로 낙찰이 보이면 메일②에 순위·투찰가를 함께 넣는다(1통)
- 주의: 지금 `bid_participant_fetches`는 0행이어도 '받음'으로 표시해 다시 안 부른다. 감시는 결과가 나올 때까지 다시
  불러야 하므로 0행 표시를 쓰지 않는다(화면 온디맨드 동작은 그대로)
- 예산: 낙찰정보 API 몫에서 source `result_watch`로 따로 센다(usage_logs). 몫이 바닥나면 다음 실행에서 이어감

**발송 규칙**: (북마크 notify on) ∧ (users.result_mail on) ∧ (status active) ∧ (그 단계가 북마크 뒤에 감지됨) ∧
`bid_result_mails`에 없음. 발송 성공 뒤 행 기록 — 중복 방지는 UNIQUE. SMTP 실패는 다음 실행에서 재시도.
메일: 텍스트+HTML(기존 `Mailer`), 공고 상세 링크, '설정에서 끌 수 있어요' 링크. 경쟁사 투찰가는 상위 10곳 + 나머지 수.
우리 순위는 `org_settings.our_bizno`로 찾고 없으면 '미참가'. 협상계약은 점수(기술·가격·총점)도 표시.

**API**: 북마크 응답에 `notify_result`, `PATCH /bookmarks/{bid_id}`(notify_result), 계정 설정에 `result_mail`
(GET·PATCH, 기존 계정 API 확장). OpenAPI 재생성.

**화면**: 북마크 직후 팝업(일반공고 ∧ 전체 스위치 켬일 때, '다시 보지 않기'는 이 브라우저에 저장 — Claude 결정),
내 보관함 북마크마다 '결과 메일' 켜기/끄기, 계정 설정에 전체 스위치. 문구 한국어.

**운영**: `deploy/systemd/nara-result-watch.{service,timer}`, RUNBOOK에 확인 명령. 배포는 사용자.

## 만드는 사람에게 남긴 것
- 유찰·재공고가 G2B 응답에 어떻게 보이는지, 개찰 뒤 Open API 반영 지연 — 첫 단계 확인 스크립트로 확인 후 `docs/decisions/`
- 한 공고 여러 분류(`bidClsfcNo`)·재입찰(`rbidNo`) 행을 메일에 어떻게 묶을지
- 메일 HTML 모양, 정확한 문구
- 같은 작업 트리에서 다른 작업(G2B v1.3, `g2b/client.py`·`participants.py`)이 진행 중 — 그 커밋 뒤 시작
