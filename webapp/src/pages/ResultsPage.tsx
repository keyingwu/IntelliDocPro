import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, ExternalLink, FilePlus2, Loader2, Settings2, X } from 'lucide-react'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { FieldSpec, FieldValue, ResultRow } from '../api/types'
import PdfPreview, { type Highlight } from '../components/PdfPreview'
import { t } from '../i18n'
import './results.css'

type Filter = 'all' | 'review' | 'ready'

const CONF_COLOR: Record<string, string> = {
  high: 'var(--ok-dot)',
  medium: 'var(--amber)',
  low: 'var(--bad)',
}

function StatusPill({ row }: { row: ResultRow }) {
  if (row.status === 'failed')
    return <span className="pill pill-failed">{t('results.status.failed')}</span>
  if (row.needs_review)
    return <span className="pill pill-review">{t('results.status.review')}</span>
  return <span className="pill pill-ready">{t('results.status.ready')}</span>
}

function Drawer({
  row,
  fieldByKey,
  onClose,
}: {
  row: ResultRow
  fieldByKey: Map<string, FieldSpec>
  onClose: () => void
}) {
  const [highlight, setHighlight] = useState<Highlight | null>(null)
  const [fallbackNote, setFallbackNote] = useState<string | null>(null)

  const document = useQuery({
    queryKey: ['document', row.document_id],
    queryFn: () => api.fetchDocument(row.document_id!),
    enabled: row.document_id !== null,
    staleTime: Infinity,
  })
  const withPreview = row.document_id !== null

  const hoverValue = (v: FieldValue, hovering: boolean) => {
    if (!withPreview) return
    if (!hovering) {
      setHighlight(null)
      setFallbackNote(null)
      return
    }
    setHighlight({
      page: v.source?.page,
      rawText: v.raw_text,
      location: v.source?.location,
    })
    if (v.source?.location) {
      setFallbackNote(
        t('fields.source.fallback', {
          page: v.source?.page ?? 1,
          location: v.source.location,
        }),
      )
    }
  }

  const fields = (
    <div className="drawer-fields">
      {row.values.map((v: FieldValue) => {
        const spec = fieldByKey.get(v.field)
        return (
        <div
          key={v.field}
          className={`drawer-field${v.needs_review ? ' flagged' : ''}`}
          onMouseEnter={() => hoverValue(v, true)}
          onMouseLeave={() => hoverValue(v, false)}
        >
          <div className="drawer-field-name">
            {spec?.name ?? v.field}
            <code className="drawer-field-key">{spec?.key ?? v.field}</code>
          </div>
          {spec?.description && <div className="drawer-field-desc">{spec.description}</div>}
          <div className="drawer-field-value">
            {v.value ?? '—'}
            {v.currency ? ` ${v.currency}` : ''}
          </div>
          <dl className="drawer-meta">
            {v.raw_text && (
              <>
                <dt>{t('results.drawer.raw')}</dt>
                <dd>“{v.raw_text}”</dd>
              </>
            )}
            {v.source && (v.source.page || v.source.location) && (
              <>
                <dt>{t('results.drawer.source')}</dt>
                <dd>
                  {v.source.page ? t('results.drawer.page', { page: v.source.page }) : ''}
                  {v.source.page && v.source.location ? ' · ' : ''}
                  {v.source.location ?? ''}
                </dd>
              </>
            )}
            <dt>{t('results.drawer.confidence')}</dt>
            <dd>
              <span className="conf-dot" style={{ background: CONF_COLOR[v.confidence] }} />{' '}
              {v.confidence}
            </dd>
          </dl>
        </div>
        )
      })}
    </div>
  )

  return (
    <aside className={`drawer card${withPreview ? ' review' : ''}`}>
      <div className="drawer-head">
        <div>
          <div className="drawer-title">{row.filename}</div>
          <StatusPill row={row} />
          {row.document_id && (
            <a
              className="doc-link"
              href={api.documentUrl(row.document_id)}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={13} />
              {t('results.viewOriginal')}
            </a>
          )}
        </div>
        <button className="btn-icon visible" onClick={onClose}>
          <X size={17} />
        </button>
      </div>
      {row.error && <div className="error-note">{row.error}</div>}
      {withPreview ? (
        <div className="review-body">
          <div className="review-pdf">
            {fallbackNote && <div className="review-banner">{fallbackNote}</div>}
            {document.data ? (
              <PdfPreview file={document.data} highlight={highlight} />
            ) : (
              <div className="review-doc-loading muted">
                {document.isError ? t('results.docUnavailable') : (
                  <>
                    <Loader2 size={16} className="spin" /> {t('common.loading')}
                  </>
                )}
              </div>
            )}
          </div>
          <div className="review-fields">{fields}</div>
        </div>
      ) : (
        fields
      )}
    </aside>
  )
}

