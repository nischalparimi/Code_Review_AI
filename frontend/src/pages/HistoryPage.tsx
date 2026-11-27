import { ArrowUpRight, Clock3, FileCode2, History, Trash2 } from 'lucide-react'
import type { AnalysisSession } from '../types'
import { formatDate } from '../utils/rules'
import { EmptyState } from '../components/ui/SeverityBadge'

export default function HistoryPage({ sessions, onOpen, onClear }: { sessions: AnalysisSession[]; onOpen: (session: AnalysisSession) => void; onClear: () => void }) {
  return <div className="page-stack"><section className="page-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> SESSION ACTIVITY</div><h2>Analysis history</h2><p>Results are held in memory for this browser session only.</p></div>{sessions.length > 0 && <button className="button-secondary danger-button" onClick={onClear}><Trash2 size={15} /> Clear session</button>}</section>
    <section className="panel history-panel">{sessions.length ? <><div className="history-head"><span>FILE</span><span>DATE</span><span>FINDINGS</span><span>QUALITY GATE</span><span /></div><div className="history-list">{sessions.map(session => <button className="history-row" key={session.id} onClick={() => onOpen(session)}><div className="history-file"><span className="file-symbol"><FileCode2 size={16} /></span><span><strong>{session.filename}</strong><small>Python source</small></span></div><span className="history-date"><Clock3 size={13} />{formatDate(session.createdAt)}</span><span className="history-findings">{session.result.total_issues} <small>{session.result.total_issues === 1 ? 'finding' : 'findings'}</small></span><span className={`history-gate ${session.result.quality_gate.passed ? 'passed' : 'failed'}`}>{session.result.quality_gate.passed ? 'Passed' : 'Failed'}</span><ArrowUpRight size={15} className="history-open" /></button>)}</div></> : <EmptyState icon={<History size={20} />} title="No session history" body="Analyze a Python file to see its actual results listed here. Nothing is stored on a server." />}</section>
    <div className="session-notice"><Clock3 size={15} /><span>Session history clears when you close or refresh this browser tab. Persistence is not configured.</span></div>
  </div>
}
