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

| 구분 | 키워드 파라미터 | 마감 필드 | 금액 필드 |
|---|---|---|---|
| 입찰공고 | `bidNtceNm` | `bidClseDt` | `bdgtAmt` / `presmptPrce` |
| 사전규격 | `prdctClsfcNoNm` | `opninRgstClseDt` | `asignBdgtAmt` |

MCP 서버는 용역(Service) 유형만 조회한다. v2의 조회 범위는 SPEC §5에서 확인할 것.

## 알려진 함정

- **조회 기간 제한**: 약 15일을 넘는 구간은 404가 난다. 15일 단위 청크로 나눠 호출하고 결과를 합친다.
- **`response.body.items` 모양이 세 가지**: `list`, `"item"` 키를 가진 `dict`(결과 1건), 문자열 `"null"`(결과 없음). 셋 다 처리한다.
- **날짜 형식이 섞여 있다**: `YYYYMMDDHHMM`, `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `YYYYMMDD`. 마감 판정 함수가 모두 받아야 한다.
- **사전규격 첨부 URL**은 `specDocFileUrl1~5` 필드에 있고 파일명 필드가 없다.
- 마감 여부와 관계없이 전부 돌려주고, 진행중/마감은 표시에만 쓴다(MCP 서버의 동작).
