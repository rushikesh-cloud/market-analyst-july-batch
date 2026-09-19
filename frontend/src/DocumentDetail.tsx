import {
  Children,
  useCallback,
  useEffect,
  useState,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  LoaderCircle,
} from 'lucide-react'
import { apiRequest } from './api-request'
import { StatusBadge, formatDate } from './document-format'
import type {
  Report,
  ReportStatus,
  Chunk,
  MarkdownPage,
} from './document-types'
import ChunkCard from './ChunkCard'
import DocumentSearch from './DocumentSearch'

function cleanTableWhitespace(markdown: string) {
  return markdown.replace(/<table\b[\s\S]*?<\/table>/gi, (table) =>
    table.replace(/>\s+</g, '><'),
  )
}
function withoutTableText(children: ReactNode) {
  return Children.toArray(children).filter((child) => typeof child !== 'string')
}
function SafeTable({ children, ...props }: ComponentPropsWithoutRef<'table'>) {
  return <table {...props}>{withoutTableText(children)}</table>
}
function SafeTableHead({
  children,
  ...props
}: ComponentPropsWithoutRef<'thead'>) {
  return <thead {...props}>{withoutTableText(children)}</thead>
}
function SafeTableBody({
  children,
  ...props
}: ComponentPropsWithoutRef<'tbody'>) {
  return <tbody {...props}>{withoutTableText(children)}</tbody>
}
function SafeTableRow({ children, ...props }: ComponentPropsWithoutRef<'tr'>) {
  return <tr {...props}>{withoutTableText(children)}</tr>
}
const markdownComponents = {
  table: SafeTable,
  thead: SafeTableHead,
  tbody: SafeTableBody,
  tfoot: SafeTableBody,
  tr: SafeTableRow,
}

