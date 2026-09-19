import { CircleCheck, CircleAlert, Clock3, LoaderCircle } from 'lucide-react'
import { statusLabels, type AnalysisRun } from './analysis-types'

const stages: Record<string, string> = {
  starting: 'Starting analysis', researching: 'Gathering evidence', analyzing: 'Reviewing evidence', validating: 'Validating result',
}
export default function AnalysisRunStatus({ run }: { run: AnalysisRun | undefined }) {
  const Icon = run?.status === 'completed' ? CircleCheck : run?.status === 'failed' || run?.status === 'insufficient_data' ? CircleAlert : run?.status === 'running' ? LoaderCircle : Clock3
  return <div className={`analysis-status ${run?.status === 'failed' ? 'error' : ''}`} role="status" aria-live="polite" aria-atomic="true">
    {run ? <><Icon size={18} aria-hidden="true" /><strong>{statusLabels[run.status]}</strong>
      {run.status === 'running' && <span>{stages[run.progress.stage ?? ''] ?? 'Reviewing evidence'}</span>}
      {run.status === 'queued' && <span>Waiting for the analysis worker.</span>}
    </> : <span>Select an agent to review or run analysis.</span>}
  </div>
}
