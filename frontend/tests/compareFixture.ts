// 비교 응답 예시 (P10·P11 화면 테스트 공용). 테스트 파일끼리 import하면 테스트가 두 번 등록되므로 따로 둔다.
export const PERIOD = { from: '2021-11-11', to: '2026-11-10', counted_from: '2021-11-11', counted_to: '2026-11-10', collecting: false }
export const US = { bizno: '1234567890', name: '(주)예시컴퍼니' }
export const THEM = { bizno: '2345678901', name: '가온데이터시스템(주)' }

const v = (key: string, label: string, us: number | null, them: number | null, verdict: string, rule: string, small = false) => ({
  key,
  label,
  us,
  them,
  verdict,
  rule,
  small_sample: small,
})

export const COMPARE = {
  period: PERIOD,
  note: '두 회사 모두 수집 완료된 기간',
  us: US,
  them: THEM,
  verdicts: [
    v('count', '낙찰 건수', 7, 12, 'down', 'ratio_20'),
    v('amount_sum', '낙찰금액 합계', 700_000_000, 2_400_000_000, 'down', 'ratio_20'),
    v('amount_avg', '건당 평균 낙찰금액', 100_000_000, 200_000_000, 'down', 'ratio_20'),
    v('org_count', '낙찰한 수요기관 수', 3, 3, 'same', 'ratio_20'),
    v('field:AI', 'AI', 4, 1, 'up', 'field_2x'),
    v('field:데이터 정비', '데이터 정비', 1, 1, 'info', 'field_2x', true),
    v('head_to_head', '직접 맞붙은 공고', 2, 1, 'up', 'head_to_head', true),
    v('g2b_rate_median', '낙찰률(G2B) 중앙값', 87.5, null, 'info', 'info'),
  ],
  strengths: ['field:AI', 'head_to_head'],
  weaknesses: ['amount_sum', 'amount_avg', 'count'],
  coverage: { complete_from: '2021-11-11', collecting: false },
  head_to_head: { matched: 3, us_wins: 2, them_wins: 1 },
  by_year: [
    { year: 2025, us: 3, them: 5, collecting: false },
    { year: 2026, us: 4, them: 7, collecting: false },
  ],
  shared_orgs: [{ dminstt_cd: '1111111', dminstt_name: '행정안전부', us: 4, them: 2 }],
  joint: { collected: false, us: [], them: [] },
  watched: false,
}

