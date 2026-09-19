/** Mount the real application shell; mock only auth and HTTP in this test server. */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from '../../src/App'
import '../../src/styles.css'

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
