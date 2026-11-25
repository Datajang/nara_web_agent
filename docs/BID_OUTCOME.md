# 마감 공고 사유 배지 (2026-11-26)

설계 `docs/superpowers/specs/2026-11-26-closed-bid-reason-design.md`, 계획 `docs/superpowers/plans/2026-11-26-closed-bid-reason.md`,
G2B 확인 `docs/decisions/2026-11-26-opening-status-bulk.md`. 코드 `backend/app/bids/outcome.py`, `backend/app/awards/status.py`.

## 무엇
마감된 공고 카드(관심 공고·검색·추천·보관함)와 상세에 사유 배지 하나. 진행 중 공고는 그대로.

| 배지 | 언제(위에서부터 먼저 맞는 것) | 색 |
|---|---|---|
| (취소공고) | 지금 '취소공고' 배지 그대로, 사유 배지 없음 | 빨강 |
| 낙찰 · {업체} (외 N) | `bid_awards`에 현재 차수 낙찰 행 | 초록 |
| 유찰 · 무응찰/단독응찰/낙찰하한선 미달 | 모든 분류의 마지막 재입찰 행이 유찰. 문구를 못 묶으면 '유찰' | 빨강 |
| 개찰완료 · 1순위 {업체} | 한 분류라도 개찰완료(낙찰자 심사 중) | 주황 |
| 재입찰 | 재입찰·재시담 | 주황 |
| 개찰 전 MM.DD HH:mm / 결과 대기 | 상태 행 없음, 개찰일(raw opengDt)이 미래 / 지남 | 회색 |
| 의견 마감 | 사전규격 | 회색 |

- 공고의 **현재 차수**(raw `bidNtceOrd`) 행만 본다. 개찰일이 없는 마감은 배지 없음(지금처럼 '마감'만)
- 화면 요청은 DB만 읽는다(G2B 호출 없음). API `BidCard.outcome`(`kind·company·more·reason·opening_at`)

## 데이터 (0014)
`bid_opening_status`: 키 (공고번호·차수·분류·재입찰), 상태, 개찰·입력 일시, 참가 수, 결과 문구(200자), 1순위 업체.

## 수집 (`--source status`, 낙찰정보 서비스 키)
- 개찰결과 목록 `getOpengResultListInfoServc`를 **개찰일시(inqryDiv=3)** 7일 창으로, 999행 넘으면 시간으로 나눠 한 페이지씩
- 증분: `nara-collector.service`(10분)에서 공고 증분 뒤 어제·오늘(`-`라 실패해도 공고 결과와 무관)
- 백필: `nara-collector-awards.service`(04:30)에서 org_settings 연수만큼 과거로. 커버리지 `collector_coverage` source=status
- 예산 `G2B_STATUS_DAILY_BUDGET`(기본 3,000). 증분 하루 수백 회 + 백필 6년 약 1,500회(한두 날)

## 배포 뒤 한 번 (운영자)
마이그레이션 0014는 `deploy.sh`가 적용한다. 과거분을 바로 채우려면(아니면 다음 04:30에 자동):
`cd /opt/nara/app/backend && sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env /opt/nara/venv/bin/python -m app.collector backfill --source status --days 2192`
확인: 관리자 화면 수집 이력에서 source=status, 공고 카드에 배지.
