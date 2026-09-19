import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { apiRequest } from '../src/api-request.ts'

const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })

test('retrieves a current token for each request and preserves custom headers', async () => {
  let tokenNumber = 0
  const requests = []
  globalThis.fetch = async (path, options) => {
    requests.push({ path, options })
    return Response.json({ ok: true })
  }
  const getToken = async () => `session-${++tokenNumber}`
  await apiRequest(getToken, '/api/companies', { headers: new Headers({ 'X-Request': 'test' }) })
  await apiRequest(getToken, '/api/documents')
  assert.equal(requests[0].options.headers.get('Authorization'), 'Bearer session-1')
  assert.equal(requests[1].options.headers.get('Authorization'), 'Bearer session-2')
  assert.equal(requests[0].options.headers.get('X-Request'), 'test')
  assert.equal(requests[0].options.redirect, 'error')
})

test('signed-out requests and non-API targets never call fetch', async () => {
  globalThis.fetch = () => { assert.fail('fetch must not run') }
  await assert.rejects(apiRequest(async () => null, '/api/companies'), /sign in/)
  for (const path of ['https://example.com/api/data', '//example.com/api/data', '/other']) {
    await assert.rejects(apiRequest(async () => 'session', path), /Invalid API path/)
  }
})

test('multipart uploads retain their body and let the browser set the boundary', async () => {
  const body = new FormData()
  body.append('file', new Blob(['%PDF-test']), 'report.pdf')
  globalThis.fetch = async (_path, options) => {
    assert.equal(options.body, body)
    assert.equal(options.headers.has('Content-Type'), false)
    assert.equal(options.headers.get('Authorization'), 'Bearer session')
    return Response.json({ id: 'report' }, { status: 202 })
  }
  assert.deepEqual(await apiRequest(async () => 'session', '/api/documents', { method: 'POST', body }), { id: 'report' })
})

test('surfaces expired-session and workspace-denied responses', async () => {
  globalThis.fetch = async () => new Response(null, { status: 401 })
  await assert.rejects(apiRequest(async () => 'expired', '/api/companies'), /session has expired/)
  globalThis.fetch = async () => Response.json({ detail: 'Awaiting access.' }, { status: 403 })
  await assert.rejects(apiRequest(async () => 'session', '/api/companies'), /Awaiting access/)
})

test('handles deletes and network failures', async () => {
  globalThis.fetch = async () => new Response(null, { status: 204 })
  assert.equal(await apiRequest(async () => 'session', '/api/companies/id', { method: 'DELETE' }), undefined)
  globalThis.fetch = async () => { throw new TypeError('network failure') }
  await assert.rejects(apiRequest(async () => 'session', '/api/companies'), /Unable to connect/)
})

test('artifact downloads retain authentication and return bytes without leaking response options', async () => {
  globalThis.fetch = async (_path, options) => {
    assert.equal(options.headers.get('Authorization'), 'Bearer session')
    assert.equal(options.responseType, undefined)
    assert.equal(options.redirect, 'error')
    return new Response(new Uint8Array([137, 80, 78, 71]), { headers: { 'Content-Type': 'image/png' } })
  }
  const blob = await apiRequest(async () => 'session', '/api/analysis-runs/run/artifacts/id', { responseType: 'blob' })
  assert.equal(blob.type, 'image/png')
  assert.deepEqual([...new Uint8Array(await blob.arrayBuffer())], [137, 80, 78, 71])
})

test('analysis recovery retains the API error code', async () => {
  globalThis.fetch = async () => Response.json({ detail: { code: 'ticker_correction_required', message: 'Correct ticker.' } }, { status: 409 })
  await assert.rejects(apiRequest(async () => 'session', '/api/companies/id/analysis-runs'),
    (error) => error.code === 'ticker_correction_required' && error.message === 'Correct ticker.')
})
