import { useState, type FormEvent } from 'react'
import { X } from 'lucide-react'
import { useApiRequest } from './use-api-request'
import { useDialog } from './use-dialog'
import type { Company } from './company-types'

export default function CompanyDialog({
  company,
  onClose,
  onSave,
}: {
  company: Company | null
  onClose: () => void
  onSave: (company: Company) => void
}) {
  const apiRequest = useApiRequest()
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
        await apiRequest<Company>(company ? `/api/companies/${company.id}` : '/api/companies', {
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
              placeholder="e.g. Reliance Industries"
              disabled={busy}
            />
          </label>
          <label className="field">
            Yahoo Finance ticker
            <input
              required
              maxLength={40}

              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder="e.g. RELIANCE.NS"
              aria-describedby={error ? "ticker-hint company-error" : "ticker-hint"}
              aria-invalid={Boolean(error)}
              disabled={busy}
            />
          </label>
          <p className="field-hint" id="ticker-hint">
            NSE equities only. Bare symbols are saved with .NS, e.g. RELIANCE.NS.
          </p>
          {error && (
            <p className="error" id="company-error" role="alert">
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

