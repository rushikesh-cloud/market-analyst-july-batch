import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Check, Eye, FileText, Plus, Trash2, X } from 'lucide-react'
import DocumentDetail from './DocumentDetail'
import { StatusBadge, formatDate } from './document-format'
import { useApiRequest } from './use-api-request'
import { useDialog } from './use-dialog'
import type { Report } from './document-types'
import type { Company } from './company-types'

export default function Documents() {
  const apiRequest = useApiRequest()
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
        apiRequest<Report[]>('/api/documents'), apiRequest<Company[]>('/api/companies'),
      ])
      setReports(documents); setCompanies(companyList)
    } catch (reason) { setError((reason as Error).message) }
    finally { setLoading(false) }
  }, [apiRequest])
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
  const apiRequest = useApiRequest()
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
  const apiRequest = useApiRequest()
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const dialog = useDialog(onClose, busy)
  async function remove() { setBusy(true); setError(''); try { await apiRequest(`/api/documents/${report.id}`, { method: 'DELETE' }); onDeleted() } catch (reason) { setError((reason as Error).message); setBusy(false) } }
  return <dialog {...dialog} aria-labelledby="delete-document-title"><div className="dialog-heading"><h2 id="delete-document-title">Delete document?</h2><button className="icon-button" onClick={onClose} disabled={busy} aria-label="Close dialog"><X size={20} /></button></div><div className="dialog-body"><p>Delete <strong>{report.filename}</strong> for {report.company.name}, fiscal year {report.fiscal_year}? Its file, extracted content, chunks, and ingestion history will be removed.</p>{error && <p className="error" role="alert">{error}</p>}</div><div className="dialog-footer"><button data-initial-focus className="button secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="button danger" onClick={() => void remove()} disabled={busy}><Trash2 size={16} />{busy ? 'Deleting…' : 'Delete document'}</button></div></dialog>
}
