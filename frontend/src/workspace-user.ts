import { createContext, useContext } from 'react'

export type WorkspaceUser = { user_id: string; role: 'admin' | 'general' }
export const WorkspaceUserContext = createContext<WorkspaceUser | null>(null)

export function useWorkspaceUser() {
  const user = useContext(WorkspaceUserContext)
  if (!user) throw new Error('Workspace access has not been verified.')
  return user
}
