// 입찰공고 목록 엑셀 파일 이름: "[오늘 날짜(한국)]_입찰공고 목록.xlsx" (2026-11-22). 서버 이름과 같다.
import { copy } from '@/copy'

const KST_DATE = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul' })

export function exportFilename(now: Date = new Date()): string {
  return copy.exportList.filename(KST_DATE.format(now))
}
