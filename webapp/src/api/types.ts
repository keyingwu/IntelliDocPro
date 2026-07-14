// Mirrors of the docstill pydantic models (src/docstill/*.py).

export type FieldType = 'text' | 'number' | 'date' | 'amount' | 'percent' | 'enum'
export type Confidence = 'high' | 'medium' | 'low'

export interface FieldSpec {
  name: string
  type: FieldType
  description?: string | null
  enum_values?: string[] | null
  required?: boolean
}

export interface ExtractionSchema {
  fields: FieldSpec[]
}

export interface SourceRef {
  page?: number | null
  location?: string | null
}

export interface FieldValue {
  field: string
  value: string | number | null
  raw_text?: string | null
  currency?: string | null
  confidence: Confidence
  source?: SourceRef | null
  needs_review: boolean
}

export interface ExtractionResult {
  values: FieldValue[]
  engine: string
  model: string
  usage: Record<string, number>
}

export interface Assistant {
  id: string
  name: string
  description: string
  engine: string
  model: string | null
  schema: ExtractionSchema
  created_at: string
  updated_at: string
  doc_count: number
  review_count: number
  failed_count: number
  total_cost_usd: number
}

export type BulkFileStatus = 'queued' | 'running' | 'done' | 'failed'

export interface CostBreakdown {
  engine: string
  model: string
  input_tokens: number
  output_tokens: number
  pricing_known: boolean
  total_cost: number
}

export interface BulkFileEntry {
  filename: string
  status: BulkFileStatus
  result?: ExtractionResult | null
  cost?: CostBreakdown | null
  needs_review?: boolean | null
  error?: string | null
  duration_s?: number | null
}

export interface BulkReport {
  status: 'running' | 'done'
  engine: string
  model: string | null
  total: number
  completed: number
  failed: number
  needs_review_files: number
  total_cost_usd: number
  entries: BulkFileEntry[]
}

export interface ResultRow {
  id: string
  run_id: string
  assistant_id: string
  filename: string
  status: 'done' | 'failed'
  needs_review: boolean | null
  error: string | null
  duration_s: number | null
  cost_usd: number | null
  values: FieldValue[]
  created_at: string
}

export interface Health {
  status: string
  engines: Record<string, boolean>
}

export interface ModelOption {
  id: string
  input_per_mtok: number | null
  output_per_mtok: number | null
}

export interface ModelsResponse {
  prices_as_of: string
  engines: Record<string, { default: string; models: ModelOption[] }>
}
