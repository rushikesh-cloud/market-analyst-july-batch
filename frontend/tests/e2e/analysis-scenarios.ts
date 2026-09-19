/** C01-validated synthetic results, served only by Playwright route mocks. */
import { type Page, type Route } from '@playwright/test'
import fixtures from './analysis-fixtures.json' with { type: 'json' }

export type FixtureAgent = 'fundamental' | 'technical' | 'news'
export const companies = [fixtures.fundamental.company, {
  id: 'synthetic-second', name: 'Second Synthetic Company', ticker: 'SECOND.NS',
}]
export const agentItems = ['fundamental', 'technical', 'news'].map((agent_type) => ({
  agent_type, available: true, error: null,
}))

export function runFixture(
  agent: FixtureAgent = 'fundamental',
  options: { id?: string; status?: string; companyIndex?: number; scenario?: 'partial' | 'insufficient'; created?: string } = {},
) {
  const company = companies[options.companyIndex ?? 0]
  const source = options.scenario ? fixtures[options.scenario] : fixtures[agent]
  const result = structuredClone(source)
  const id = options.id ?? `run-${agent}`
  const status = options.status ?? result.status
  result.company = company
  result.run_id = id
  result.evidence.forEach((item) => { item.run_id = id })
  return {
    id, company_id: company.id, company, agent_type: agent, status,
    created_at: options.created ?? '2026-07-01T12:00:00Z',
    started_at: status === 'queued' ? null : '2026-07-01T12:00:00Z',
    finished_at: ['queued', 'running'].includes(status) ? null : '2026-07-01T12:01:00Z',
    as_of: status === 'queued' ? null : result.as_of,
    progress: status === 'running' ? { stage: 'Reviewing evidence' } : {},
    result: ['completed', 'insufficient_data'].includes(status) ? result : null,
    error: status === 'failed' ? { code: 'provider_unavailable', message: 'The analysis provider is unavailable. Try again later.' } : null,
  }
}

export type MockRun = ReturnType<typeof runFixture>
export type MockAnalysisState = {
  companies: typeof companies;
  agents: typeof agentItems;
  runs: MockRun[];
  submissions: number;
  polls: number;
  artifactRequests: number;
  onHistory?: (route: Route, company: string, agent: FixtureAgent) => Promise<boolean>;
  onPoll?: (route: Route, id: string) => Promise<boolean>;
  onSubmit?: (route: Route, company: string, agent: FixtureAgent) => Promise<boolean>;
}

export async function mockAnalysis(page: Page, initial: MockRun[] = []): Promise<MockAnalysisState> {
  const state: MockAnalysisState = {
    companies: structuredClone(companies), agents: structuredClone(agentItems),
    runs: initial, submissions: 0, polls: 0, artifactRequests: 0,
  }
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (['/api/companies', '/api/analysis/companies'].includes(url.pathname)) return route.fulfill({ json: state.companies })
    if (url.pathname === '/api/analysis-agents') return route.fulfill({ json: { items: state.agents } })
    const history = url.pathname.match(/^\/api\/companies\/([^/]+)\/analysis-runs$/)
    if (history) {
      const company = decodeURIComponent(history[1])
      if (route.request().method() === 'POST') {
        state.submissions++
        const agent = route.request().postDataJSON().agent_type as FixtureAgent
        if (await state.onSubmit?.(route, company, agent)) return
        const run = runFixture(agent, { id: `new-${state.submissions}`, status: 'queued', companyIndex: companies.findIndex((item) => item.id === company), created: '2026-07-02T12:00:00Z' })
        state.runs.unshift(run)
        return route.fulfill({ status: 202, json: run })
      }
      const agent = url.searchParams.get('agent_type') as FixtureAgent
      if (await state.onHistory?.(route, company, agent)) return
      return route.fulfill({ json: {
        items: state.runs.filter((run) => run.company_id === company && (!agent || run.agent_type === agent)),
        limit: Number(url.searchParams.get('limit') ?? 20), offset: Number(url.searchParams.get('offset') ?? 0),
      } })
    }
    if (/\/artifacts\//.test(url.pathname)) {
      state.artifactRequests++
      return route.fulfill({ contentType: 'image/png', body: Buffer.from('synthetic image artifact') })
    }
    const detail = url.pathname.match(/^\/api\/analysis-runs\/([^/]+)$/)
    if (detail) {
      state.polls++
      if (await state.onPoll?.(route, detail[1])) return
      const run = state.runs.find((item) => item.id === detail[1])
      return route.fulfill({ status: run ? 200 : 404, json: run ?? { detail: 'Not found.' } })
    }
    return route.fulfill({ status: 404, json: { detail: 'Unknown mock route.' } })
  })
  return state
}

export async function openAnalysis(page: Page) {
  await page.goto('/tests/e2e/index.html#analysis')
}
