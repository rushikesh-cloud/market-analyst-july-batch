import { useAuth } from '@clerk/react'
import { useCallback } from 'react'
import { apiRequest } from './api-request'

export function useApiRequest() {
  const { getToken } = useAuth()
  return useCallback(
    <T,>(path: string, options?: RequestInit) => apiRequest<T>(getToken, path, options),
    [getToken],
  )
}
