import { useMutation, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  FlaskConical,
  Loader2,
  Plus,
  Trash2,
  XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import type {
  BulkFileStatus,
  ExtractionResult,
  FieldSpec,
  FieldType,
  FieldValue,
} from '../api/types'
import PdfPreview, { type Highlight } from '../components/PdfPreview'
import UploadDropzone from '../components/UploadDropzone'
import { t } from '../i18n'
import './wizard.css'

const FIELD_TYPES: FieldType[] = ['text', 'number', 'date', 'amount', 'percent', 'enum']

const CONF_COLOR: Record<string, string> = {
  high: 'var(--ok-dot)',
  medium: 'var(--amber)',
  low: 'var(--bad)',
}

function EngineSelect({
  value,
  onChange,
}: {
  value: string
  onChange: (engine: string) => void
}) {
  const { data } = useQuery({ queryKey: ['health'], queryFn: api.health })
  const engines = data ? Object.entries(data.engines) : []
  return (
    <select className="input select" value={value} onChange={(e) => onChange(e.target.value)}>
      {engines.length === 0 && <option value={value}>{value}</option>}
      {engines.map(([name, configured]) => (
        <option key={name} value={name} disabled={!configured}>
          {name}
          {configured ? '' : ' (not configured)'}
        </option>
      ))}
    </select>
  )
}

// ---- step 2: field editor row ----

function FieldRow({
  field,
  extracted,
  onChange,
  onRemove,
  onHover,
}: {
  field: FieldSpec
  extracted: FieldValue | undefined
  onChange: (next: FieldSpec) => void
  onRemove: () => void
  onHover: (hovering: boolean) => void
}) {
  const cycleType = () => {
    const next = FIELD_TYPES[(FIELD_TYPES.indexOf(field.type) + 1) % FIELD_TYPES.length]
    onChange({ ...field, type: next, enum_values: next === 'enum' ? field.enum_values ?? [] : null })
  }
  return (
    <div
      className="field-row"
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <div className="field-row-main">
        <button
          className="type-chip"
          style={{
            color: `var(--type-${field.type})`,
            background: `var(--type-${field.type}-bg)`,
          }}
          onClick={cycleType}
          title="Click to change type"
        >
          {field.type}
        </button>
        <input
          className="input field-name"
          value={field.name}
          placeholder={t('fields.name.placeholder')}
          onChange={(e) => onChange({ ...field, name: e.target.value })}
        />
        <button className="btn-icon danger visible" onClick={onRemove} title={t('common.delete')}>
          <Trash2 size={15} />
        </button>
      </div>
      <input
        className="input field-hint"
        value={field.description ?? ''}
        placeholder={t('fields.description.placeholder')}
        onChange={(e) => onChange({ ...field, description: e.target.value || null })}
      />
      {field.type === 'enum' && (
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

// ---- step 3: bulk upload ----

const BULK_ICON: Record<BulkFileStatus, React.ReactNode> = {
  queued: <span className="queue-dot" />,
  running: <Loader2 size={15} className="spin" style={{ color: 'var(--teal)' }} />,
  done: <CheckCircle2 size={15} style={{ color: 'var(--ok-dot)' }} />,
  failed: <XCircle size={15} style={{ color: 'var(--bad)' }} />,
}

function BulkStep({ assistantId }: { assistantId: string }) {
  const navigate = useNavigate()
  const [picked, setPicked] = useState<File[]>([])
  const [jobId, setJobId] = useState<string | null>(null)

  const start = useMutation({
    mutationFn: () => api.startAssistantBulk(assistantId, picked),
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
        <button className="btn btn-primary" onClick={() => navigate(`/results/${assistantId}`)}>
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
  const { assistantId: routeId } = useParams()
  const [searchParams] = useSearchParams()

  const [step, setStep] = useState(routeId ? Number(searchParams.get('step') ?? 2) : 1)
  const [assistantId, setAssistantId] = useState<string | null>(routeId ?? null)
  const [name, setName] = useState('')
  const [engine, setEngine] = useState('claude')
  const [fields, setFields] = useState<FieldSpec[]>([])
  const [sampleFile, setSampleFile] = useState<File | null>(null)
  const [testResult, setTestResult] = useState<ExtractionResult | null>(null)
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [fallbackNote, setFallbackNote] = useState<string | null>(null)

  // edit mode: hydrate from the stored assistant
  const existing = useQuery({
    queryKey: ['assistant', routeId],
    queryFn: () => api.getAssistant(routeId!),
    enabled: !!routeId,
  })
  useEffect(() => {
    if (existing.data) {
      setName(existing.data.name)
      setEngine(existing.data.engine)
      setFields(existing.data.schema.fields)
    }
  }, [existing.data])

  const suggest = useMutation({
    mutationFn: async (file: File) => {
      const schema = await api.suggestSchema(file, engine)
      const assistant = await api.createAssistant({
        name: name.trim() || file.name.replace(/\.[^.]+$/, ''),
        engine,
        schema,
      })
      return assistant
    },
    onSuccess: (assistant) => {
      setAssistantId(assistant.id)
      setName(assistant.name)
      setFields(assistant.schema.fields)
      setStep(2)
    },
  })

  const skipManual = useMutation({
    mutationFn: () =>
      api.createAssistant({
        name: name.trim() || t('wizard.title.new'),
        engine,
        schema: { fields: [{ name: 'Field 1', type: 'text' }] },
      }),
    onSuccess: (assistant) => {
      setAssistantId(assistant.id)
      setName(assistant.name)
      setFields(assistant.schema.fields)
      setStep(2)
    },
  })

  const saveAndContinue = useMutation({
    mutationFn: () =>
      api.updateAssistant(assistantId!, { name, engine, schema: { fields } }),
    onSuccess: () => setStep(3),
  })

  const test = useMutation({
    mutationFn: () => api.extract(sampleFile!, { fields }, engine),
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
    const extracted = extractedByField.get(field.name)
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
    new Set(fields.map((f) => f.name.trim())).size === fields.length

  const steps = [t('wizard.step.sample'), t('wizard.step.fields'), t('wizard.step.bulk')]

  return (
    <>
      <div className="page-head">
        <div>
          <button className="back-link" onClick={() => navigate('/')}>
            <ArrowLeft size={14} />
            {t('nav.assistants')}
          </button>
          <h1>
            <input
              className="name-input"
              value={name}
              placeholder={t('wizard.name.placeholder')}
              onChange={(e) => setName(e.target.value)}
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
          <div className="engine-row">
            <label>{t('wizard.engine')}</label>
            <EngineSelect value={engine} onChange={setEngine} />
          </div>
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
                setSampleFile(files[0])
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
              <span className="muted">{fields.length}</span>
            </div>
            <div className="fields-list">
              {fields.map((field, i) => (
                <FieldRow
                  key={i}
                  field={field}
                  extracted={extractedByField.get(field.name)}
                  onChange={(next) => setFields(fields.map((f, j) => (j === i ? next : f)))}
                  onRemove={() => setFields(fields.filter((_, j) => j !== i))}
                  onHover={(hovering) => hoverField(field, hovering)}
                />
              ))}
            </div>
            <button
              className="btn btn-ghost add-field"
              onClick={() => setFields([...fields, { name: '', type: 'text' }])}
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
                className="btn btn-primary"
                disabled={!fieldsValid || saveAndContinue.isPending}
                onClick={() => saveAndContinue.mutate()}
              >
                {t('fields.continue')}
                <ArrowRight size={16} />
              </button>
            </div>
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
              <div className="preview-empty">{t('fields.preview.empty')}</div>
            )}
          </div>
        </div>
      )}

      {step === 3 && assistantId && <BulkStep assistantId={assistantId} />}
    </>
  )
}
