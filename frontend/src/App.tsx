import { apiRequest } from './api-request'
import DocumentDetail from './DocumentDetail'
import { StatusBadge, formatDate } from './document-format'
import type { Report } from './document-types'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  CircleAlert,
  Eye,
  Files,
  FileText,
  Pencil,
  Plus,
  Search,
  Trash2,
  Workflow,
  X,
  type LucideIcon,
} from 'lucide-react'

type Company = { id: string; name: string; ticker: string }
type Page = 'companies' | 'documents' | 'analysis'
const pages: { id: Page; label: string; icon: LucideIcon }[] = [
  { id: 'companies', label: 'Companies', icon: Building2 },
  { id: 'documents', label: 'Documents', icon: Files },
  { id: 'analysis', label: 'Agentic Analysis', icon: Workflow },
]
function currentPage(): Page {
  const page = window.location.hash.slice(1)
  return pages.some(({ id }) => id === page) ? (page as Page) : 'companies'
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  return apiRequest<T>(`/api/companies${path}`, options)
}


export default function App() {
  const [page, setPage] = useState<Page>(currentPage)
  useEffect(() => {
    const update = () => setPage(currentPage())
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const active = pages.find(({ id }) => id === page)!
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault()
          document.getElementById('main-content')?.focus()
        }}
      >
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="#companies" aria-label="Market Analyst home">
          <span className="brand-mark">
            <ChartNoAxesCombined size={22} />
          </span>
          <span>
            Market Analyst
            <span className="brand-caption">RESEARCH WORKSPACE</span>
          </span>
        </a>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {pages.map(({ id, label, icon: Icon }) => (
            <a
              key={id}
              href={`#${id}`}
              className={`nav-link ${page === id ? 'active' : ''}`}
              aria-current={page === id ? 'page' : undefined}
              title={label}
              aria-label={label}
            >
              <Icon size={19} />
              <span>{label}</span>
              {page === id && <ChevronRight size={15} className="nav-arrow" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="workspace-avatar">MA</span>
          <div>
            Research workspace<small>Market Analyst</small>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Workspace</span>
          <ChevronRight size={14} />
          <strong>{active.label}</strong>
          <span className="workspace-label">EQUITY RESEARCH</span>
        </header>
        <main id="main-content" tabIndex={-1} className={page === 'documents' ? 'documents-main' : undefined}>
          {page === 'companies' ? (
            <Companies />
          ) : page === 'documents' ? (
            <Documents />
          ) : (
            <>
              <div className="page-heading">
                <h1>{active.label}</h1>
              </div>
              <section className="panel planned">
                <active.icon size={30} />
                <h2>{active.label}</h2>
                <p>
                  Company analysis and agent results are planned.
                </p>
                <a className="button secondary" href="#companies">
                  View companies
                  <ChevronRight size={16} />
                </a>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function Companies() {
  const [companies, setCompanies] = useState<Company[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [query, setQuery] = useState('')
  const [notice, setNotice] = useState('')
  const [editor, setEditor] = useState<Company | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Company | null>(null)
  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      setCompanies(await request<Company[]>(''))
    } catch (error) {
      setLoadError((error as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    void load()
  }, [load])
  const filtered = companies
    .filter((company) =>
      `${company.name} ${company.ticker}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
    )
    .sort((a, b) => a.name.localeCompare(b.name))
  function saved(company: Company) {
    setCompanies((previous) => [
      ...previous.filter(({ id }) => id !== company.id),
      company,
    ])
    setNotice(editor === 'new' ? 'Company added.' : 'Company updated.')
    setEditor(null)
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="section-label">COMPANY REGISTRY</div>
          <h1>Companies</h1>
          <p>Manage your research universe.</p>
        </div>
        <button
          className="button primary"
          onClick={() => {
            setNotice('')
            setEditor('new')
          }}
        >
          <Plus size={18} />
          Add company
        </button>
      </div>
      <section className="panel" aria-label="Company registry">
        <div className="table-toolbar">
          <div className="table-title">
            All companies
            <span className="count">
              {loading || loadError ? '—' : companies.length}
            </span>
          </div>
          <label className="search">
            <Search size={17} />
            <input
              type="search"
              placeholder="Search companies…"
              aria-label="Search companies"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
        </div>
        {loading ? (
          <div className="empty" role="status">
            Loading companies…
          </div>
        ) : loadError ? (
          <div className="empty">
            <p role="alert">{loadError}</p>
            <button className="button secondary" onClick={() => void load()}>
              Retry
            </button>
          </div>
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Company name</th>
                    <th scope="col">Yahoo Finance ticker</th>
                    <th scope="col" className="actions-heading">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((company) => (
                    <tr key={company.id}>
                      <td>
                        <div className="company-cell">
                          <span className="company-avatar" aria-hidden="true">
                            {company.name.slice(0, 2).toUpperCase()}
                          </span>
                          <span>{company.name}</span>
                        </div>
                      </td>
                      <td>
                        <span className="ticker">{company.ticker}</span>
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="icon-button"
                            title={`Edit ${company.name}`}
                            aria-label={`Edit ${company.name}`}
                            onClick={() => {
                              setNotice('')
                              setEditor(company)
                            }}
                          >
                            <Pencil size={17} />
                          </button>
                          <button
                            className="icon-button danger-icon"
                            title={`Delete ${company.name}`}
                            aria-label={`Delete ${company.name}`}
                            onClick={() => {
                              setNotice('')
                              setDeleting(company)
                            }}
                          >
                            <Trash2 size={17} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {filtered.length === 0 && (
              <div className="empty">
                <span className="empty-icon">
                  {query ? <Search size={25} /> : <Building2 size={27} />}
                </span>
                <h2>
                  {query
                    ? 'No matching companies'
                    : 'Build your research universe'}
                </h2>
                <p>
                  {query
                    ? 'Try another company name or ticker.'
                    : 'Add your first company to get started.'}
                </p>
                <button
                  className="button secondary"
                  onClick={() => (query ? setQuery('') : setEditor('new'))}
                >
                  {query ? (
                    'Clear search'
                  ) : (
                    <>
                      <Plus size={16} />
                      Add company
                    </>
                  )}
                </button>
              </div>
            )}
            <div className="table-footer">
              <span>
                {filtered.length}{' '}
                {filtered.length === 1 ? 'company' : 'companies'}
                {query && ` of ${companies.length}`}
              </span>
              <span>Symbol format · Yahoo Finance</span>
            </div>
          </>
        )}
      </section>
      <div className="notice" role="status">
        {notice && (
          <>
            <Check size={16} />
            {notice}
          </>
        )}
      </div>
      {editor && (
        <CompanyDialog
          company={editor === 'new' ? null : editor}
          onClose={() => setEditor(null)}
          onSave={saved}
        />
      )}
      {deleting && (
        <DeleteDialog
          company={deleting}
          onClose={() => setDeleting(null)}
          onDelete={() => {
            setCompanies((previous) =>
              previous.filter(({ id }) => id !== deleting.id),
            )
            setNotice('Company deleted.')
            setDeleting(null)
          }}
        />
      )}
    </>
  )
}

function Documents() {
  const [reports, setReports] = useState<Report[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [companyFilter, setCompanyFilter] = useState('')
  const [yearFilter, setYearFilter] = useState('')
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState<Report | null>(null)
  const [deleting, setDeleting] = useState<Report | null>(null)
  const [notice, setNotice] = useState('')
  const load = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [documents, companyList] = await Promise.all([
        apiRequest<Report[]>('/api/documents'), request<Company[]>(''),
      ])
      setReports(documents); setCompanies(companyList)
    } catch (reason) { setError((reason as Error).message) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])
  const visible = reports.filter((report) =>
    (!companyFilter || report.company_id === companyFilter) &&
    (!yearFilter || report.fiscal_year === Number(yearFilter)))
  const years = [...new Set(reports.map(({ fiscal_year }) => fiscal_year))].sort((a, b) => b - a)
  if (selected) return <DocumentDetail report={selected} onBack={() => { setSelected(null); void load() }} />
  return <div className="documents-index">
    <div className="page-heading">
      <div><div className="section-label">ANNUAL REPORTS</div><h1>Documents</h1><p>Upload and inspect company reports.</p></div>
      <button className="button primary" onClick={() => setUploading(true)} disabled={!companies.length}>
        <Plus size={18} /> Upload document
      </button>
    </div>
    <section className="panel" aria-label="Annual reports">
      <div className="table-toolbar document-toolbar">
        <div className="table-title">All documents <span className="count">{loading || error ? '—' : reports.length}</span></div>
        <div className="filters">
          <label><span className="sr-only">Filter by company</span><select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}><option value="">All companies</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label>
          <label><span className="sr-only">Filter by fiscal year</span><select value={yearFilter} onChange={(e) => setYearFilter(e.target.value)}><option value="">All years</option>{years.map((year) => <option key={year}>{year}</option>)}</select></label>
        </div>
      </div>
      {loading ? <div className="empty" role="status">Loading documents…</div> : error ? <div className="empty"><p role="alert">{error}</p><button className="button secondary" onClick={() => void load()}>Retry</button></div> : <>
        <div className="table-scroll"><table><thead><tr><th>Company</th><th>Fiscal year ending</th><th>Filename</th><th>Status</th><th>Uploaded</th><th className="actions-heading">Actions</th></tr></thead>
          <tbody>{visible.map((report) => <tr key={report.id}><td><div className="company-cell"><span className="company-avatar" aria-hidden="true">{report.company.name.slice(0, 2).toUpperCase()}</span>{report.company.name}</div></td><td>{report.fiscal_year}</td><td className="filename">{report.filename}</td><td><StatusBadge status={report.status} /></td><td>{formatDate(report.created_at)}</td><td><div className="row-actions"><button className="icon-button" aria-label={`Open ${report.filename}`} title="Open document" onClick={() => setSelected(report)}><Eye size={17} /></button><button className="icon-button danger-icon" aria-label={`Delete ${report.filename}`} title="Delete document" onClick={() => setDeleting(report)}><Trash2 size={17} /></button></div></td></tr>)}</tbody>
        </table></div>
        {!visible.length && <div className="empty"><span className="empty-icon"><FileText size={27} /></span><h2>{reports.length ? 'No matching documents' : 'No annual reports yet'}</h2><p>{reports.length ? 'Change the company or year filter.' : companies.length ? 'Upload the first annual report.' : 'Add a company before uploading a report.'}</p>{companies.length > 0 && <button className="button secondary" onClick={() => setUploading(true)}><Plus size={16} /> Upload document</button>}</div>}
        <div className="table-footer"><span>{visible.length} {visible.length === 1 ? 'document' : 'documents'}</span><span>One report per company and fiscal year</span></div>
      </>}
    </section>
    <div className="notice" role="status">{notice && <><Check size={16} />{notice}</>}</div>
    {uploading && <UploadDocumentDialog companies={companies} onClose={() => setUploading(false)} onUploaded={(report) => { setReports((items) => [report, ...items]); setUploading(false); setNotice('Document queued for ingestion.') }} />}
    {deleting && <DeleteDocumentDialog report={deleting} onClose={() => setDeleting(null)} onDeleted={() => { setReports((items) => items.filter(({ id }) => id !== deleting.id)); setDeleting(null); setNotice('Document deleted.') }} />}
  </div>
}


function UploadDocumentDialog({ companies, onClose, onUploaded }: { companies: Company[]; onClose: () => void; onUploaded: (report: Report) => void }) {
  const [companyId, setCompanyId] = useState(companies[0]?.id ?? '')
  const [year, setYear] = useState(new Date().getFullYear().toString())
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const dialog = useDialog(onClose, busy)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) { setError('Select a PDF file.'); return }
    if (file.size > 50 * 1024 * 1024) { setError('PDF exceeds the 50 MB upload limit.'); return }
    setBusy(true); setError('')
    const data = new FormData(); data.append('company_id', companyId); data.append('fiscal_year', year); data.append('file', file)
    try { onUploaded(await apiRequest<Report>('/api/documents', { method: 'POST', body: data })) }
    catch (reason) { setError((reason as Error).message); setBusy(false) }
  }
  const maximumYear = new Date().getFullYear() + 1
  return <dialog {...dialog} aria-labelledby="upload-title"><form onSubmit={submit}><div className="dialog-heading"><h2 id="upload-title">Upload annual report</h2><button type="button" className="icon-button" onClick={onClose} disabled={busy} aria-label="Close dialog"><X size={20} /></button></div><div className="dialog-body">
    <label className="field">Company<select data-initial-focus required value={companyId} onChange={(e) => setCompanyId(e.target.value)} disabled={busy}>{companies.map((company) => <option key={company.id} value={company.id}>{company.name} ({company.ticker})</option>)}</select></label>
    <label className="field">Fiscal year ending<input required type="number" min="1900" max={maximumYear} value={year} onChange={(e) => setYear(e.target.value)} disabled={busy} /></label>
    <label className="field">Annual report PDF<input required type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={busy} /></label><p className="field-hint">PDF only, up to 50 MB.</p>
    {error && <p className="error" role="alert">{error}</p>}
  </div><div className="dialog-footer"><button type="button" className="button secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="button primary" disabled={busy}>{busy ? 'Uploading…' : 'Upload and ingest'}</button></div></form></dialog>
}

function DeleteDocumentDialog({ report, onClose, onDeleted }: { report: Report; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const dialog = useDialog(onClose, busy)
  async function remove() { setBusy(true); setError(''); try { await apiRequest(`/api/documents/${report.id}`, { method: 'DELETE' }); onDeleted() } catch (reason) { setError((reason as Error).message); setBusy(false) } }
  return <dialog {...dialog} aria-labelledby="delete-document-title"><div className="dialog-heading"><h2 id="delete-document-title">Delete document?</h2><button className="icon-button" onClick={onClose} disabled={busy} aria-label="Close dialog"><X size={20} /></button></div><div className="dialog-body"><p>Delete <strong>{report.filename}</strong> for {report.company.name}, fiscal year {report.fiscal_year}? Its file, extracted content, chunks, and ingestion history will be removed.</p>{error && <p className="error" role="alert">{error}</p>}</div><div className="dialog-footer"><button data-initial-focus className="button secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="button danger" onClick={() => void remove()} disabled={busy}><Trash2 size={16} />{busy ? 'Deleting…' : 'Delete document'}</button></div></dialog>
}


function useDialog(onClose: () => void, busy: boolean) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const focused = document.activeElement as HTMLElement | null
    ref.current?.showModal()
    ref.current?.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    return () => {
      focused?.focus()
    }
  }, [])
  return {
    ref,
    onCancel: (event: React.SyntheticEvent) => {
      event.preventDefault()
      if (!busy) onClose()
    },
  }
}

function CompanyDialog({
  company,
  onClose,
  onSave,
}: {
  company: Company | null
  onClose: () => void
  onSave: (company: Company) => void
}) {
  const [name, setName] = useState(company?.name ?? '')
  const [ticker, setTicker] = useState(company?.ticker ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const dialog = useDialog(onClose, busy)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Enter a company name.')
      return
    }
    setBusy(true)
    setError('')
    try {
      onSave(
        await request<Company>(company ? `/${company.id}` : '', {
          method: company ? 'PUT' : 'POST',
          body: JSON.stringify({
            name: name.trim(),
            ticker: ticker.trim().toUpperCase(),
          }),
        }),
      )
    } catch (error) {
      setError((error as Error).message)
      setBusy(false)
    }
  }
  return (
    <dialog {...dialog} aria-labelledby="company-dialog-title">
      <form onSubmit={submit}>
        <div className="dialog-heading">
          <h2 id="company-dialog-title">
            {company ? 'Edit company' : 'Add company'}
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            disabled={busy}
            aria-label="Close dialog"
            title="Close"
          >
            <X size={20} />
          </button>
        </div>
        <div className="dialog-body">
          <label className="field">
            Company name
            <input
              data-initial-focus
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Microsoft Corporation"
              disabled={busy}
            />
          </label>
          <label className="field">
            Yahoo Finance ticker
            <input
              required
              maxLength={40}
              pattern="[A-Za-z0-9^][A-Za-z0-9.\^=\-]*"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder="e.g. MSFT"
              aria-describedby="ticker-hint"
              disabled={busy}
            />
          </label>
          <p className="field-hint" id="ticker-hint">
            Include the exchange suffix when needed, e.g. RELIANCE.NS.
          </p>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="dialog-footer">
          <button
            type="button"
            className="button secondary"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button primary" disabled={busy}>
            {busy ? 'Saving…' : company ? 'Save changes' : 'Add company'}
          </button>
        </div>
      </form>
    </dialog>
  )
}

function DeleteDialog({
  company,
  onClose,
  onDelete,
}: {
  company: Company
  onClose: () => void
  onDelete: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useDialog(onClose, busy)
  async function remove() {
    setBusy(true)
    setError('')
    try {
      await request(`/${company.id}`, { method: 'DELETE' })
      onDelete()
    } catch (error) {
      setError((error as Error).message)
      setBusy(false)
    }
  }
  return (
    <dialog
      {...dialog}
      aria-labelledby="delete-title"
      aria-describedby="delete-description"
    >
      <div className="dialog-heading">
        <h2 id="delete-title">Delete company?</h2>
        <button
          className="icon-button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close dialog"
          title="Close"
        >
          <X size={20} />
        </button>
      </div>
      <div className="dialog-body">
        <p id="delete-description">
          Remove <strong>{company.name}</strong> ({company.ticker}) from your
          company registry? This cannot be undone.
        </p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="dialog-footer">
        <button
          data-initial-focus
          className="button secondary"
          onClick={onClose}
          disabled={busy}
        >
          Cancel
        </button>
        <button
          className="button danger"
          onClick={() => void remove()}
          disabled={busy}
        >
          <Trash2 size={16} />
          {busy ? 'Deleting…' : 'Delete company'}
        </button>
      </div>
    </dialog>
  )
}

// TODO: Integrate AI chatbot.
