import type { ReactNode } from 'react'
import AnalysisEvidence, { evidenceElementId } from './AnalysisEvidence'
import type { AgentResult, AnalysisRequest } from './analysis-types'

function Findings({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null
  return <section><h3>{label}</h3><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></section>
}

export default function AnalysisResultSummary({ result, request, showingPrevious, renderDetails }: {
  result: AgentResult; request: AnalysisRequest; showingPrevious: boolean
  renderDetails?: (result: AgentResult) => ReactNode
}) {
  return <section className="panel analysis-result" data-testid="analysis-result" aria-labelledby="analysis-result-heading">
    <div className="analysis-result-heading">
      <h2 id="analysis-result-heading">Result</h2>
      {showingPrevious && <p>Previous successful result</p>}
      <p><strong>{result.company.name}</strong> <span className="ticker">{result.company.ticker}</span></p>
      <p>Assessed {new Date(result.as_of).toLocaleString()} · {result.horizon}</p>
    </div>
    <dl className="analysis-metrics">
      <div><dt>Final score</dt><dd>{result.final_score === null ? 'Not scored' : `${result.final_score.toFixed(1)} / 10`}</dd></div>
      <div><dt>Evidence coverage</dt><dd>{Number(result.coverage.toFixed(1))}%</dd></div>
      <div><dt>Confidence</dt><dd className="analysis-capitalize">{result.confidence}</dd></div>
    </dl>
    {result.details.kind === 'news' && <p className="analysis-coverage-note">{result.details.coverage_description}</p>}
    <p className="analysis-summary">{result.summary}</p>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Scrollable parameter scores">
      <table aria-label="Parameter scores">
        <thead><tr><th scope="col">Parameter</th><th scope="col">Score</th><th scope="col">Weight</th><th scope="col">Assessment</th></tr></thead>
        <tbody>{result.parameters.map((parameter) => <tr key={parameter.key}>
          <th scope="row">{parameter.name}</th>
          <td>{parameter.score === null ? 'Not scored' : `${parameter.score.toFixed(1)} / 10`}</td>
          <td>{parameter.weight}</td>
          <td><p>{parameter.explanation}</p>
            {parameter.evidence_ids.map((id) => <a className="analysis-citation" key={id} href={`#${evidenceElementId(result.run_id, id)}`} onClick={(event) => {
              event.preventDefault()
              const element = document.getElementById(evidenceElementId(result.run_id, id))
              element?.scrollIntoView({ block: 'center' })
              element?.focus({ preventScroll: true })
            }}>{id}</a>)}
          </td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="analysis-findings">
      <Findings label="Strengths" items={result.strengths} />
      <Findings label="Risks" items={result.risks} />
      <Findings label="Limitations" items={result.limitations} />
    </div>
    {renderDetails?.(result)}
    <AnalysisEvidence key={result.run_id} runId={result.run_id} evidence={result.evidence} request={request} />
  </section>
}
