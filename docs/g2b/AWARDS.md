# G2B 낙찰·계약 API 메모 (경쟁사 분석용)

출처: data.go.kr 낙찰정보서비스·계약정보서비스 활용 가이드(사용자가 올린 문서). `[문서]`는 문서 기준이고 실제 응답으로는 아직 확인 전, `[확인됨]`은 probe로 확인한 것이다. probe 결과는 `docs/decisions/2026-11-16-awards-probe.md`가 우선한다.

## 기본
- 낙찰정보서비스: `http://apis.data.go.kr/1230000/as/ScsbidInfoService/` 계약정보서비스: `.../1230000/ao/CntrctInfoService/` [문서]
- 공통 요청: `ServiceKey`, `pageNo`, `numOfRows`, `type=json`. 키는 서비스마다 data.go.kr에서 따로 활용신청해야 한다 [문서]
- **조회 기간은 KST 날짜 7개까지** (2026-11-10부터). 분 길이가 아니라 시작일~종료일 날짜 차(6일 이하)로 센다. 넘으면 HTTP 200 + resultCode 07 '입력범위값 초과 에러' [확인됨]
- 날짜 형식 `YYYYMMDDHHMM`. `inqryDiv`: 1 등록일시, 2 공고일시, 3 개찰일시, 4 입찰공고번호(이때 `bidNtceNo` 필수) [문서]
- 공고번호: 신체계 `R25BK00927163`(R+연도2+단계2+일련), 구체계 11자리. `bidNtceOrd`는 차수(3자리). 낙찰 번호는 `bids.bid_no`와 그대로 같다 [확인됨]
- 한 공고에 `bidClsfcNo`(분류)·`rbidNo`(재입찰)별로 낙찰 행이 따로 있다 [확인됨]
- 기존 `NARA_API_KEY`로 낙찰·계약 서비스 모두 호출된다 [확인됨]

## 쓰는 오퍼레이션 (용역)
| 오퍼레이션 | 쓰임 |
|---|---|
| `getScsbidListSttusServc` | 낙찰 목록. 날짜 창으로 일괄 수집 |
| `getScsbidListSttusServcPPSSrch` | 낙찰 검색. 공고명 부분일치·기관·지역·업종·추정가격 범위·`bizno` 필터 (추정가격은 **검색 조건으로만** 있고 응답에는 없다) |
| `getOpengResultListInfoOpengCompt` | 개찰완료 목록. 업체별 순위·투찰금액·기술/가격/총점. `bidNtceNo` 필요 → 공고 단위로만 호출 |
| `getOpengResultListInfoServc` | 개찰결과 문자열(`opengCorpInfo`). 보조용. 협상계약은 금액·비율이 비어 있을 수 있음 |
| `getCntrctInfoListServc` | 계약 목록. `corpList`(10칸 `^` 연결, 3번째 칸이 단독·공동·분담·혼합방식, 10번째가 사업자번호). `cmmnCntrctYn`은 믿을 수 없음. `ntceNo`는 신체계 13자리(차수 없음)·구체계 11자리+차수·수의계약 빈 값 [확인됨] |

## `getScsbidListSttusServc` 응답 필드 [문서]
저장: `bidNtceNo`, `bidNtceOrd`, `bidNtceNm`, `prtcptCnum`(참가업체 수), `bidwinnrNm`, `bidwinnrBizno`(10자리), `sucsfbidAmt`(낙찰금액), `sucsfbidRate`(낙찰률, **예정가격 대비**), `rlOpengDt`, `dminsttCd`, `dminsttNm`, `rgstDt`, `fnlSucsfDate`.
저장하지 않음(개인정보): `bidwinnrCeoNm`, `bidwinnrAdrs`, `bidwinnrTelNo`, `fnlSucsfCorpOfcl`.
없는 것: 추정가격, 계약방식명. 추정가격은 `bids`에서 가져오고 없으면 null.

## `getOpengResultListInfoOpengCompt` 응답 필드 [문서]
`opengRank`, `prcbdrBizno`, `prcbdrNm`, `bidprcAmt`, `bidprcrt`, `bidPrceEvlVal`, `techEvlVal`, `techEvlNaturVal`, `totalEvlAmtVal`. 협상계약이면 점수 3종이 채워지고 `bidprcrt`는 대부분 빈다. 그 밖 방식은 반대 [확인됨].

## 실제 사용량 (P11, 2026-11-16 실측)
- 계약정보 용역은 **하루 약 4,300건**(14일 65,086건, 999행 67회). probe의 6일 2,997건보다 훨씬 많다. 공고번호가 있는 공동수급은 14일에 970공고
- 개찰완료 목록의 순위 빈칸 = 부적격·탈락, 사유는 `rmrk`(낙찰하한선 미달·협상평가부적격자). 순위는 유효 업체 안에서 1부터 빈 번호 없음 (P12-a)
- 개찰완료 목록은 `bidNtceNo`+`bidNtceOrd`(inqryDiv 없이)로 공고 1회. 실제 2건 확인: 행 수 = 참가업체 수, `opengRank`는 일부 업체만, 협상계약만 점수 3종

## 오류와 한계
- `numOfRows` 최대 999. **1000을 넣으면 오류 없이 10행만** 온다 [확인됨]. 용역 낙찰은 7일 창에 약 1,700건(2페이지).
  **페이지를 넘기면 순서가 흔들려 행이 겹치고 다른 행이 빠진다**(건수는 맞음) [확인됨 2026-11-25] → 한 페이지에 들어가게 시간(시·분)으로
  쪼개 받는다(시·분 필터 작동 확인). 2017-04-17 오전은 G2B가 173건이라 하고 172행만 준다(결함, 매번 같음)
- 공고의 추정가격이 1원처럼 잘못 들어온 경우가 있다(낙찰금액/추정가격 16,490). 비율이 2를 넘으면 비운다 [확인됨, 2026-11-17]
- 협상계약 낙찰은 `sucsfbidRate`가 대부분(약 92%) 비어 있다. 공동수급이어도 낙찰 응답은 주계약업체 1행뿐이다 [확인됨]
- 입찰공고서비스의 기존 규칙은 `docs/g2b/API.md`를 따른다(HTTP 200 + resultCode 07 등).
- 공개된 나라장터 낙찰만 있다. 민간 발주와 자체 전자조달 기관은 빠질 수 있다.