export default function ResultsPage() {
  const { agentId } = useParams()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [selected, setSelected] = useState<ResultRow | null>(null)

  const agent = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => api.getAgent(agentId!),
  })
  const results = useQuery({
    queryKey: ['results', agentId, filter],
    queryFn: () => api.listResults(agentId!, filter),
  })

  if (!agent.data) return <div className="muted">{t('common.loading')}</div>
  const a = agent.data
  const schemaFields = a.schema.fields
  const fieldByKey = new Map<string, FieldSpec>()
  for (const f of schemaFields) {
    fieldByKey.set(f.key, f)
    fieldByKey.set(f.name, f) // results predating field keys stored the name
  }
  const rows = results.data ?? []

  const filters: { key: Filter; label: string; count?: number }[] = [
    { key: 'all', label: t('results.filter.all'), count: a.doc_count + a.failed_count },
    { key: 'review', label: t('results.filter.review'), count: a.review_count },
    { key: 'ready', label: t('results.filter.ready') },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <button className="back-link" onClick={() => navigate('/')}>
            <ArrowLeft size={14} />
            {t('nav.agents')}
          </button>
          <h1>{a.name}</h1>
          <div className="sub">
            {a.engine}
            {a.model ? ` · ${a.model}` : ''} · {t('results.docs', { count: a.doc_count })} ·{' '}
            {t('results.cost', { cost: `$${a.total_cost_usd.toFixed(4)}` })}
          </div>
        </div>
        <div className="head-actions">
          <button className="btn btn-ghost" onClick={() => navigate(`/build/${a.id}?step=2`)}>
            <Settings2 size={15} />
            {t('results.editFields')}
          </button>
          <button className="btn btn-ghost" onClick={() => navigate(`/build/${a.id}?step=3`)}>
            <FilePlus2 size={15} />
            {t('results.addDocs')}
          </button>
          <a className="btn btn-primary" href={api.exportUrl(a.id)}>
            <Download size={15} />
            {t('results.export')}
          </a>
        </div>
      </div>

      <div className="filter-row">
        {filters.map((f) => (
          <button
            key={f.key}
            className={`filter-chip${filter === f.key ? ' active' : ''}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
            {f.count !== undefined && <span className="filter-count">{f.count}</span>}
          </button>
        ))}
      </div>

      {rows.length === 0 && <div className="muted empty-note">{t('results.empty')}</div>}

      {rows.length > 0 && (
        <div className="table-wrap card rise">
          <table className="results-table">
            <thead>
              <tr>
                <th className="col-doc">Document</th>
                {schemaFields.map((f) => (
                  <th key={f.key} title={f.description ?? undefined}>
                    {f.name}
                    <span className="th-key">{f.key}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const byField = new Map(row.values.map((v) => [v.field, v]))
                return (
                  <tr key={row.id} onClick={() => setSelected(row)}>
                    <td className="col-doc">
                      <span className="doc-name">{row.filename}</span>
                      <StatusPill row={row} />
                    </td>
                    {schemaFields.map((f) => {
                      // results predating field keys stored the name in `field`
                      const v = byField.get(f.key) ?? byField.get(f.name)
                      const flagged = v?.needs_review
                      return (
                        <td key={f.key} className={flagged ? 'flagged' : ''}>
                          {v?.value ?? '—'}
                          {v?.currency ? ` ${v.currency}` : ''}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <Drawer row={selected} fieldByKey={fieldByKey} onClose={() => setSelected(null)} />
      )}
    </>
  )
}
