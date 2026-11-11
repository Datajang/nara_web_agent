# G2B API 사실 모음

출처: `narajangteo_mcp_server`의 CLAUDE.md를 복사·정리한 것. 원본 저장소는 수정하지 않는다.
v2의 호출 구조(DB-first, 일일 예산, 단일 실행)는 `docs/SPEC.md` §5가 우선한다. 여기는 API 자체의 성질만 적는다.

## 서비스키 2개 (이름은 v1 .env 그대로)

| 환경변수 | 대상 | 비고 |
|---|---|---|
| `NARA_API_KEY` | 입찰공고 | data.go.kr "나라장터 입찰정보" |
| `NARA_PRESPEC_API_KEY` | 사전규격 | 별도 서비스라 키가 따로 필요 |

서비스키는 쿼리스트링에 실린다. 요청 URL 전체를 로그·예외 메시지에 남기지 않는다(규칙 4).

## 엔드포인트

| 구분 | 오퍼레이션 | 기본 URL |
|---|---|---|
| 입찰공고 | `getBidPblancListInfoServcPPSSrch` | `http://apis.data.go.kr/1230000/ad/BidPublicInfoService` |
| 사전규격 | `getPublicPrcureThngInfoServcPPSSrch` | `http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService` |
| e발주 첨부 | `getBidPblancListInfoEorderAtchFileInfo` | 입찰공고와 같은 URL. v1이 첨부 없는 공고 보충에 사용 |

e발주 첨부 조회는 `inqryDiv=2`, `bidNtceNo=<공고번호>`로 부른다. 응답의 `eorderAtchFileNm`·`eorderAtchFileUrl`·`eorderDocDivNm`에서 문서구분 또는 파일명에 '제안요청'이 든 것만 쓴다. 그래도 없으면 공고의 `bfSpecRgstNo`로 사전규격 `specDocFileUrl1~5`를 교차 참조한다 (v1 `g2b_search.py`, 커밋 61519ad).

| 구분 | 키워드 파라미터 | 마감 필드 | 금액 필드 |
|---|---|---|---|
| 입찰공고 | `bidNtceNm` | `bidClseDt` | `bdgtAmt` / `presmptPrce` |
| 사전규격 | `prdctClsfcNoNm` | `opninRgstClseDt` | `asignBdgtAmt` |

MCP 서버는 용역(Service) 유형만 조회한다. v2의 조회 범위는 SPEC §5에서 확인할 것.

## 알려진 함정

- **조회 기간 제한**: 약 15일을 넘으면 HTTP 200에 `nkoneps.com.response.ResponseError`(resultCode 07)가 온다. 15일 단위로 나눠 호출한다.
- **오류 응답 2종**: 위의 07과, 잘못된 키의 HTTP 403 + `OpenAPI_ServiceResponse.cmmMsgHeader`. 정상은 `response.header.resultCode=00`.
- **페이지**: `numOfRows` 999 허용(2026-11 확인). 하루 일반공고 약 850건, 사전규격 약 420건.
- **정정 차수**: 같은 `bidNtceNo`가 `bidNtceOrd`(000~)별로 여러 줄 온다. 차수가 가장 큰 행이 최신.
- **`response.body.items` 모양이 세 가지**: `list`, `"item"` 키를 가진 `dict`(결과 1건), 문자열 `"null"`(결과 없음). 셋 다 처리한다.
- **날짜 형식이 섞여 있다**: `YYYYMMDDHHMM`, `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `YYYYMMDD`. 마감 판정 함수가 모두 받아야 한다.
- **사전규격 첨부 URL**은 `specDocFileUrl1~5` 필드에 있고 파일명 필드가 없다.
- 마감 여부와 관계없이 전부 돌려주고, 진행중/마감은 표시에만 쓴다(MCP 서버의 동작).
- **첨부 다운로드**: v1은 httpx가 아니라 `curl` 서브프로세스로 받는다. 주석상 이유는 "g2b TLS가 Python ssl과 호환되지 않음"이다. `--insecure`(인증서 검증 끔), 브라우저 UA, `-e https://www.g2b.go.kr/` 리퍼러를 쓴다. 2026-11 확인 결과 httpx(인증서 검증 켬)로 정상 다운로드되어 v2는 curl을 쓰지 않는다(`docs/decisions/2026-11-11-g2b-probe.md`).
