/** Mount the real application shell; mock only auth and HTTP in this test server. */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '../../src/App'
import { WorkspaceUserContext } from '../../src/workspace-user'
import '../../src/styles.css'

const role = new URLSearchParams(window.location.search).get('role') === 'general' ? 'general' : 'admin'
createRoot(document.getElementById('root')!).render(
  <StrictMode><WorkspaceUserContext.Provider value={{ user_id: 'synthetic', role }}><App /></WorkspaceUserContext.Provider></StrictMode>,
)
