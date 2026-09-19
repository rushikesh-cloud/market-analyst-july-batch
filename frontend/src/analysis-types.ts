import type { ApiRequestOptions } from './api-request'
import type { Company } from './company-types'

export type AgentType = 'fundamental' | 'technical' | 'news'
export type AnalysisStatus = 'queued' | 'running' | 'completed' | 'insufficient_data' | 'failed'
export type SafeAnalysisError = { code: string; message: string }
export type AnalysisRequest = <T>(path: string, options?: ApiRequestOptions) => Promise<T>
export type ParameterScore = {
  key: string; name: string; weight: number; score: number | null
  explanation: string; evidence_ids: string[]
}
export type EvidenceReference = {
  id: string; run_id: string; type: 'report_chunk' | 'article' | 'data_observation' | 'chart'
  excerpt: string | null
  observation: { key: string; value: number | null; unit: string | null; observed_at: string | null; description: string } | null
  source: {
    title: string; document_id: string | null; chunk_id: string | null; page: number | null
    fiscal_year: string | null; url: string | null; publisher: string | null
    published_at: string | null; publication_date: string | null
    date_precision: 'timestamp' | 'date' | 'unknown'; artifact_id: string | null
  }
  provenance: { provider: string; retrieved_at: string; tool: string; source_snapshot_id: string | null }
}
type FinancialMetric = {
  key: string; label: string; value: number | null; currency: string | null; scale: string
  fiscal_period: string; basis: 'consolidated' | 'standalone' | 'unknown'
  origin: 'reported' | 'derived'; evidence_ids: string[]
}
type FundamentalDetails = {
  kind: 'fundamental'; report_id: string | null; fiscal_year: string | null
  basis: FinancialMetric['basis']
  sector_profile: 'operating_company' | 'bank' | 'nbfc' | 'life_insurer' | 'general_insurer' | 'ambiguous' | null
  sector_evidence_ids: string[]; metrics: FinancialMetric[]; warnings: string[]
}
type TechnicalDetails = {
  kind: 'technical'; chart_artifact_id: string | null; data_artifact_id: string | null
  data_start: string | null; data_end: string | null; session_count: number
  adjustment: string | null; image_delivered: boolean; signal_agreement: string | null
  observations: { key: string; value: number | null; explanation: string; evidence_ids: string[] }[]
}
type NewsCategory = 'financial_results' | 'business_developments' | 'governance_regulatory'
type NewsDetails = {
  kind: 'news'; window_start: string; window_end: string; retained_article_count: number; coverage_description: string
  category_scores: { category: NewsCategory; score: number | null }[]
  events: {
    key: string; title: string; category: NewsCategory; sentiment: number | null; materiality: number
    factual_status: 'confirmed' | 'commentary' | 'allegation' | 'disputed'
    source_class: 'official' | 'attributable_reporting' | 'commentary' | 'uncorroborated'
    explanation: string; uncertainty: string | null; evidence_ids: string[]
    event_date: string | null; weight: number; eligible: boolean
  }[]
}
export type AgentResult = {
  schema_version: '1.0'; run_id: string; agent_type: AgentType
  status: 'completed' | 'insufficient_data'; company: Company; as_of: string
  evidence_dates: string[]; horizon: string; summary: string; parameters: ParameterScore[]
  final_score: number | null; confidence: 'low' | 'medium' | 'high'; coverage: number
  strengths: string[]; risks: string[]; limitations: string[]; evidence: EvidenceReference[]
  details: FundamentalDetails | TechnicalDetails | NewsDetails
}
export type AnalysisRun = {
  id: string; company_id: string; company: Company; agent_type: AgentType; status: AnalysisStatus
  created_at: string; started_at: string | null; finished_at: string | null; as_of: string | null
  progress: { stage?: string }; result: AgentResult | null; error: SafeAnalysisError | null
}
export type AnalysisHistoryResponse = { items: AnalysisRun[]; limit: number; offset: number }
export type AgentAvailability = { agent_type: AgentType; available: boolean; error: SafeAnalysisError | null }
export const agents: { type: AgentType; name: string }[] = [
  { type: 'fundamental', name: 'Fundamental' }, { type: 'technical', name: 'Technical' }, { type: 'news', name: 'News' },
]
export const statusLabels: Record<AnalysisStatus, string> = {
  queued: 'Queued', running: 'Running', completed: 'Completed', insufficient_data: 'Insufficient data', failed: 'Failed',
}
export function isActive(run: AnalysisRun) { return run.status === 'queued' || run.status === 'running' }
