import { useEffect, useRef, useState } from 'react'
import { Download, ExternalLink } from 'lucide-react'
import type { AnalysisRequest, EvidenceReference } from './analysis-types'

export const evidenceElementId = (runId: string, id: string) => `evidence-${encodeURIComponent(runId)}-${encodeURIComponent(id)}`
function sourceLink(value: string | null) {
  if (!value) return null
  try {
    const parsed = new URL(value)
    return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : null
  } catch { return null }
}

export default function AnalysisEvidence({ runId, evidence, request }: {
  runId: string; evidence: EvidenceReference[]; request: AnalysisRequest
}) {
  const [downloading, setDownloading] = useState<string | null>(null)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const blobs = useRef(new Set<string>())
  useEffect(() => {
    mounted.current = true
    const activeBlobs = blobs.current
    return () => { mounted.current = false; activeBlobs.forEach((url) => URL.revokeObjectURL(url)); activeBlobs.clear() }
  }, [])

  async function download(id: string) {
    if (downloading) return
    setDownloading(id)
    setError('')
    try {
      const blob = await request<Blob>(`/api/analysis-runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(id)}`, { responseType: 'blob' })
      if (!mounted.current) return
      const url = URL.createObjectURL(blob)
      blobs.current.add(url)
      const link = document.createElement('a')
      link.href = url
      const extension = blob.type === 'image/png' ? 'png' : blob.type === 'application/json' ? 'json' : 'bin'
      link.download = `analysis-artifact.${extension}`
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => { URL.revokeObjectURL(url); blobs.current.delete(url) }, 1000)
    } catch (failure) {
      if (mounted.current) setError(failure instanceof Error ? failure.message : 'Artifact unavailable. Please retry.')
    } finally {
      if (mounted.current) setDownloading(null)
    }
  }

  return <section className="analysis-evidence" aria-labelledby="analysis-evidence-heading">
    <h3 id="analysis-evidence-heading">Evidence</h3>
    {!evidence.length && <p>No supporting evidence was available.</p>}
    {error && <p className="error" role="alert">{error}</p>}
    <ol className="analysis-evidence-list">
      {evidence.map((item) => {
        const href = sourceLink(item.source.url)
        return <li key={item.id} id={evidenceElementId(runId, item.id)} tabIndex={-1}>
          <div className="analysis-evidence-title"><strong>{item.source.title}</strong><span>{item.id}</span></div>
          {item.excerpt && <p>{item.excerpt}</p>}
          {item.observation && <p>{item.observation.description}{item.observation.value !== null ? `: ${item.observation.value}${item.observation.unit ? ` ${item.observation.unit}` : ''}` : ''}</p>}
          <div className="analysis-evidence-meta">
            {item.source.page !== null && <span>Page {item.source.page}</span>}
            {item.source.fiscal_year && <span>Fiscal year {item.source.fiscal_year}</span>}
            {item.source.publisher && <span>{item.source.publisher}</span>}
            <span>Retrieved {new Date(item.provenance.retrieved_at).toLocaleDateString()}</span>
            {href && <a href={href} target="_blank" rel="noopener noreferrer">View source <ExternalLink size={13} aria-hidden="true" /></a>}
            {item.source.artifact_id && <button className="button secondary" type="button" onClick={() => void download(item.source.artifact_id!)} disabled={downloading !== null}>
              <Download size={15} aria-hidden="true" />{downloading === item.source.artifact_id ? 'Downloading…' : 'Download artifact'}
            </button>}
          </div>
        </li>
      })}
    </ol>
  </section>
}
