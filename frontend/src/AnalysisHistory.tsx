import { statusLabels, type AnalysisRun } from './analysis-types'

export default function AnalysisHistory({ items, selectedId, onSelect }: {
  items: AnalysisRun[]; selectedId: string; onSelect: (id: string) => void
}) {
  if (!items.length) return <p className="analysis-empty">No analysis runs yet.</p>
  return <div className="field analysis-history">
    <label htmlFor="analysis-history">Run history</label>
    <select id="analysis-history" value={selectedId} onChange={(event) => onSelect(event.target.value)}>
      {items.map((run) => <option key={run.id} value={run.id}>
        {new Date(run.created_at).toLocaleString()} · {statusLabels[run.status]}
      </option>)}
    </select>
    {items.length === 100 && <span className="field-hint">Showing the latest 100 runs.</span>}
  </div>
}
