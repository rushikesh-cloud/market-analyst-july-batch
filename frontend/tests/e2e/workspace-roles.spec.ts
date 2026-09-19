import { expect, test } from '@playwright/test'
import { mockAnalysis, runFixture } from './analysis-scenarios'

test('general users only see analysis, including on direct management URLs', async ({ page }) => {
  const state = await mockAnalysis(page, [runFixture()])
  const managementRequests: string[] = []
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname
    if (path === '/api/companies' || path.startsWith('/api/documents')) managementRequests.push(path)
  })
  await page.goto('/tests/e2e/index.html?role=general#companies')
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav.getByRole('link')).toHaveCount(1)
  await expect(nav.getByRole('link', { name: 'Agentic Analysis' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Agentic Analysis', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/#analysis$/)
  await expect(page.getByRole('link', { name: 'Market Analyst home' })).toHaveAttribute('href', '#analysis')
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  await expect.poll(() => state.submissions).toBe(1)
  await page.evaluate(() => { location.hash = '#documents' })
  await expect(page).toHaveURL(/#analysis$/)
  await expect(page.getByRole('heading', { name: 'Agentic Analysis', exact: true })).toBeVisible()
  expect(managementRequests).toEqual([])
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(nav.getByRole('link')).toHaveCount(1)
  await expect(nav.getByRole('link', { name: 'Agentic Analysis' })).toBeVisible()
})

test('general users get administrator guidance for empty companies and ticker errors', async ({ page }) => {
  const state = await mockAnalysis(page)
  const companies = state.companies
  state.companies = []
  await page.goto('/tests/e2e/index.html?role=general')
  await expect(page.getByText('Ask an administrator to add a company before running analysis.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Add company' })).toHaveCount(0)
  state.companies = companies
  state.onSubmit = async (route) => {
    await route.fulfill({ status: 409, json: { detail: { code: 'ticker_correction_required', message: 'Ticker correction required.' } } })
    return true
  }
  await page.reload()
  await page.getByRole('button', { name: 'Run analysis', exact: true }).click()
  await expect(page.getByText('Ask an administrator to correct this company’s ticker.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Correct ticker' })).toHaveCount(0)
})

test('admins retain all navigation tabs and company creation', async ({ page }) => {
  await mockAnalysis(page)
  await page.goto('/tests/e2e/index.html')
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(nav.getByRole('link')).toHaveCount(3)
  for (const name of ['Companies', 'Documents', 'Agentic Analysis']) {
    await expect(nav.getByRole('link', { name, exact: true })).toBeVisible()
  }
  await expect(page.getByRole('heading', { name: 'Companies', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add company', exact: true }).first()).toBeEnabled()
  await nav.getByRole('link', { name: 'Agentic Analysis' }).click()
  await expect(page.getByRole('button', { name: 'Run analysis', exact: true })).toBeEnabled()
})
