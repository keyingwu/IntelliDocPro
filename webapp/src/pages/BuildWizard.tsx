import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  FileCheck2,
  FlaskConical,
  Loader2,
  Plus,
  Save,
  Send,
  Sparkles,
  Trash2,
  Undo2,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useReducer, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type {
  BulkFileStatus,
  ExtractionResult,
  FieldSpec,
  FieldType,
  FieldValue,
  SchemaChatMessage,
} from '../api/types'
import PdfPreview, { type Highlight } from '../components/PdfPreview'
import UploadDropzone from '../components/UploadDropzone'
import { t } from '../i18n'
import { FIELD_KEY_RE, fieldKeyFromName } from '../lib/fieldKey'
import {
  initialSchemaRefineState,
  sampleFileKey,
  schemaRefineReducer,
  type RefineChatEntry,
} from './schemaRefineState'
import './wizard.css'

const FIELD_TYPES: FieldType[] = ['text', 'number', 'date', 'amount', 'percent', 'enum']

const CONF_COLOR: Record<string, string> = {
  high: 'var(--ok-dot)',
  medium: 'var(--amber)',
  low: 'var(--bad)',
}

function EngineModelPicker({
  engine,
  model,
  onEngine,
  onModel,
}: {
  engine: string
  model: string
  onEngine: (engine: string) => void
  onModel: (model: string) => void
}) {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const catalog = useQuery({ queryKey: ['models'], queryFn: api.models })
  const engines = health.data ? Object.entries(health.data.engines) : []
  const info = catalog.data?.engines[engine]
  const deploymentStyle = (info?.models.length ?? 0) === 0 // Azure: free-text deployment

  return (
    <div className="engine-row">
      <label>{t('wizard.engine')}</label>
      <select
        className="input select"
        value={engine}
        onChange={(e) => {
          onEngine(e.target.value)
          onModel('')
        }}
      >
        {engines.length === 0 && <option value={engine}>{engine}</option>}
        {engines.map(([name, configured]) => (
          <option key={name} value={name} disabled={!configured}>
            {name}
            {configured ? '' : ' (not configured)'}
          </option>
        ))}
      </select>
      <label>{t('wizard.model')}</label>
      {deploymentStyle ? (
        <input
          className="input model-input"
          value={model}
          placeholder={info?.default || t('wizard.model.deployment')}
          onChange={(e) => onModel(e.target.value)}
        />
      ) : (
        <select
          className="input select model-input"
          value={model}
          onChange={(e) => onModel(e.target.value)}
        >
          <option value="">{t('wizard.model.default', { model: info?.default ?? '…' })}</option>
          {info?.models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}
              {m.input_per_mtok != null ? `  —  $${m.input_per_mtok} / $${m.output_per_mtok} per 1M tok` : ''}
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

// ---- step 2: field editor row ----

function FieldRow({
  field,
  extracted,
  keyLocked,
  onChange,
  onRemove,
  onHover,
}: {
  field: FieldSpec
  extracted: FieldValue | undefined
  /** Persisted keys must survive display renames: results and exports key on them. */
  keyLocked: boolean
  onChange: (next: FieldSpec) => void
  onRemove: () => void
  onHover: (hovering: boolean) => void
}) {
  return (
    <div
      className="field-row"
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <div className="field-row-main">
        <select
          className="type-select"
          style={{
            color: `var(--type-${field.type})`,
            background: `var(--type-${field.type}-bg)`,
          }}
          value={field.type}
          aria-label={t('fields.type.label')}
          onChange={(event) => {
            const next = event.target.value as FieldType
            onChange({
              ...field,
              type: next,
              enum_values: next === 'enum' ? field.enum_values ?? [] : null,
            })
          }}
        >
          {FIELD_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <input
          className="input field-name"
          value={field.name}
          placeholder={t('fields.name.placeholder')}
          onChange={(e) => {
            const name = e.target.value
            // The key follows the typed name only while the field is unsaved
            // and the key has not been set to something else.
            const follows = !keyLocked && field.key === fieldKeyFromName(field.name)
            onChange({ ...field, name, key: follows ? fieldKeyFromName(name) : field.key })
          }}
        />
        <button className="btn-icon danger visible" onClick={onRemove} title={t('common.delete')}>
          <Trash2 size={15} />
        </button>
      </div>
      <label className="field-sub" title={t('fields.key.label')}>
        <span className="field-sub-label">{t('fields.key.tag')}</span>
        <input
          className="input field-key"
          value={field.key}
          placeholder={t('fields.key.placeholder')}
          onChange={(e) => onChange({ ...field, key: e.target.value.toLowerCase() })}
        />
      </label>
      <label className="field-sub">
        <span className="field-sub-label">{t('fields.description.tag')}</span>
        <input
          className="input field-hint"
          value={field.description ?? ''}
          placeholder={t('fields.description.placeholder')}
          onChange={(e) => onChange({ ...field, description: e.target.value || null })}
        />
      </label>
      {field.type === 'enum' && (
        <label className="field-sub">
          <span className="field-sub-label">{t('fields.enum.tag')}</span>
          <input
            className="input field-hint"
            value={(field.enum_values ?? []).join(', ')}
            placeholder={t('fields.enum.placeholder')}
            onChange={(e) =>
              onChange({
                ...field,
                enum_values: e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
      )}
      {extracted && (
        <div className="field-extract">
          <span className="conf-dot" style={{ background: CONF_COLOR[extracted.confidence] }} />
          <span className="field-extract-value">
            {extracted.value ?? '—'}
            {extracted.currency ? ` ${extracted.currency}` : ''}
          </span>
          {extracted.source?.page && (
            <span className="field-extract-src">
              p.{extracted.source.page}
              {extracted.source.location ? ` · ${extracted.source.location}` : ''}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

interface RefineRequest {
  requestId: string
  instruction: string
  sampleKey: string
  file: File
  fields: FieldSpec[]
  history: SchemaChatMessage[]
  engine: string
  model: string | null
}

function SchemaRefinePanel({
  messages,
  instruction,
  sampleFile,
  isPending,
  canUndo,
  onInstruction,
  onSend,
  onUndo,
  onAddManually,
}: {
  messages: RefineChatEntry[]
  instruction: string
  sampleFile: File | null
  isPending: boolean
  canUndo: boolean
  onInstruction: (value: string) => void
  onSend: () => void
  onUndo: () => void
  onAddManually: (request: string) => void
}) {
  const canSend = sampleFile !== null && instruction.trim().length > 0 && !isPending

  return (
    <section className={`refine-card${sampleFile ? '' : ' locked'}`}>
      <div className="refine-head">
        <span className="refine-mark">
          <Sparkles size={15} />
        </span>
        <div>
          <h3>{t('fields.ai.title')}</h3>
          <p>{t('fields.ai.subtitle')}</p>
        </div>
        {sampleFile && (
          <span className="sample-chip" title={sampleFile.name}>
            <FileCheck2 size={13} />
            {sampleFile.name}
          </span>
        )}
      </div>

      <div className={`refine-thread${messages.length === 0 ? ' empty' : ''}`} aria-live="polite">
        {messages.length === 0 ? (
          <div className="refine-intro">
            {sampleFile ? t('fields.ai.intro') : t('fields.ai.needsSample')}
          </div>
        ) : (
          messages.map((message) => (
            <div key={message.id} className={`refine-message ${message.role}`}>
              <div className="refine-message-label">
                {message.role === 'user'
                  ? t('fields.ai.you')
                  : message.role === 'assistant'
                    ? t('fields.ai.assistant')
                    : t('fields.ai.notice')}
              </div>
              <div>{message.content}</div>
              {message.result && message.result.applied.length > 0 && (
                <div className="refine-applied">
                  {message.result.applied.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              )}
              {message.result && message.result.rejected.length > 0 && (
                <div className="refine-rejections">
                  {message.result.rejected.map((item, index) => (
                    <div key={`${item.request}-${index}`} className="refine-rejection">
                      <div>
                        <strong>{item.request}</strong>
                        <span>{item.reason}</span>
                      </div>
                      <button
                        type="button"
                        className="btn btn-ghost manual-shortcut"
                        onClick={() => onAddManually(item.request)}
                      >
                        <Plus size={13} />
                        {t('fields.ai.addManually')}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
        {isPending && (
          <div className="refine-thinking">
            <Loader2 size={14} className="spin" />
            {t('fields.ai.thinking')}
          </div>
        )}
      </div>

      {canUndo && (
        <button type="button" className="refine-undo" onClick={onUndo}>
          <Undo2 size={14} />
          {t('fields.ai.undo')}
        </button>
      )}

      <form
        className="refine-composer"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSend) onSend()
        }}
      >
        <textarea
          className="input"
          rows={2}
          maxLength={4000}
          value={instruction}
          disabled={sampleFile === null || isPending}
          placeholder={
            sampleFile ? t('fields.ai.placeholder') : t('fields.ai.placeholderLocked')
          }
          onChange={(event) => onInstruction(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              if (canSend) onSend()
            }
          }}
        />
        <button
          type="submit"
          className="refine-send"
          disabled={!canSend}
          aria-label={t('fields.ai.send')}
        >
          {isPending ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
        </button>
      </form>
    </section>
  )
}

// ---- step 3: bulk upload ----

const BULK_ICON: Record<BulkFileStatus, React.ReactNode> = {
  queued: <span className="queue-dot" />,
  running: <Loader2 size={15} className="spin" style={{ color: 'var(--teal)' }} />,
  done: <CheckCircle2 size={15} style={{ color: 'var(--ok-dot)' }} />,
  failed: <XCircle size={15} style={{ color: 'var(--bad)' }} />,
}

function BulkStep({ agentId }: { agentId: string }) {
  const navigate = useNavigate()
  const [picked, setPicked] = useState<File[]>([])
  const [jobId, setJobId] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: () => api.startAgentBulk(agentId, picked),
    onSuccess: (r) => setJobId(r.job_id),
  })

  const { data: report } = useQuery({
    queryKey: ['bulk', jobId],
    queryFn: () => api.bulkStatus(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => (query.state.data?.status === 'done' ? false : 1000),
  })

  if (!jobId) {
    return (
      <div className="bulk-stage rise">
        <UploadDropzone
          multiple
          title={t('bulk.drop.title')}
          body={t('bulk.drop.body')}
          buttonLabel={t('bulk.drop.button')}
          onFiles={(files) => setPicked((prev) => [...prev, ...files])}
        />
        {picked.length > 0 && (
          <>
            <div className="picked-list card">
              {picked.map((f, i) => (
                <div key={`${f.name}-${i}`} className="picked-row">
                  <span>{f.name}</span>
                  <button
                    className="btn-icon danger visible"
                    onClick={() => setPicked(picked.filter((_, j) => j !== i))}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            <button className="btn btn-primary" disabled={start.isPending} onClick={() => start.mutate()}>
              {start.isPending ? <Loader2 size={16} className="spin" /> : <ArrowRight size={16} />}
              {t('bulk.start', { count: picked.length })}
            </button>
          </>
        )}
      </div>
    )
  }

  const done = report?.status === 'done'
  const progress = report ? (report.completed + report.failed) / Math.max(report.total, 1) : 0

  return (
    <div className="bulk-stage rise">
      <div className="bulk-head">
        <h3>{done ? t('bulk.done') : t('bulk.running')}</h3>
        <span className="bulk-cost">
          {t('bulk.cost')}: <b>${(report?.total_cost_usd ?? 0).toFixed(4)}</b>
        </span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progress * 100}%` }} />
      </div>
      <div className="bulk-list card">
        {report?.entries.map((entry) => (
          <div key={entry.filename} className="bulk-row">
            <span className="bulk-row-status">{BULK_ICON[entry.status]}</span>
            <span className="bulk-row-name">{entry.filename}</span>
            {entry.needs_review && (
              <span className="pill review-pill">
                <CircleAlert size={12} />
                {t('results.status.review')}
              </span>
            )}
            <span className="bulk-row-meta">
              {entry.status === 'failed'
                ? entry.error
                : entry.cost
                  ? `$${entry.cost.total_cost.toFixed(4)} · ${entry.duration_s}s`
                  : t(`bulk.status.${entry.status}`)}
            </span>
          </div>
        ))}
      </div>
      {done && (
        <button className="btn btn-primary" onClick={() => navigate(`/results/${agentId}`)}>
          {t('bulk.toResults')}
          <ArrowRight size={16} />
        </button>
      )}
    </div>
  )
}

// ---- the wizard shell ----

export default function BuildWizard() {
  const navigate = useNavigate()
  const { agentId: routeId } = useParams()
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState(routeId ? Number(searchParams.get('step') ?? 2) : 1)
  const [agentId, setAgentId] = useState<string | null>(routeId ?? null)
  const [name, setName] = useState('')
  const [engine, setEngine] = useState('openai')
  const [model, setModel] = useState('')
  const [refineState, dispatchRefine] = useReducer(
    schemaRefineReducer,
    undefined,
    () => initialSchemaRefineState(),
  )
  const [instruction, setInstruction] = useState('')
  const [sampleFile, setSampleFile] = useState<File | null>(null)
  const [testResult, setTestResult] = useState<ExtractionResult | null>(null)
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [fallbackNote, setFallbackNote] = useState<string | null>(null)
  const hydratedAgentId = useRef<string | null>(null)
  const requestCounter = useRef(0)
  const refineStateRef = useRef(refineState)
  const fields = refineState.fields

  useEffect(() => {
    refineStateRef.current = refineState
  }, [refineState])

  const clearTestContext = () => {
    setTestResult(null)
    setHighlight(null)
    setFallbackNote(null)
  }

  const applyManualFields = (nextFields: FieldSpec[]) => {
    saveSchema.reset()
    dispatchRefine({ type: 'manual-change', fields: nextFields })
    clearTestContext()
  }

  const handleSampleFile = (file: File) => {
    setSampleFile(file)
    dispatchRefine({ type: 'sample-replaced' })
    setInstruction('')
    clearTestContext()
  }

  // edit mode: hydrate from the stored Document Agent
  const [persistedKeys, setPersistedKeys] = useState<Set<string>>(new Set())
  const lockKeys = (locked: FieldSpec[]) =>
    setPersistedKeys(new Set(locked.map((f) => f.key).filter(Boolean)))

  const existing = useQuery({
    queryKey: ['agent', routeId],
    queryFn: () => api.getAgent(routeId!),
    enabled: !!routeId,
  })
  useEffect(() => {
    if (existing.data && hydratedAgentId.current !== existing.data.id) {
      hydratedAgentId.current = existing.data.id
      setName(existing.data.name)
      setEngine(existing.data.engine)
      setModel(existing.data.model ?? '')
      dispatchRefine({ type: 'hydrate', fields: existing.data.schema.fields })
      lockKeys(existing.data.schema.fields)
      if (existing.data.sample_document_id) {
        api
          .fetchDocument(existing.data.sample_document_id)
          .then((file) => setSampleFile((prev) => prev ?? file))
          .catch(() => {}) // preview stays empty; the user can re-upload
      }
    }
  }, [existing.data])

  const suggest = useMutation({
    mutationFn: async (file: File) => {
      const schema = await api.suggestSchema(file, engine, model || null)
      const agent = await api.createAgent({
        name: name.trim() || file.name.replace(/\.[^.]+$/, ''),
        engine,
        model: model || null,
        schema,
      })
      // best-effort: a failed sample upload must not break agent creation
      await api.uploadSample(agent.id, file).catch(() => {})
      return agent
    },
    onSuccess: (agent) => {
      setAgentId(agent.id)
      setName(agent.name)
      dispatchRefine({ type: 'hydrate', fields: agent.schema.fields })
      lockKeys(agent.schema.fields)
      setStep(2)
    },
  })

  const skipManual = useMutation({
    mutationFn: () =>
      api.createAgent({
        name: name.trim() || t('wizard.title.new'),
        engine,
        model: model || null,
        schema: { fields: [{ name: 'Field 1', key: 'field_1', type: 'text' }] },
      }),
    onSuccess: (agent) => {
      setAgentId(agent.id)
      setName(agent.name)
      dispatchRefine({ type: 'hydrate', fields: agent.schema.fields })
      lockKeys(agent.schema.fields)
      setStep(2)
    },
  })

  const updateAgent = () =>
    api.updateAgent(agentId!, {
      name,
      engine,
      model: model || null,
      schema: { fields },
    })

  const saveSchema = useMutation({
    mutationFn: updateAgent,
    onSuccess: () => lockKeys(fields),
  })

  const saveAndContinue = useMutation({
    mutationFn: updateAgent,
    onSuccess: () => {
      lockKeys(fields)
      setStep(3)
    },
  })

  const refine = useMutation({
    mutationFn: (request: RefineRequest) =>
      api.refineSchema(
        request.file,
        { fields: request.fields },
        request.instruction,
        request.engine,
        request.model,
        request.history,
      ),
    onSuccess: (result, request) => {
      const current = refineStateRef.current
      const applies =
        current.pending?.id === request.requestId &&
        current.pending.revision === current.revision &&
        current.pending.sampleKey === request.sampleKey
      dispatchRefine({
        type: 'refine-succeeded',
        requestId: request.requestId,
        sampleKey: request.sampleKey,
        result,
      })
      if (applies && result.changed) {
        saveSchema.reset()
        clearTestContext()
      }
    },
    onError: (error, request) => {
      dispatchRefine({
        type: 'refine-failed',
        requestId: request.requestId,
        message: error instanceof Error ? error.message : String(error),
      })
    },
  })

  const sendRefine = () => {
    const cleanInstruction = instruction.trim()
    if (!sampleFile || !cleanInstruction || refine.isPending) return
    const requestId = `refine-${Date.now()}-${++requestCounter.current}`
    const sampleKey = sampleFileKey(sampleFile)
    const request: RefineRequest = {
      requestId,
      instruction: cleanInstruction,
      sampleKey,
      file: sampleFile,
      fields,
      history: refineState.history,
      engine,
      model: model || null,
    }
    dispatchRefine({
      type: 'refine-started',
      requestId,
      instruction: cleanInstruction,
      sampleKey,
    })
    setInstruction('')
    refine.mutate(request)
  }

  const test = useMutation({
    mutationFn: () => api.extract(sampleFile!, { fields }, engine, model || null),
    onSuccess: (result) => setTestResult(result),
  })

  const extractedByField = useMemo(() => {
    const map = new Map<string, FieldValue>()
    for (const v of testResult?.values ?? []) map.set(v.field, v)
    return map
  }, [testResult])

  const hoverField = (field: FieldSpec, hovering: boolean) => {
    if (!hovering) {
      setHighlight(null)
      setFallbackNote(null)
      return
    }
    const extracted = extractedByField.get(field.key) ?? extractedByField.get(field.name)
    if (!extracted) return
    setHighlight({
      page: extracted.source?.page,
      rawText: extracted.raw_text,
      location: extracted.source?.location,
    })
    if (extracted.source?.location) {
      setFallbackNote(
        t('fields.source.fallback', {
          page: extracted.source?.page ?? 1,
          location: extracted.source.location,
        }),
      )
    }
  }

  const fieldsValid =
    fields.length > 0 &&
    fields.every((f) => f.name.trim().length > 0) &&
    fields.every((f) => FIELD_KEY_RE.test(f.key)) &&
    fields.every((f) => f.type !== 'enum' || (f.enum_values?.length ?? 0) > 0) &&
    new Set(fields.map((f) => f.name.trim())).size === fields.length &&
    new Set(fields.map((f) => f.key)).size === fields.length

  const steps = [t('wizard.step.sample'), t('wizard.step.fields'), t('wizard.step.bulk')]

  return (
    <>
      <div className="page-head">
        <div>
          <button className="back-link" onClick={() => navigate('/')}>
            <ArrowLeft size={14} />
            {t('nav.agents')}
          </button>
          <h1>
            <input
              className="name-input"
              value={name}
              placeholder={t('wizard.name.placeholder')}
              onChange={(e) => {
                saveSchema.reset()
                setName(e.target.value)
              }}
            />
          </h1>
        </div>
        <div className="stepper">
          {steps.map((label, i) => {
            const n = i + 1
            const state = step === n ? 'current' : step > n ? 'done' : 'todo'
            return (
              <span key={label} className={`step ${state}`}>
                <span className="step-circle">{state === 'done' ? '✓' : n}</span>
                {label}
                {i < steps.length - 1 && <span className="step-sep" />}
              </span>
            )
          })}
        </div>
      </div>

      {step === 1 && (
        <div className="sample-stage rise">
          <EngineModelPicker
            engine={engine}
            model={model}
            onEngine={(nextEngine) => {
              saveSchema.reset()
              setEngine(nextEngine)
            }}
            onModel={(nextModel) => {
              saveSchema.reset()
              setModel(nextModel)
            }}
          />
          {suggest.isPending ? (
            <div className="analyzing card">
              <Loader2 size={22} className="spin" style={{ color: 'var(--teal)' }} />
              {t('sample.analyzing')}
            </div>
          ) : (
            <UploadDropzone
              title={t('sample.drop.title')}
              body={t('sample.drop.body')}
              buttonLabel={t('sample.drop.button')}
              onFiles={(files) => {
                handleSampleFile(files[0])
                suggest.mutate(files[0])
              }}
            >
              <button className="linkish skip-link" onClick={() => skipManual.mutate()}>
                {t('sample.skip')}
              </button>
            </UploadDropzone>
          )}
          {suggest.isError && <div className="error-note">{String(suggest.error)}</div>}
        </div>
      )}

      {step === 2 && (
        <div className="fields-stage rise">
          <div className="fields-pane">
            <div className="fields-head">
              <h3>{t('fields.title')}</h3>
              <span className="fields-count">{fields.length}</span>
            </div>
            <EngineModelPicker
              engine={engine}
              model={model}
              onEngine={(nextEngine) => {
                saveSchema.reset()
                setEngine(nextEngine)
              }}
              onModel={(nextModel) => {
                saveSchema.reset()
                setModel(nextModel)
              }}
            />
            <SchemaRefinePanel
              messages={refineState.messages}
              instruction={instruction}
              sampleFile={sampleFile}
              isPending={refine.isPending}
              canUndo={refineState.undoSnapshot !== null}
              onInstruction={setInstruction}
              onSend={sendRefine}
              onUndo={() => {
                saveSchema.reset()
                dispatchRefine({ type: 'undo' })
                clearTestContext()
              }}
              onAddManually={(request) => {
                const requestedName = request.trim()
                const nameAvailable = !fields.some((field) => field.name === requestedName)
                const name = nameAvailable && requestedName.length <= 80 ? requestedName : ''
                const derived = fieldKeyFromName(name)
                applyManualFields([
                  ...fields,
                  {
                    name,
                    key: fields.some((field) => field.key === derived) ? '' : derived,
                    type: 'text',
                  },
                ])
              }}
            />
            <div className="fields-list">
              {fields.map((field, i) => (
                <FieldRow
                  key={i}
                  field={field}
                  extracted={extractedByField.get(field.key) ?? extractedByField.get(field.name)}
                  keyLocked={persistedKeys.has(field.key)}
                  onChange={(next) =>
                    applyManualFields(fields.map((f, j) => (j === i ? next : f)))
                  }
                  onRemove={() => applyManualFields(fields.filter((_, j) => j !== i))}
                  onHover={(hovering) => hoverField(field, hovering)}
                />
              ))}
            </div>
            <button
              className="btn btn-ghost add-field"
              onClick={() => applyManualFields([...fields, { name: '', key: '', type: 'text' }])}
            >
              <Plus size={15} />
              {t('fields.add')}
            </button>
            <div className="fields-actions">
              {sampleFile && (
                <button
                  className="btn btn-ghost"
                  disabled={test.isPending || !fieldsValid}
                  onClick={() => test.mutate()}
                >
                  {test.isPending ? <Loader2 size={15} className="spin" /> : <FlaskConical size={15} />}
                  {test.isPending ? t('fields.testing') : t('fields.test')}
                </button>
              )}
              <button
                className={`btn btn-ghost schema-save${saveSchema.isSuccess ? ' saved' : ''}`}
                disabled={!fieldsValid || saveSchema.isPending || saveAndContinue.isPending}
                onClick={() => saveSchema.mutate()}
              >
                {saveSchema.isPending ? (
                  <Loader2 size={15} className="spin" />
                ) : saveSchema.isSuccess ? (
                  <CheckCircle2 size={15} />
                ) : (
                  <Save size={15} />
                )}
                {saveSchema.isPending
                  ? t('fields.saving')
                  : saveSchema.isSuccess
                    ? t('fields.saved')
                    : t('fields.save')}
              </button>
              <button
                className="btn btn-primary"
                disabled={!fieldsValid || saveAndContinue.isPending || saveSchema.isPending}
                onClick={() => saveAndContinue.mutate()}
              >
                {t('fields.continue')}
                <ArrowRight size={16} />
              </button>
            </div>
            {saveSchema.isError ? (
              <div className="error-note fields-save-error" role="alert">
                {t('fields.save.error', { message: String(saveSchema.error) })}
              </div>
            ) : null}
          </div>
          <div className="preview-pane card">
            {sampleFile ? (
              <>
                {fallbackNote && <div className="preview-banner">{fallbackNote}</div>}
                {testResult && !fallbackNote && (
                  <div className="preview-banner subtle">{t('fields.preview.hint')}</div>
                )}
                <PdfPreview file={sampleFile} highlight={highlight} />
              </>
            ) : (
              <div className="preview-upload">
                <UploadDropzone
                  compact
                  title={t('fields.sample.title')}
                  body={t('fields.sample.body')}
                  buttonLabel={t('fields.sample.button')}
                  onFiles={(files) => {
                    handleSampleFile(files[0])
                    if (agentId) api.uploadSample(agentId, files[0]).catch(() => {})
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {step === 3 && agentId && <BulkStep agentId={agentId} />}
    </>
  )
}
