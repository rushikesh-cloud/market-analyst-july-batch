export type ApiRequestOptions = RequestInit & { responseType?: 'json' | 'blob' }

export class ApiError extends Error {
  readonly code?: string
  constructor(message: string, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

export async function apiRequest<T>(
  getToken: () => Promise<string | null>,
  path: string,
  options?: ApiRequestOptions,
): Promise<T> {
  // Only send session credentials to this application's API.
  if (!path.startsWith('/api/')) throw new Error('Invalid API path.')
  const token = await getToken()
  if (!token) throw new Error('Please sign in to continue.')
  const headers = new Headers(options?.headers)
  headers.set('Authorization', `Bearer ${token}`)
  if (!(options?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let response: Response
  const { responseType = 'json', ...fetchOptions } = options ?? {}
  try {
    response = await fetch(path, {
      ...fetchOptions,
      headers,
      redirect: 'error',
    })
  } catch {
    throw new Error('Unable to connect. Please try again.')
  }
  if (!response.ok) {
    if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const message = typeof detail === 'string'
      ? detail
      : typeof detail?.message === 'string'
        ? detail.message
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ')
          : ''
    throw new ApiError(message || 'Unable to save changes. Check the fields and try again.',
      typeof detail?.code === 'string' ? detail.code : undefined)
  }
  return response.status === 204 ? (undefined as T)
    : responseType === 'blob' ? await response.blob() as T : response.json()
}
