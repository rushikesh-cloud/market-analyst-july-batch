import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Play, RefreshCw } from 'lucide-react'
import type { Company } from './company-types'
import { useApiRequest } from './use-api-request'
import { agents, type AgentAvailability, type AgentType, type AnalysisRequest } from './analysis-types'
import { useAnalysisHistory } from './use-analysis-history'
import AnalysisHistory from './AnalysisHistory'
import AnalysisRunStatus from './AnalysisRunStatus'
import AnalysisResultSummary from './AnalysisResultSummary'
import './analysis.css'

function savedSelection(): { companyId: string; agent: AgentType } {
  try {
    const saved = JSON.parse(sessionStorage.getItem('analysis-selection') ?? '{}')
    return { companyId: typeof saved.companyId === 'string' ? saved.companyId : '',
      agent: agents.some((item) => item.type === saved.agent) ? saved.agent : 'fundamental' }
  } catch { return { companyId: '', agent: 'fundamental' } }
}

export default function AnalysisPage({ request: injectedRequest }: { request?: AnalysisRequest }) {
  const authenticatedRequest = useApiRequest()
  const request = injectedRequest ?? authenticatedRequest
  const [companies, setCompanies] = useState<Company[]>([])
  const [availability, setAvailability] = useState<AgentAvailability[]>([])
  const [initialSelection] = useState(savedSelection)
  const [companyId, setCompanyId] = useState(initialSelection.companyId)
  const [agent, setAgent] = useState<AgentType>(initialSelection.agent)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const tabs = useRef<(HTMLButtonElement | null)[]>([])
  const history = useAnalysisHistory(companyId, agent, request)
  const selectedAvailability = availability.find((item) => item.agent_type === agent)

  useEffect(() => {
    if (!companyId) return
    try { sessionStorage.setItem('analysis-selection', JSON.stringify({ companyId, agent })) }
    catch { /* Storage may be disabled; the current selection remains usable. */ }
  }, [companyId, agent])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    void Promise.all([
      request<Company[]>('/api/companies', { signal: controller.signal }),
      request<{ items: AgentAvailability[] }>('/api/analysis-agents', { signal: controller.signal }),
    ]).then(([items, capabilities]) => {
      if (controller.signal.aborted) return
      setCompanies(items)
      setAvailability(capabilities.items)
      setCompanyId((previous) => items.some((company) => company.id === previous) ? previous : items[0]?.id ?? '')
      setLoading(false)
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return
      setError(failure instanceof Error ? failure.message : 'Unable to load analysis. Please retry.')
      setLoading(false)
    })
    return () => controller.abort()
  }, [request, revision])

  function navigateTabs(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const target = event.key === 'ArrowRight' ? (index + 1) % agents.length
      : event.key === 'ArrowLeft' ? (index + agents.length - 1) % agents.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? agents.length - 1 : null
    if (target === null) return
    event.preventDefault()
    setAgent(agents[target].type)
    tabs.current[target]?.focus()
  }

  const unavailable = !loading && selectedAvailability && !selectedAvailability.available
  const canRun = !loading && !error && Boolean(companyId) && Boolean(selectedAvailability?.available) && !history.loading && !history.active && !history.submitting
  const runError = history.latest?.error
  return <div className="analysis-page">
    <div className="page-heading">
      <div><h1>Agentic Analysis</h1><p>Independent assessments with saved evidence and history.</p></div>
      <button className="button primary" disabled={!canRun} onClick={() => void history.start()}>
        <Play size={16} aria-hidden="true" />{history.submitting ? 'Starting…' : 'Run analysis'}
      </button>
    </div>
    {error && <div className="analysis-error"><p role="alert" className="error">{error}</p><button className="button secondary" onClick={() => setRevision((value) => value + 1)}>Retry</button></div>}
    {loading && <p>Loading companies and agents…</p>}
    {!loading && !error && !companies.length && <section className="panel empty"><h2>No companies</h2><p>Add a company to start analysis.</p><a className="button secondary" href="#companies">Add company</a></section>}
    {companies.length > 0 && <>
      <section className="panel analysis-controls" aria-label="Analysis selection">
        <div className="field"><label htmlFor="analysis-company">Company</label>
          <select id="analysis-company" value={companyId} onChange={(event) => setCompanyId(event.target.value)}>
            {companies.map((company) => <option key={company.id} value={company.id}>{company.name} · {company.ticker}</option>)}
          </select>
        </div>
        <div className="tabs" role="tablist" aria-label="Analysis agents">
          {agents.map((item, index) => <button key={item.type} id={`analysis-tab-${item.type}`} ref={(node) => { tabs.current[index] = node }}
            role="tab" aria-selected={agent === item.type} aria-controls="analysis-agent-panel" tabIndex={agent === item.type ? 0 : -1}
            onClick={() => setAgent(item.type)} onKeyDown={(event) => navigateTabs(event, index)}>{item.name}</button>)}
        </div>
      </section>
      <div id="analysis-agent-panel" role="tabpanel" aria-labelledby={`analysis-tab-${agent}`}>
        {unavailable && <div className="analysis-unavailable"><p>{selectedAvailability.error?.message ?? 'This analysis agent is unavailable.'}</p>
          <button className="button secondary" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" />Check availability</button>
        </div>}
        <AnalysisRunStatus run={history.active ?? history.latest} />
        {history.error && <div className="analysis-error"><p className="error" role="alert">{history.error.message}</p>
          {history.errorCode === 'ticker_correction_required' ? <a className="button secondary" href="#companies">Correct ticker</a>
            : <button className="button secondary" onClick={history.retry}>Retry</button>}
        </div>}
        {runError && <div className="analysis-error"><p className="error">{runError.message}</p><p>Use Run analysis to try again.</p></div>}
        {history.loading ? <p>Loading analysis history…</p> : <AnalysisHistory items={history.items} selectedId={history.selectedId} onSelect={history.select} />}
        {history.displayedResult && <AnalysisResultSummary result={history.displayedResult} request={request} showingPrevious={history.showingPrevious} />}
      </div>
    </>}
  </div>
}
