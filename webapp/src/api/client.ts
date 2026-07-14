import type {
  Assistant,
  BulkReport,
  ExtractionResult,
  ExtractionSchema,
  Health,
  ModelsResponse,
  ResultRow,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init)
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const body = await resp.json()
      detail = body.detail ?? body.error ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, detail)
  }
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

function json(body: unknown, method = 'POST'): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const api = {
  health: () => request<Health>('/health'),
  models: () => request<ModelsResponse>('/models'),

  listAssistants: () => request<Assistant[]>('/assistants'),
  getAssistant: (id: string) => request<Assistant>(`/assistants/${id}`),
  createAssistant: (body: {
    name: string
    description?: string
    engine: string
    model?: string | null
    schema: ExtractionSchema
  }) => request<Assistant>('/assistants', json(body)),
  updateAssistant: (id: string, body: Partial<{ name: string; description: string; engine: string; model: string | null; schema: ExtractionSchema }>) =>
    request<Assistant>(`/assistants/${id}`, json(body, 'PUT')),
  deleteAssistant: (id: string) => request<void>(`/assistants/${id}`, { method: 'DELETE' }),

  suggestSchema: (file: File, engine: string, model?: string | null) => {
    const form = new FormData()
    form.append('file', file)
    form.append('engine', engine)
    if (model) form.append('model', model)
    return request<ExtractionSchema>('/schema/suggest', { method: 'POST', body: form })
  },

  extract: (file: File, schema: ExtractionSchema, engine: string, model?: string | null) => {
    const form = new FormData()
    form.append('file', file)
    form.append('schema', JSON.stringify(schema))
    form.append('engine', engine)
    if (model) form.append('model', model)
    return request<ExtractionResult>('/extract', { method: 'POST', body: form })
  },

  startAssistantBulk: (assistantId: string, files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<{ job_id: string; total: number }>(`/assistants/${assistantId}/bulk`, {
      method: 'POST',
      body: form,
    })
  },
  bulkStatus: (jobId: string) => request<BulkReport>(`/bulk/${jobId}`),

  listResults: (assistantId: string, filter: 'all' | 'review' | 'ready') =>
    request<ResultRow[]>(`/assistants/${assistantId}/results?filter=${filter}`),

  exportUrl: (assistantId: string) => `/assistants/${assistantId}/export.xlsx`,
}
