import { useEffect, useRef, useState, type FormEvent } from 'react'
import { CircleAlert, LoaderCircle, Search } from 'lucide-react'
import { apiRequest } from './api-request'
import ChunkCard from './ChunkCard'
import type { Chunk } from './document-types'

type SearchResults = {
  query: string
  k: number
  max_tokens: number
  total_tokens: number
  budget_limited: boolean
  items: (Chunk & {
    score: number
    semantic_rank: number | null
    text_rank: number | null
  })[]
}

export default function DocumentSearch({
  documentId,
  ready,
}: {
  documentId: string
  ready: boolean
}) {
  const [query, setQuery] = useState('')
  const [k, setK] = useState('10')
  const [tokens, setTokens] = useState('10000')
  const [results, setResults] = useState<SearchResults | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const activeRequest = useRef<AbortController | null>(null)
  useEffect(() => () => activeRequest.current?.abort(), [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!query.trim()) {
      setError('Enter a search query.')
      return
    }
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setBusy(true)
    setError('')
    setResults(null)
    try {
      const response = await apiRequest<SearchResults>(
        `/api/documents/${documentId}/search`,
        {
          method: 'POST',
          body: JSON.stringify({
            query: query.trim(),
            k: Number(k),
            max_tokens: Number(tokens),
          }),
          signal: controller.signal,
        },
      )
      if (!controller.signal.aborted) setResults(response)
    } catch (reason) {
      if (!controller.signal.aborted) setError((reason as Error).message)
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }

  return (
    <section
      className="document-search"
      id="document-panel-search"
      role="tabpanel"
      aria-labelledby="document-tab-search"
    >
      <form
        className="chunk-search-form"
        onSubmit={(event) => void submit(event)}
      >
        <label className="field query-field">
          Query
          <input
            type="search"
            required
            maxLength={2000}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. Revenue growth and outlook"
            disabled={busy}
          />
        </label>
        <label className="field">
          Chunks (K)
          <input
            type="number"
            required
            min={1}
            max={100}
            step={1}
            value={k}
            onChange={(event) => setK(event.target.value)}
            disabled={busy}
          />
        </label>
        <label className="field">
          Token budget
          <input
            type="number"
            required
            min={1}
            max={100000}
            step={1}
            value={tokens}
            onChange={(event) => setTokens(event.target.value)}
            aria-describedby="search-budget-hint"
            disabled={busy}
          />
        </label>
        <button className="button primary" disabled={busy || !ready}>
          {busy ? (
            <LoaderCircle size={18} className="spin" />
          ) : (
            <Search size={18} />
          )}
          {busy ? 'Searching…' : error ? 'Retry search' : 'Search'}
        </button>
        <p id="search-budget-hint" className="field-hint">
          Up to {k || '10'} matching chunks, within the total token budget.
          Whole chunks include heading and overlap tokens.
        </p>
      </form>
      <div className="search-results" aria-busy={busy}>
        {!ready ? (
          <div className="empty" role="status">
            <h2>Search is not ready yet</h2>
            <p>
              Search becomes available when document ingestion completes. Check
              the Status tab for progress.
            </p>
          </div>
        ) : busy ? (
          <div className="empty" role="status">
            Finding matching chunks…
          </div>
        ) : error ? (
          <div className="empty">
            <CircleAlert size={24} />
            <p role="alert">{error}</p>
            <p>Use Retry search above to try again.</p>
          </div>
        ) : results ? (
          <>
            <div className="search-summary" role="status">
              <h2>
                {results.items.length} matching{' '}
                {results.items.length === 1 ? 'chunk' : 'chunks'}
              </h2>
              <p>
                “{results.query}” · {results.total_tokens.toLocaleString()} /{' '}
                {results.max_tokens.toLocaleString()} tokens · Up to {results.k}{' '}
                chunks
              </p>
              {results.budget_limited && (
                <p>
                  Some chunks exceed the remaining token budget. Increase it to
                  include more results.
                </p>
              )}
            </div>
            {results.items.length ? (
              <ol className="search-match-list">
                {results.items.map((chunk, index) => (
                  <li key={chunk.id}>
                    <h3 className="match-rank">Match {index + 1}</h3>
                    <ChunkCard chunk={chunk} />
                  </li>
                ))}
              </ol>
            ) : (
              <div className="empty">
                <h2>No chunks returned</h2>
                <p>
                  {results.budget_limited
                    ? 'Increase the token budget and search again.'
                    : 'Try another query or check the document content.'}
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="empty">
            <Search size={28} />
            <h2>Search this document</h2>
            <p>Enter a query to find matching chunks across all pages.</p>
          </div>
        )}
      </div>
    </section>
  )
}
