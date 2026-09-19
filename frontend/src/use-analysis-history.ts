import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api-request'
import { isActive, type AgentType, type AnalysisHistoryResponse, type AnalysisRequest, type AnalysisRun } from './analysis-types'

type HistoryState = {
  scope: string; items: AnalysisRun[]; selectedId: string; loading: boolean
  submitting: boolean; error: Error | null
}
const initial = (scope: string): HistoryState => ({ scope, items: [], selectedId: '', loading: true, submitting: false, error: null })
const asError = (error: unknown) => error instanceof Error ? error : new Error('Unable to load analysis. Please retry.')

export function useAnalysisHistory(companyId: string, agent: AgentType, request: AnalysisRequest) {
  const scope = `${companyId}/${agent}`
  const latestScope = useRef(scope)
  latestScope.current = scope
  const generation = useRef(0)
  const submitting = useRef<string | null>(null)
  const [state, setState] = useState<HistoryState>(() => initial(scope))
  const [revision, setRevision] = useState(0)
  const retry = useCallback(() => setRevision((value) => value + 1), [])
  const historyPath = `/api/companies/${encodeURIComponent(companyId)}/analysis-runs?agent_type=${agent}&limit=100&offset=0`
  const current = state.scope === scope ? state : initial(scope)
  const active = current.items.find(isActive)

  useEffect(() => {
    const currentGeneration = ++generation.current
    const controller = new AbortController()
    submitting.current = null
    setState((old) => old.scope === scope ? { ...old, loading: true, error: null, submitting: false } : initial(scope))
    if (!companyId) {
      setState({ ...initial(scope), loading: false })
      return () => controller.abort()
    }
    void request<AnalysisHistoryResponse>(historyPath, { signal: controller.signal }).then((response) => {
      if (controller.signal.aborted || generation.current !== currentGeneration || latestScope.current !== scope) return
      const items = response.items.filter((run) => run.company_id === companyId && run.agent_type === agent)
      setState((old) => ({ ...initial(scope), items,
        selectedId: items.some((item) => item.id === old.selectedId) ? old.selectedId : items[0]?.id ?? '', loading: false }))
    }).catch((error: unknown) => {
      if (!controller.signal.aborted && generation.current === currentGeneration && latestScope.current === scope) {
        setState((old) => ({ ...old, loading: false, error: asError(error) }))
      }
    })
    return () => { controller.abort(); generation.current++ }
  }, [companyId, agent, historyPath, request, revision, scope])

  useEffect(() => {
    if (!active || current.error) return
    const controller = new AbortController()
    const currentGeneration = generation.current
    let timer: ReturnType<typeof setTimeout>
    const isCurrent = () => !controller.signal.aborted && latestScope.current === scope && generation.current === currentGeneration
    const poll = async () => {
      try {
        const run = await request<AnalysisRun>(`/api/analysis-runs/${encodeURIComponent(active.id)}`, { signal: controller.signal })
        if (!isCurrent()) return
        if (run.company_id !== companyId || run.agent_type !== agent || run.id !== active.id) {
          throw new Error('The analysis response could not be verified. Please retry.')
        }
        if (isActive(run)) {
          setState((old) => ({ ...old, items: old.items.map((item) => item.id === run.id ? run : item) }))
          timer = setTimeout(poll, 2000)
        } else {
          try {
            const history = await request<AnalysisHistoryResponse>(historyPath, { signal: controller.signal })
            if (isCurrent()) setState((old) => ({ ...old, items: history.items.filter((item) => item.company_id === companyId && item.agent_type === agent).map((item) => item.id === run.id ? run : item) }))
          } catch (error) {
            if (isCurrent()) setState((old) => ({ ...old, items: old.items.map((item) => item.id === run.id ? run : item), error: asError(error) }))
          }
        }
      } catch (error) {
        if (isCurrent()) setState((old) => ({ ...old, error: asError(error) }))
      }
    }
    timer = setTimeout(poll, 2000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [active?.id, agent, companyId, current.error, historyPath, request, scope])

  async function start() {
    if (!companyId || active || submitting.current === scope || current.loading) return
    submitting.current = scope
    const currentGeneration = generation.current
    setState((old) => ({ ...old, submitting: true, error: null }))
    try {
      const run = await request<AnalysisRun>(`/api/companies/${encodeURIComponent(companyId)}/analysis-runs`, {
        method: 'POST', body: JSON.stringify({ agent_type: agent }),
      })
      if (latestScope.current !== scope || generation.current !== currentGeneration) return
      if (run.company_id !== companyId || run.agent_type !== agent) throw new Error('The analysis response could not be verified. Please retry.')
      setState((old) => ({ ...old, items: [run, ...old.items.filter((item) => item.id !== run.id)], selectedId: run.id, submitting: false }))
    } catch (error) {
      if (latestScope.current === scope && generation.current === currentGeneration) {
        setState((old) => ({ ...old, submitting: false, error: asError(error) }))
      }
    } finally {
      if (submitting.current === scope) submitting.current = null
    }
  }

  const select = (selectedId: string) => setState((old) => ({ ...old, selectedId }))
  const selected = current.items.find((run) => run.id === current.selectedId) ?? current.items[0]
  const previousSuccess = current.items.find((run) => run.status === 'completed' && run.result)
  return {
    ...current, active, selected, latest: current.items[0],
    displayedResult: selected?.result ?? previousSuccess?.result ?? null,
    showingPrevious: Boolean(selected && !selected.result && previousSuccess),
    errorCode: current.error instanceof ApiError ? current.error.code : undefined,
    start, retry, select,
  }
}
