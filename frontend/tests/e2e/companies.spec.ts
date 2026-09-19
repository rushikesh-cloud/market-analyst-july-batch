import { expect, test } from '@playwright/test'

const initialCompany = { id: 'synthetic-company', name: 'Synthetic Company', ticker: 'SYNTHETIC.NS' }

test('C04-06: add and edit display canonical tickers returned by the API', async ({ page }) => {
  const companies = [initialCompany]
  const requests: { name: string; ticker: string }[] = []
  await page.route('**/api/companies**', async (route) => {
    const request = route.request()
    if (request.method() === 'GET') return route.fulfill({ json: companies })
    const payload = request.postDataJSON()
    requests.push(payload)
    const saved = {
      ...payload,
      id: 'created-company',
      ticker: payload.ticker.endsWith('.NS') ? payload.ticker : `${payload.ticker}.NS`,
    }
    companies.splice(1, 1, saved)
    return route.fulfill({ status: request.method() === 'POST' ? 201 : 200, json: saved })
  })
  await page.goto('/tests/e2e/index.html#companies')
  await expect(page.getByRole('heading', { name: 'Companies', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add company', exact: true }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Company name', { exact: true }).fill('  Synthetic Added  ')
  await dialog.getByLabel('Yahoo Finance ticker', { exact: true }).fill(' reliance ')
  await dialog.getByRole('button', { name: 'Add company', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('RELIANCE.NS', { exact: true })).toBeVisible()
  expect(requests[0]).toEqual({ name: 'Synthetic Added', ticker: 'RELIANCE' })
  await page.getByRole('button', { name: 'Edit Synthetic Added', exact: true }).click()
  await dialog.getByLabel('Yahoo Finance ticker', { exact: true }).fill('m&m')
  await dialog.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('M&M.NS', { exact: true })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: 'Company updated.' })).toBeVisible()
})

test('C04-06: invalid input preserves the dialog and announces an inline ticker error', async ({ page }) => {
  const error = 'Use an NSE equity symbol such as RELIANCE.NS. Other exchanges are not supported.'
  await page.route('**/api/companies**', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ json: [initialCompany] })
    return route.fulfill({ status: 422, json: { detail: error } })
  })
  await page.goto('/tests/e2e/index.html#companies')
  await page.getByRole('button', { name: 'Add company', exact: true }).click()
  const dialog = page.getByRole('dialog')
  const ticker = dialog.getByLabel('Yahoo Finance ticker', { exact: true })
  await dialog.getByLabel('Company name', { exact: true }).fill('Preserved synthetic name')
  await ticker.fill('RELIANCE.BO')
  await dialog.getByRole('button', { name: 'Add company', exact: true }).click()
  await expect(dialog.getByRole('alert')).toHaveText(error)
  await expect(ticker).toHaveValue('RELIANCE.BO')
  await expect(ticker).toHaveAttribute('aria-invalid', 'true')
  await expect(ticker).toHaveAttribute('aria-describedby', /company-error/)
  await expect(dialog.getByLabel('Company name', { exact: true })).toHaveValue('Preserved synthetic name')
  await expect(dialog.getByRole('button', { name: 'Add company', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(dialog).not.toBeVisible()
})
