import { SignInButton, SignUpButton, UserButton, useAuth } from '@clerk/react'
import { ChartNoAxesCombined } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useApiRequest } from './use-api-request'

export function AuthScreen({ children }: { children: ReactNode }) {
  return (
    <main className="auth-screen">
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <ChartNoAxesCombined size={28} aria-hidden="true" />
        <h1 id="auth-title">Market Analyst</h1>
        {children}
      </section>
    </main>
  )
}

function WorkspaceAccess({ children }: { children: ReactNode }) {
  const apiRequest = useApiRequest()
  const [allowed, setAllowed] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    setError('')
    void apiRequest('/api/auth/me').then(() => {
      if (active) setAllowed(true)
    }).catch((reason: Error) => {
      if (active) setError(reason.message)
    })
    return () => { active = false }
  }, [apiRequest, attempt])
  if (allowed) return children
  return (
    <AuthScreen>
      {error ? <>
        <p role="alert">{error}</p>
        <div className="auth-actions">
          <button className="button secondary" onClick={() => setAttempt(attempt + 1)}>Retry</button>
          <UserButton />
        </div>
      </> : <p role="status">Opening your workspace…</p>}
    </AuthScreen>
  )
}

export default function AuthBoundary({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, sessionId } = useAuth()
  if (!isLoaded) return <AuthScreen><p role="status">Loading sign-in…</p></AuthScreen>
  if (isSignedIn) return <WorkspaceAccess key={sessionId}>{children}</WorkspaceAccess>
  return (
    <AuthScreen>
      <p>Sign in to your research workspace.</p>
      <div className="auth-actions">
        <SignInButton mode="modal"><button className="button primary">Sign in</button></SignInButton>
        <SignUpButton mode="modal"><button className="button secondary">Sign up</button></SignUpButton>
      </div>
    </AuthScreen>
  )
}
