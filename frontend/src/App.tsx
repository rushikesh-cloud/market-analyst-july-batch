import { useEffect, useState } from 'react'
import { UserButton } from '@clerk/react'
import { Building2, ChartNoAxesCombined, ChevronRight, Files, Workflow, type LucideIcon } from 'lucide-react'
import Companies from './Companies'
import Documents from './Documents'

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
          <div className="account-control"><UserButton /></div>
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
