import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { ClerkProvider } from '@clerk/react'
import AuthBoundary, { AuthScreen } from './AuthBoundary'
import './styles.css'

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {publishableKey ? (
      <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/" appearance={{
        variables: {
          colorPrimary: 'var(--accent)', colorForeground: 'var(--text)', colorMutedForeground: 'var(--muted)',
          colorBackground: 'var(--surface)', colorDanger: 'var(--danger)', borderRadius: '8px',
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
      }}>
        <AuthBoundary><App /></AuthBoundary>
      </ClerkProvider>
    ) : (
      <AuthScreen><p role="alert">Sign-in is unavailable. Please contact your workspace administrator.</p></AuthScreen>
    )}
  </StrictMode>,
)
