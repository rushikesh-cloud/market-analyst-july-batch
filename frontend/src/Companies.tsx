import { useCallback, useEffect, useState } from 'react'
import { Building2, Check, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import { useApiRequest } from './use-api-request'
import { useDialog } from './use-dialog'
import type { Company } from './company-types'
import CompanyDialog from './CompanyDialog'

export default function Companies() {
  const apiRequest = useApiRequest()
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
      setCompanies(await apiRequest<Company[]>('/api/companies'))
    } catch (error) {
      setLoadError((error as Error).message)
    } finally {
      setLoading(false)
    }
  }, [apiRequest])
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

function DeleteDialog({
  company,
  onClose,
  onDelete,
}: {
  company: Company
  onClose: () => void
  onDelete: () => void
}) {
  const apiRequest = useApiRequest()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dialog = useDialog(onClose, busy)
  async function remove() {
    setBusy(true)
    setError('')
    try {
      await apiRequest(`/api/companies/${company.id}`, { method: 'DELETE' })
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
