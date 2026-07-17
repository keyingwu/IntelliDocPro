import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Plus, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { DocumentAgent } from '../api/types'
import { t } from '../i18n'
import './agents.css'

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

function AgentCard({ agent, index }: { agent: DocumentAgent; index: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hue = hueFor(agent.id)

  const remove = useMutation({
    mutationFn: () => api.deleteAgent(agent.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['agents'] }),
  })

  return (
    <div
      className="agent-card card rise"
      style={{ animationDelay: `${index * 45}ms` }}
      onClick={() => navigate(`/results/${agent.id}`)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && navigate(`/results/${agent.id}`)}
    >
      <div className="agent-card-top">
        <span className="agent-icon" style={{ background: hue.bg, color: hue.fg }}>
          <FileText size={19} />
        </span>
        <button
          className="btn-icon danger"
          title={t('common.delete')}
          onClick={(e) => {
            e.stopPropagation()
            if (window.confirm(t('agents.delete.confirm'))) remove.mutate()
          }}
        >
          <Trash2 size={15} />
        </button>
      </div>
      <div className="agent-name">{agent.name}</div>
      <div className="agent-desc">
        {agent.description ||
          `${agent.engine}${agent.model ? ` · ${agent.model}` : ''} · ${agent.schema.fields.length} fields`}
      </div>
      <div className="agent-stats">
        <span>
          <b>{agent.doc_count}</b> {t('agents.docs')}
        </span>
        {agent.review_count > 0 && (
          <span className="stat-review">
            <b>{agent.review_count}</b> {t('agents.review')}
          </span>
        )}
        <span className="stat-cost">
          {usd(agent.total_cost_usd)} {t('agents.spent')}
        </span>
      </div>
    </div>
  )
}

export default function AgentsPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['agents'],
    queryFn: api.listAgents,
  })

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('agents.title')}</h1>
          <div className="sub">{t('agents.subtitle')}</div>
        </div>
        <button className="btn btn-primary" onClick={() => navigate('/build')}>
          <Plus size={16} />
          {t('agents.new')}
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
          <div className="empty-title">{t('agents.empty.title')}</div>
          <div className="empty-body">{t('agents.empty.body')}</div>
          <button className="btn btn-primary" onClick={() => navigate('/build')}>
            <Plus size={16} />
            {t('agents.new')}
          </button>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="agent-grid">
          {data.map((a, i) => (
            <AgentCard key={a.id} agent={a} index={i} />
          ))}
        </div>
      )}
    </>
  )
}
