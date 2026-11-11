// 화면에서 쓰는 API 타입 별칭. 원본은 백엔드 OpenAPI에서 생성한 schema.d.ts (npm run gen:api).
import type { components } from './schema'

type S = components['schemas']
export type BidCard = S['BidCard']
export type SearchQuery = S['SearchQuery']
export type SearchResult = S['SearchResultOut']
export type BidDetail = S['BidDetail']
export type FileText = S['FileTextOut']
export type BidSummary = S['BidSummary']
export type AnalysisResult = S['AnalysisResult']
export type Profile = S['ProfileOut']
export type ProfileIn = S['ProfileIn']
export type ProfilePatch = S['ProfilePatch']
export type SearchRun = S['SearchRunOut']
export type SearchRunList = S['SearchRunList']
export type SearchRunDetail = S['SearchRunDetail']
export type AnalysisList = S['AnalysisList']
export type AnalysisSummary = S['AnalysisSummaryOut']
export type AnalysisDetail = S['AnalysisDetail']
export type Bookmark = S['BookmarkOut']
export type BookmarkList = S['BookmarkList']
export type Conversation = S['ConversationOut']
export type ChatMessage = S['MessageOut']
export type FeedbackIn = S['FeedbackIn']
export type UsageRow = S['UsageRow']
export type UsageOut = S['UsageOut']
export type FeedbackRow = S['FeedbackRow']
export type CollectorRun = S['CollectorRunOut']
export type CollectorRunList = S['CollectorRunList']
export type CollectorRunIn = S['CollectorRunIn']
export type Coverage = S['CoverageOut']
export type MePatch = S['MePatch']

// SSE 이벤트 (§6.4)
export type StatusEvent = S['StatusEvent']
export type TokenEvent = S['TokenEvent']
export type CardsEvent = S['CardsEvent']
export type ResultEvent = S['ResultEvent']
export type ActionEvent = S['ActionEvent']
export type ErrorEvent = S['ErrorEvent']
export type DoneEvent = S['DoneEvent']
export type StreamEvent =
  | StatusEvent
  | TokenEvent
  | CardsEvent
  | ResultEvent
  | ActionEvent
  | ErrorEvent
  | DoneEvent
export type Stage = StatusEvent['stage']
