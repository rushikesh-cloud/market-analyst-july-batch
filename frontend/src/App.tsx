import { useEffect, useState } from 'react'

type HealthResponse = { status: string }

export default function App() {
  const [apiStatus, setApiStatus] = useState('Checking API…')

  useEffect(() => {
    fetch('/api/health')
      .then((response) => response.json() as Promise<HealthResponse>)
      .then(({ status }) => setApiStatus(`API is ${status}`))
      .catch(() => setApiStatus('API is unavailable'))
  }, [])

  return (
    <main>
      <p className="eyebrow">Market Analyst</p>
      <h1>Stock research, built to grow.</h1>
      <p>React and FastAPI are connected and ready for the analysis workflow.</p>
      <span className="status">{apiStatus}</span>
    </main>
  )
}
