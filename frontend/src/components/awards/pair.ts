// PairBars 한 줄: 우리·상대 값과 옆에 적을 글자. null은 '수집 중'.
export interface PairRow {
  key: string | number
  label: string
  us: number | null
  them: number | null
  usText: string
  themText: string
  collecting?: boolean
}
