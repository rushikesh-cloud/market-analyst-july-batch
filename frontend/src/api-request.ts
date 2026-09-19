export async function apiRequest<T>(
  getToken: () => Promise<string | null>,
  path: string,
  options?: RequestInit,
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
  try {
    response = await fetch(path, {
      ...options,
      headers,
      redirect: 'error',
    })
  } catch {
    throw new Error('Unable to connect. Please try again.')
  }
  if (!response.ok) {
    if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
    const body = await response.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : 'Unable to save changes. Check the fields and try again.',
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
