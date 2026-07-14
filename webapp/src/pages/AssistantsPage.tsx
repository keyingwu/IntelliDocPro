import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { Assistant } from '../api/types'
import { t } from '../i18n'
import './assistants.css'

const CARD_HUES = [
  { bg: 'var(--teal-wash)', fg: 'var(--teal-deep)' },
  { bg: 'var(--purple-wash)', fg: 'var(--purple)' },
  { bg: 'var(--ok-wash)', fg: 'var(--ok)' },
  { bg: 'var(--amber-wash)', fg: 'var(--amber-deep)' },
]

function hueFor(id: string) {
  let h = 0
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 997
  return CARD_HUES[h % CARD_HUES.length]
}

function usd(n: number) {
  return `$${n.toFixed(n >= 1 ? 2 : 4)}`
}

function AssistantCard({ assistant, index }: { assistant: Assistant; index: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hue = hueFor(assistant.id)

  const remove = useMutation({
    mutationFn: () => api.deleteAssistant(assistant.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['assistants'] }),
  })

  return (
    <div
      className="assistant-card card rise"
      style={{ animationDelay: `${index * 45}ms` }}
      onClick={() => navigate(`/results/${assistant.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/results/${assistant.id}`)}
    >
      <div className="assistant-card-top">
        <span className="assistant-icon" style={{ background: hue.bg, color: hue.fg }}>
          <FileText size={19} />
        </span>
        <button
          className="btn-icon danger"
          title={t('common.delete')}
          onClick={(e) => {
            e.stopPropagation()
            if (window.confirm(t('assistants.delete.confirm'))) remove.mutate()
          }}
        >
          <Trash2 size={15} />
        </button>
      </div>
      <div className="assistant-name">{assistant.name}</div>
      <div className="assistant-desc">
        {assistant.description ||
          `${assistant.engine}${assistant.model ? ` · ${assistant.model}` : ''} · ${assistant.schema.fields.length} fields`}
      </div>
      <div className="assistant-stats">
        <span>
          <b>{assistant.doc_count}</b> {t('assistants.docs')}
        </span>
        {assistant.review_count > 0 && (
          <span className="stat-review">
            <b>{assistant.review_count}</b> {t('assistants.review')}
          </span>
        )}
        <span className="stat-cost">
          {usd(assistant.total_cost_usd)} {t('assistants.spent')}
        </span>
      </div>
    </div>
  )
}

export default function AssistantsPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['assistants'],
    queryFn: api.listAssistants,
  })

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('assistants.title')}</h1>
          <div className="sub">{t('assistants.subtitle')}</div>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/build')}>
          <Plus size={16} />
          {t('assistants.new')}
        </button>
      </div>

      {isLoading && <div className="muted">{t('common.loading')}</div>}
      {isError && (
        <div className="muted">
          {t('common.error')}{' '}
          <button className="linkish" onClick={() => refetch()}>
            {t('common.retry')}
          </button>
        </div>
      )}

      {data && data.length === 0 && (
        <div className="empty card rise">
          <div className="empty-title">{t('assistants.empty.title')}</div>
          <div className="empty-body">{t('assistants.empty.body')}</div>
          <button className="btn btn-primary" onClick={() => navigate('/build')}>
            <Plus size={16} />
            {t('assistants.new')}
          </button>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="assistant-grid">
          {data.map((a, i) => (
            <AssistantCard key={a.id} assistant={a} index={i} />
          ))}
        </div>
      )}
    </>
  )
}
