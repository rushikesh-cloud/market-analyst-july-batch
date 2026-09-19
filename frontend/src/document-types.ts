type Company = { id: string; name: string; ticker: string }
export type Report = {
  id: string
  company_id: string
  company: Company
  fiscal_year: number
  filename: string
  storage_path: string
  status: string
  created_at: string
  updated_at: string
}
export type Stage = {
  name: string
  status: string
  completed_items: number | null
  total_items: number | null
  started_at: string | null
  finished_at: string | null
  error: string | null
}
export type ReportStatus = {
  document_id: string
  status: string
  attempt: number
  error: string | null
  stages: Stage[]
}
export type Chunk = {
  id: string
  sequence: number
  page_number: number
  chunk_type: string
  heading_path: string[]
  content: string
  overlap_text: string
  token_count: number
}
export type MarkdownPage = {
  markdown: string
  page: number
  page_count: number
}
