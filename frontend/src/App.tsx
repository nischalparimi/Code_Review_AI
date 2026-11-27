import { lazy, Suspense, useEffect, useState } from 'react'
import { AppShell } from './components/layout/AppShell'
import { checkHealth } from './services/api'
import type { AnalysisResult, AnalysisSession, PageId } from './types'

const OverviewPage = lazy(() => import('./pages/OverviewPage'))
const AnalyzerPage = lazy(() => import('./pages/AnalyzerPage'))
const HistoryPage = lazy(() => import('./pages/HistoryPage'))
const RulesPage = lazy(() => import('./pages/RulesPage'))
const ReportsPage = lazy(() => import('./pages/ReportsPage'))
const GitHubPage = lazy(() => import('./pages/GitHubPage'))
const PullRequestPage = lazy(() => import('./pages/PullRequestPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))

const pageTitles: Record<PageId, string> = {
  overview: 'Overview', analyzer: 'Code Analyzer', history: 'Analysis History', rules: 'Rules', reports: 'Reports', github: 'GitHub Repository', 'pull-request': 'Pull Request Review', settings: 'Settings',
}

export default function App() {
  const [page, setPage] = useState<PageId>('overview')
  const [sessions, setSessions] = useState<AnalysisSession[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [connected, setConnected] = useState<boolean | null>(null)

  useEffect(() => { void checkHealth().then(() => setConnected(true)).catch(() => setConnected(false)) }, [])
  const selectedSession = sessions.find(item => item.id === selectedId) ?? null
  const addAnalysis = (filename: string, result: AnalysisResult, sourceCode: string) => {
    const session: AnalysisSession = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, filename, createdAt: new Date().toISOString(), result, source_code: sourceCode }
    setSessions(current => [session, ...current])
    setSelectedId(session.id)
  }
  const openSession = (session: AnalysisSession) => { setSelectedId(session.id); setPage('analyzer') }
  const clearHistory = () => { setSessions([]); setSelectedId(null) }
  const renderPage = () => {
    switch (page) {
      case 'overview': return <OverviewPage sessions={sessions} onNavigate={setPage} onOpenSession={openSession} />
      case 'analyzer': return <AnalyzerPage session={selectedSession} onAnalyzed={addAnalysis} onNewAnalysis={() => setSelectedId(null)} />
      case 'history': return <HistoryPage sessions={sessions} onOpen={openSession} onClear={clearHistory} />
      case 'rules': return <RulesPage />
      case 'reports': return <ReportsPage sessions={sessions} />
      case 'github': return <GitHubPage />
      case 'pull-request': return <PullRequestPage />
      case 'settings': return <SettingsPage connected={connected} />
    }
  }
  return <AppShell page={page} title={pageTitles[page]} connected={connected} onNavigate={setPage}><Suspense fallback={<div className="loading-state page-loading">Loading workspace…</div>}>{renderPage()}</Suspense></AppShell>
}