export default function DocumentDetail({
  report,
  onBack,
}: {
  report: Report
  onBack: () => void
}) {
  const [tab, setTab] = useState<'status' | 'content' | 'search'>('status')
  const [status, setStatus] = useState<ReportStatus | null>(null)
  const [markdown, setMarkdown] = useState('')
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [pollKey, setPollKey] = useState(0)
  const [page, setPage] = useState(1)
  const [pageCount, setPageCount] = useState(1)
  const [pageInput, setPageInput] = useState('1')
  const [contentLoading, setContentLoading] = useState(false)
  const loadStatus = useCallback(async () => {
    try {
      const value = await apiRequest<ReportStatus>(
        `/api/documents/${report.id}/status`,
      )
      setStatus(value)
      setError('')
      return value
    } catch (reason) {
      setError((reason as Error).message)
      return null
    }
  }, [report.id])
  useEffect(() => {
    let cancelled = false
    let timer = 0
    let delay = 3000
    const poll = async () => {
      const value = await loadStatus()
      if (cancelled) return
      if (!value) {
        delay = Math.min(delay * 2, 30000)
        timer = window.setTimeout(poll, delay)
        return
      }
      if (['complete', 'failed'].includes(value.status)) return
      delay = 3000
      timer = window.setTimeout(poll, delay)
    }
    void poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [loadStatus, pollKey])
  const contentAvailable =
    status?.stages.some(
      ({ name, status: stageStatus }) =>
        name === 'parse' && stageStatus === 'complete',
    ) ?? false
  useEffect(() => {
    if (contentAvailable)
      setTab((current) => (current === 'status' ? 'content' : current))
  }, [contentAvailable])
  useEffect(() => {
    if (tab !== 'content' || !contentAvailable) return
    let cancelled = false
    setContentLoading(true)
    Promise.all([
      apiRequest<MarkdownPage>(
        `/api/documents/${report.id}/content?page=${page}`,
      ),
      apiRequest<{ items: Chunk[] }>(
        `/api/documents/${report.id}/chunks?page=${page}&limit=500`,
      ),
    ])
      .then(([content, chunkPage]) => {
        if (cancelled) return
        setMarkdown(content.markdown)
        setPageCount(content.page_count)
        setChunks(chunkPage.items)
        setError('')
      })
      .catch((reason) => {
        if (!cancelled) setError((reason as Error).message)
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [tab, contentAvailable, page, report.id, status?.status])
  useEffect(() => {
    setPageInput(String(page))
  }, [page])
  function goToPage(value: number) {
    setPage(Math.min(Math.max(value, 1), pageCount))
  }
  function applyPageInput() {
    const value = Number(pageInput)
    if (Number.isInteger(value)) goToPage(value)
    else setPageInput(String(page))
  }
  async function retry() {
    setRetrying(true)
    try {
      await apiRequest(`/api/documents/${report.id}/retry`, { method: 'POST' })
      await loadStatus()
      setPollKey((value) => value + 1)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setRetrying(false)
    }
  }
  return (
    <div className="document-detail">
      <header className="document-detail-header">
        <button className="back-button" onClick={onBack}>
          ‹ Back to documents
        </button>
        <div className="document-title-row">
          <div>
            <div className="section-label">
              {report.company.name.toUpperCase()} · {report.fiscal_year}
            </div>
            <h1>{report.filename}</h1>
            <p>
              Ingestion attempt {status?.attempt ?? '—'} ·{' '}
              <StatusBadge status={status?.status ?? report.status} />
            </p>
          </div>
          {status?.status === 'failed' && (
            <button
              className="button primary"
              onClick={() => void retry()}
              disabled={retrying}
            >
              {retrying ? 'Queuing…' : 'Retry ingestion'}
            </button>
          )}
        </div>
        <div
          className="tabs"
          role="tablist"
          aria-label="Document views"
          onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key))
              return
            const tabs = Array.from(
              event.currentTarget.querySelectorAll<HTMLButtonElement>(
                '[role="tab"]:not(:disabled)',
              ),
            )
            const index = tabs.indexOf(
              document.activeElement as HTMLButtonElement,
            )
            const next =
              event.key === 'Home'
                ? 0
                : event.key === 'End'
                  ? tabs.length - 1
                  : (index +
                      (event.key === 'ArrowRight' ? 1 : -1) +
                      tabs.length) %
                    tabs.length
            event.preventDefault()
            tabs[next].focus()
            tabs[next].click()
          }}
        >
          {(['status', 'content', 'search'] as const).map((view) => (
            <button
              key={view}
              id={`document-tab-${view}`}
              role="tab"
              aria-controls={`document-panel-${view}`}
              aria-selected={tab === view}
              tabIndex={tab === view ? 0 : -1}
              onClick={() => setTab(view)}
              disabled={view === 'content' && !contentAvailable}
            >
              {view[0].toUpperCase() + view.slice(1)}
            </button>
          ))}
        </div>
      </header>
      {error && (
        <p className="error panel-error" role="alert">
          {error}
        </p>
      )}
      {tab === 'search' ? (
        <DocumentSearch
          key={report.id}
          documentId={report.id}
          ready={status?.status === 'complete'}
        />
      ) : tab === 'status' ? (
        <section
          className="status-panel"
          id="document-panel-status"
          role="tabpanel"
          aria-labelledby="document-tab-status"
        >
          <ol className="pipeline">
            {status?.stages.map((stage) => (
              <li key={stage.name} className={`pipeline-stage ${stage.status}`}>
                <span className="stage-icon">
                  {stage.status === 'complete' ? (
                    <Check size={16} />
                  ) : stage.status === 'failed' ? (
                    <CircleAlert size={16} />
                  ) : stage.status === 'processing' ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Clock3 size={16} />
                  )}
                </span>
                <div>
                  <strong>
                    {stage.name[0].toUpperCase() + stage.name.slice(1)}
                  </strong>
                  <small>
                    {stage.completed_items !== null
                      ? `${stage.completed_items} of ${stage.total_items} items`
                      : stage.started_at
                        ? `Started ${formatDate(stage.started_at)}`
                        : 'Waiting'}
                  </small>
                  {stage.error && <p className="error">{stage.error}</p>}
                </div>
              </li>
            )) ?? <li className="empty">Loading pipeline…</li>}
          </ol>
          {status?.error && (
            <div className="pipeline-error">
              <CircleAlert size={18} />
              <div>
                <strong>Ingestion failed</strong>
                <p>{status.error}</p>
              </div>
            </div>
          )}
        </section>
      ) : (
        <section
          className="content-split"
          id="document-panel-content"
          role="tabpanel"
          aria-labelledby="document-tab-content"
        >
          <article className="content-pane">
            <header>
              <strong>Extracted Markdown</strong>
              <span>
                Page {page} of {pageCount}
              </span>
            </header>
            <div className="markdown-view">
              {contentLoading ? (
                <div className="pane-loading" role="status">
                  Loading page…
                </div>
              ) : (
                <ReactMarkdown
                  rehypePlugins={[rehypeRaw, rehypeSanitize]}
                  components={markdownComponents}
                >
                  {cleanTableWhitespace(markdown)}
                </ReactMarkdown>
              )}
            </div>
            <footer className="page-controls">
              <button
                className="icon-button"
                aria-label="Previous page"
                title="Previous page"
                disabled={page <= 1}
                onClick={() => goToPage(page - 1)}
              >
                <ChevronLeft size={18} />
              </button>
              <label>
                <span className="sr-only">Page number</span>
                <input
                  type="number"
                  min="1"
                  max={pageCount}
                  value={pageInput}
                  onChange={(event) => setPageInput(event.target.value)}
                  onBlur={applyPageInput}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') applyPageInput()
                  }}
                />
              </label>
              <span>of {pageCount}</span>
              <button
                className="icon-button"
                aria-label="Next page"
                title="Next page"
                disabled={page >= pageCount}
                onClick={() => goToPage(page + 1)}
              >
                <ChevronRight size={18} />
              </button>
            </footer>
          </article>
          <aside className="chunks-pane">
            <header>
              <strong>Page chunks</strong>
              <span>
                {chunks.length} on page {page}
              </span>
            </header>
            <div className="chunk-list">
              {chunks.length ? (
                chunks.map((chunk) => (
                  <ChunkCard key={chunk.id} chunk={chunk} />
                ))
              ) : (
                <div className="pane-loading">
                  {status?.stages.some(
                    ({ name, status: stageStatus }) =>
                      name === 'chunk' && stageStatus === 'complete',
                  )
                    ? 'No chunks on this page.'
                    : 'Chunks will appear when chunking reaches this page.'}
                </div>
              )}
            </div>
          </aside>
        </section>
      )}
    </div>
  )
}
