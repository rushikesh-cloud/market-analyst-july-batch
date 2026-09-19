import { expect, test } from '@playwright/test'
import { companies, mockAnalysis, openAnalysis, runFixture } from './analysis-scenarios'

test('C09-01: empty companies and initial selection expose honest empty states', async ({ page }) => {
  const state = await mockAnalysis(page)
  state.companies = []
  await openAnalysis(page)
  await expect(page.getByRole('heading', { name: 'Agentic Analysis', exact: true })).toBeVisible()
  await expect(page.getByText('Add a company to start analysis.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeDisabled()
  state.companies = companies
  await page.reload()
  await expect(page.getByLabel('Company', { exact: true })).toHaveValue(companies[0].id)
  await expect(page.getByText('No analysis runs yet.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
})

test('C09-02: duplicate clicks submit once and terminal completion stops polling', async ({ page }) => {
  await page.clock.install()
  const state = await mockAnalysis(page)
  await openAnalysis(page)
  const button = page.getByRole('button', { name: 'Run analysis', exact: true })
  await expect(button).toBeEnabled()
  await button.evaluate((element: HTMLButtonElement) => { element.click(); element.click() })
  await expect.poll(() => state.submissions).toBe(1)
  await expect(page.getByRole('status')).toContainText('Queued')
  state.runs[0] = runFixture('fundamental', { id: 'new-1', status: 'running' })
  await page.clock.fastForward(2000)
  await expect(page.getByRole('status')).toContainText('Reviewing evidence')
  state.runs[0] = runFixture('fundamental', { id: 'new-1' })
  await page.clock.fastForward(2000)
  await expect(page.getByRole('heading', { name: 'Result', exact: true })).toBeVisible()
  await expect(page.getByRole('definition').filter({ hasText: '6.0 / 10' })).toBeVisible()
  const polls = state.polls
  await page.clock.fastForward(6000)
  expect(state.polls).toBe(polls)
})

test('C09-03: superseded company history never replaces the new selection', async ({ page }) => {
  const state = await mockAnalysis(page, [runFixture('fundamental', { companyIndex: 1, id: 'second-result' })])
  let release: (() => void) | undefined
  state.onHistory = async (route, company) => {
    if (company !== companies[0].id) return false
    await new Promise<void>((resolve) => { release = resolve })
    await route.fulfill({ json: { items: [runFixture('fundamental')], limit: 20, offset: 0 } })
    return true
  }
  await openAnalysis(page)
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.getByLabel('Company', { exact: true }).selectOption(companies[1].id)
  await expect(page.getByTestId('analysis-result')).toContainText(companies[1].name)
  release?.()
  await expect(page.getByTestId('analysis-result')).not.toContainText(companies[0].name)
  await page.getByRole('tab', { name: 'Technical', exact: true }).click()
  await expect(page.getByText('No analysis runs yet.', { exact: true })).toBeVisible()
  await expect(page.getByTestId('analysis-result')).toHaveCount(0)
})

test('C09-03: a late submission response cannot replace another agent', async ({ page }) => {
  const state = await mockAnalysis(page)
  let release: (() => void) | undefined
  state.onSubmit = async (route) => {
    await new Promise<void>((resolve) => { release = resolve })
    await route.fulfill({ status: 202, json: runFixture('fundamental', { id: 'late-run', status: 'queued' }) })
    return true
  }
  await openAnalysis(page)
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  await expect.poll(() => Boolean(release)).toBe(true)
  await page.getByRole('tab', { name: 'Technical', exact: true }).click()
  release?.()
  await expect(page.getByText('No analysis runs yet.', { exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Technical', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('status')).not.toContainText('Queued')
})

test('C09-04: reload resumes active state and reruns preserve the prior success', async ({ page }) => {
  await page.clock.install()
  const old = runFixture('fundamental', { id: 'old-result' })
  const state = await mockAnalysis(page, [old])
  await openAnalysis(page)
  await expect(page.getByTestId('analysis-result')).toContainText('Synthetic fixture only')
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Queued')
  await expect(page.getByTestId('analysis-result')).toContainText('Synthetic fixture only')
  await page.reload()
  await expect(page.getByRole('status')).toContainText('Queued')
  await expect(page.getByTestId('analysis-result')).toContainText('Synthetic fixture only')
  await page.getByLabel('Run history', { exact: true }).selectOption('old-result')
  await expect(page.getByTestId('analysis-result')).toContainText('Synthetic fixture only')
  state.runs[0] = runFixture('fundamental', { id: 'new-1', status: 'failed' })
  await page.clock.fastForward(2000)
  await expect(page.getByRole('status')).toContainText('Failed')
  await expect(page.getByTestId('analysis-result')).toContainText('Synthetic fixture only')
})

test('C09-04: reload retains a second company and active tab; leaving stops polling', async ({ page }) => {
  await page.clock.install()
  const state = await mockAnalysis(page, [runFixture('technical', { companyIndex: 1, status: 'running' })])
  await openAnalysis(page)
  await page.getByLabel('Company', { exact: true }).selectOption(companies[1].id)
  await page.getByRole('tab', { name: 'Technical', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Running')
  await page.reload()
  await expect(page.getByLabel('Company', { exact: true })).toHaveValue(companies[1].id)
  await expect(page.getByRole('tab', { name: 'Technical', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('status')).toContainText('Running')
  await page.getByRole('link', { name: 'Companies', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Companies', exact: true })).toBeVisible()
  const polls = state.polls
  await page.clock.fastForward(6000)
  expect(state.polls).toBe(polls)
})

test('C09-05: insufficient data and unavailable agents preserve context and recovery', async ({ page }) => {
  const state = await mockAnalysis(page, [runFixture('technical', { scenario: 'insufficient' })])
  await openAnalysis(page)
  await page.getByRole('tab', { name: 'Technical', exact: true }).click()
  await expect(page.getByText('Not scored', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('status')).toContainText('Insufficient data')
  await expect(page.getByText('0.0 / 10', { exact: true })).toHaveCount(0)
  state.agents = state.agents.map((item) => ({ ...item, available: false, error: { code: 'agent_unavailable', message: 'This analysis agent is not installed.' } }))
  await page.reload()
  await expect(page.getByText('This analysis agent is not installed.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeDisabled()
  await expect(page.getByLabel('Company', { exact: true })).toHaveValue(companies[0].id)
})

test('C09-05: read failures retry and ticker errors offer correction without losing context', async ({ page }) => {
  const state = await mockAnalysis(page)
  let failedRead = true
  state.onHistory = async (route) => {
    if (!failedRead) return false
    await route.fulfill({ status: 503, json: { detail: { code: 'provider_unavailable', message: 'History is temporarily unavailable.' } } })
    return true
  }
  await openAnalysis(page)
  await expect(page.getByRole('alert')).toContainText('History is temporarily unavailable.')
  failedRead = false
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByText('No analysis runs yet.', { exact: true })).toBeVisible()
  state.onSubmit = async (route) => {
    await route.fulfill({ status: 409, json: { detail: { code: 'ticker_correction_required', message: 'Save a canonical NSE ticker before analysis.' } } })
    return true
  }
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Save a canonical NSE ticker')
  await expect(page.getByRole('link', { name: 'Correct ticker', exact: true })).toHaveAttribute('href', '#companies')
  await expect(page.getByLabel('Company', { exact: true })).toHaveValue(companies[0].id)
})

test('C09-06: keyboard tabs, mobile layout, and 200 percent zoom remain usable', async ({ page }) => {
  await mockAnalysis(page, ['fundamental', 'technical', 'news'].map((agent) => runFixture(agent as 'fundamental' | 'technical' | 'news')))
  await openAnalysis(page)
  const fundamental = page.getByRole('tab', { name: 'Fundamental', exact: true })
  await fundamental.focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: 'Technical', exact: true })).toBeFocused()
  await expect(page.getByRole('tab', { name: 'Technical', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('End')
  await expect(page.getByRole('tab', { name: 'News', exact: true })).toBeFocused()
  await page.keyboard.press('Home')
  await expect(fundamental).toBeFocused()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByLabel('Company', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: '../output/playwright/analysis-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.evaluate(() => { document.documentElement.style.zoom = '2' })
  await expect(page.getByRole('table', { name: 'Parameter scores' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  await page.screenshot({ path: '../output/playwright/analysis-zoom.png', fullPage: true })
  await page.evaluate(() => { document.documentElement.style.zoom = '1' })
  await page.screenshot({ path: '../output/playwright/analysis-desktop.png', fullPage: true })
})

test('C09-07: all detail variants use safe text and artifacts use authenticated requests', async ({ page }) => {
  const results = ['fundamental', 'technical', 'news'].map((agent) => runFixture(agent as 'fundamental' | 'technical' | 'news'))
  results[0] = runFixture('fundamental', { scenario: 'partial' })
  results[0].result!.summary = '<script>window.analysisInjected = true</script>'
  results[0].result!.evidence[0].excerpt = '<img src=x onerror="window.analysisInjected=true">'
  results[0].result!.evidence[0].source.url = 'javascript:window.analysisInjected=true'
  results[1].result!.evidence[0].source.url = 'data:text/html,<script>alert(1)</script>'
  await page.addInitScript(() => {
    const originalCreate = URL.createObjectURL.bind(URL)
    const originalRevoke = URL.revokeObjectURL.bind(URL)
    const tracker = window as Window & { createdBlobs: string[]; revokedBlobs: string[] }
    tracker.createdBlobs = []
    tracker.revokedBlobs = []
    URL.createObjectURL = (blob) => { const url = originalCreate(blob); tracker.createdBlobs.push(url); return url }
    URL.revokeObjectURL = (url) => { tracker.revokedBlobs.push(url); originalRevoke(url) }
  })
  const state = await mockAnalysis(page, results)
  await openAnalysis(page)
  await expect(page.getByTestId('analysis-result')).toContainText('<script>window.analysisInjected = true</script>')
  await expect(page.getByTestId('analysis-result')).toContainText('<img src=x onerror=')
  expect(await page.evaluate(() => (window as Window & { analysisInjected?: boolean }).analysisInjected)).toBeUndefined()
  await expect(page.locator('a[href^="javascript:"], a[href^="data:"]')).toHaveCount(0)
  await expect(page.getByRole('definition').filter({ hasText: '90%' })).toBeVisible()
  for (const name of ['Technical', 'News', 'Fundamental']) {
    await page.getByRole('tab', { name, exact: true }).click()
    await expect(page.getByRole('table', { name: 'Parameter scores' })).toBeVisible()
  }
  await page.getByRole('tab', { name: 'Technical', exact: true }).click()
  const request = page.waitForRequest((request) => request.url().includes('/artifacts/'))
  await page.getByRole('button', { name: 'Download artifact', exact: true }).first().click()
  expect((await request).headers().authorization).toContain('Bearer ')
  await expect.poll(() => state.artifactRequests).toBe(1)
  await expect.poll(() => page.evaluate(() => (window as Window & { createdBlobs: string[] }).createdBlobs.length)).toBe(1)
  await page.getByRole('link', { name: 'Companies', exact: true }).click()
  await expect.poll(() => page.evaluate(() => (window as Window & { revokedBlobs: string[] }).revokedBlobs.length)).toBeGreaterThan(0)
})
