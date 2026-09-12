import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  Building2,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  Files,
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
  let response: Response
  try {
    response = await fetch(`/api/companies${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options?.headers },
    })
  } catch {
    throw new Error('Unable to connect. Please try again.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : 'Unable to save changes. Check the fields and try again.',
    )
  }
  return response.status === 204 ? (undefined as T) : response.json()
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
        <main id="main-content" tabIndex={-1}>
          {page === 'companies' ? (
            <Companies />
          ) : (
            <>
              <div className="page-heading">
                <h1>{active.label}</h1>
              </div>
              <section className="panel planned">
                <active.icon size={30} />
                <h2>{active.label}</h2>
                <p>
                  {page === 'documents'
                    ? 'Company reports and document ingestion are planned.'
                    : 'Company analysis and agent results are planned.'}
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
