import { useAuth } from '@clerk/react'
import { useCallback } from 'react'
import { apiRequest, type ApiRequestOptions } from './api-request'

export function useApiRequest() {
  const { getToken } = useAuth()
  return useCallback(
    <T,>(path: string, options?: ApiRequestOptions) => apiRequest<T>(getToken, path, options),
    [getToken],
  )
}
