import { useState } from 'react'
import {
  Activity, ArrowUpRight, BookOpen, ChevronLeft, Code2, Github,
  FileBarChart2, GitPullRequest, History, LayoutDashboard, Menu, Settings2, ShieldCheck, X,
} from 'lucide-react'
import type { PageId } from '../../types'

const navigation: { id: PageId; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'analyzer', label: 'Code Analyzer', icon: Code2 },
  { id: 'history', label: 'Analysis History', icon: History },
  { id: 'rules', label: 'Rules', icon: ShieldCheck },
  { id: 'reports', label: 'Reports', icon: FileBarChart2 },
  { id: 'github', label: 'GitHub', icon: Github },
  { id: 'pull-request', label: 'Pull Request Review', icon: GitPullRequest },
  { id: 'settings', label: 'Settings', icon: Settings2 },
]

interface Props {
  page: PageId
  title: string
  connected: boolean | null
  onNavigate: (page: PageId) => void
  children: React.ReactNode
}

export function AppShell({ page, title, connected, onNavigate, children }: Props) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const navigate = (target: PageId) => { onNavigate(target); setMobileOpen(false) }

  return <div className="app-shell">
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={`sidebar ${mobileOpen ? 'sidebar-open' : ''}`}>
      <div className="brand-row">
        <div className="brand-mark"><Code2 size={19} strokeWidth={2.4} /></div>
        <div className="brand-copy"><span>CodeReview</span><b>AI</b><small>STATIC ANALYSIS</small></div>
        <button className="icon-button mobile-close" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X size={18} /></button>
      </div>
      <div className="workspace-label">WORKSPACE <ChevronLeft size={13} /></div>
      <nav className="side-nav" aria-label="Main navigation">
        {navigation.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${page === id ? 'active' : ''}`} onClick={() => navigate(id)}>
          <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{id === 'analyzer' && <span className="nav-live-dot" />}
        </button>)}
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-note">
        <div className="note-icon"><Activity size={15} /></div>
        <div><strong>Local analysis</strong><span>Source stays on this machine</span></div>
      </div>
      <div className="sidebar-profile"><div className="profile-avatar">CR</div><div className="profile-text"><strong>Developer workspace</strong><span>Session only</span></div><ArrowUpRight size={15} className="profile-arrow" /></div>
    </aside>

    <div className="main-frame">
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu size={19} /></button>
        <div className="top-title"><div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{title}</strong></div><h1>{title}</h1></div>
        <div className="top-actions"><div className={`connection-chip ${connected === true ? 'is-online' : connected === false ? 'is-offline' : ''}`}><span className="connection-dot" />{connected === true ? 'Backend connected' : connected === false ? 'Backend offline' : 'Checking backend'}</div><div className="top-avatar">CR</div></div>
      </header>
      <main className="page-content">{children}</main>
      <footer className="app-footer"><span><BookOpen size={13} /> Python AST analyzer</span><span>Local workspace <i /> No persistent storage</span></footer>
    </div>
  </div>
}
