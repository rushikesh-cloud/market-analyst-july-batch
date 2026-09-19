export async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  let response: Response
  try {
    const isForm = options?.body instanceof FormData
    response = await fetch(path, {
      ...options,
      headers: {
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        ...options?.headers,
      },
    })
  } catch {
    throw new Error('Unable to connect. Please try again.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : 'Unable to save changes. Check the fields and try again.',
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
}
