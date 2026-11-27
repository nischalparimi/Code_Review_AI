import { useMemo } from 'react'
import { ArrowRight, ArrowUpRight, BadgeCheck, CircleAlert, Code2, FileSearch, History, ShieldAlert, TrendingUp } from 'lucide-react'
import { CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AnalysisSession, PageId } from '../types'
import { formatDate } from '../utils/rules'
import { EmptyState } from '../components/ui/SeverityBadge'

const COLORS = ['#f16e76', '#e9a84c', '#7799ff']

export default function OverviewPage({ sessions, onNavigate, onOpenSession }: { sessions: AnalysisSession[]; onNavigate: (page: PageId) => void; onOpenSession: (session: AnalysisSession) => void }) {
  const totals = useMemo(() => sessions.reduce((acc, item) => {
    acc.issues += item.result.total_issues
    acc.critical += item.result.summary.critical ?? 0
    acc.warning += item.result.summary.warning ?? 0
    acc.info += item.result.summary.info ?? 0
    return acc
  }, { issues: 0, critical: 0, warning: 0, info: 0 }), [sessions])
  const chart = [{ name: 'Critical', value: totals.critical }, { name: 'Warning', value: totals.warning }, { name: 'Info', value: totals.info }].filter(item => item.value > 0)
  const recent = sessions.slice(0, 5)
  const latestScore = sessions[0]?.result.quality_score
  const scoreHistory = sessions.slice().reverse().flatMap(session => session.result.quality_score ? [{
    label: new Date(session.createdAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    score: session.result.quality_score.score,
    filename: session.filename,
  }] : [])
  const scoreValues = scoreHistory.map(item => item.score)
  const highestScore = scoreValues.length ? Math.max(...scoreValues) : null
  const lowestScore = scoreValues.length ? Math.min(...scoreValues) : null

  return <div className="page-stack">
    <section className="welcome-row"><div><div className="eyebrow"><span className="eyebrow-line" /> DEVELOPER QUALITY WORKSPACE</div><h2>Code health, at a glance.</h2><p>Review Python code with your local AST analysis engine.</p></div><button className="button-primary" onClick={() => onNavigate('analyzer')}><Code2 size={16} /> Analyze code <ArrowRight size={15} /></button></section>
    <section className="metric-grid" aria-label="Session metrics">
      <MetricCard label="Total analyses" value={sessions.length} icon={<FileSearch size={18} />} foot={sessions.length ? 'In this browser session' : 'No session activity yet'} accent="blue" />
      <MetricCard label="Total findings" value={totals.issues} icon={<CircleAlert size={18} />} foot={sessions.length ? 'Across analyzed files' : 'Results appear here after analysis'} accent="violet" />
      <MetricCard label="Critical findings" value={totals.critical} icon={<ShieldAlert size={18} />} foot={sessions.length ? 'Across this session' : 'No findings recorded'} accent="red" />
      <MetricCard label="Latest quality score" value={latestScore ? `${latestScore.score}/100` : '—'} icon={<BadgeCheck size={18} />} foot={latestScore ? `${latestScore.grade} · ${latestScore.grade_label}` : 'No score recorded in this session'} accent="green" />
    </section>
    <section className="overview-grid">
      <div className="panel severity-panel"><div className="panel-heading"><div><h3>Severity distribution</h3><p>Findings from analyses in this session</p></div><button className="quiet-link" onClick={() => onNavigate('history')}>Session history <ArrowUpRight size={14} /></button></div>
        {chart.length ? <div className="chart-area"><div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={chart} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="88%" paddingAngle={4} stroke="none">{chart.map((entry, index) => <Cell key={entry.name} fill={COLORS[index]} />)}</Pie><Tooltip contentStyle={{ background: '#151c2a', border: '1px solid #2b3547', borderRadius: 8, color: '#ecf1fb' }} /></PieChart></ResponsiveContainer><div className="donut-center"><strong>{totals.issues}</strong><span>findings</span></div></div><div className="legend-list">{[{ label: 'Critical', value: totals.critical, color: COLORS[0] }, { label: 'Warning', value: totals.warning, color: COLORS[1] }, { label: 'Info', value: totals.info, color: COLORS[2] }].map(row => <div className="legend-row" key={row.label}><span className="legend-label"><i style={{ background: row.color }} />{row.label}</span><strong>{row.value}</strong></div>)}</div></div> : <EmptyState icon={<CircleAlert size={20} />} title="No analysis data yet" body="Severity metrics are calculated from real results in this session." action={<button className="button-secondary small" onClick={() => onNavigate('analyzer')}>Start an analysis <ArrowRight size={14} /></button>} />}
      </div>
      <div className="panel recent-panel"><div className="panel-heading"><div><h3>Recent analyses</h3><p>Only available during this session</p></div>{recent.length > 0 && <button className="icon-button subtle" onClick={() => onNavigate('history')} aria-label="View history"><ArrowUpRight size={17} /></button>}</div>
        {recent.length ? <div className="recent-list">{recent.map(item => <button key={item.id} className="recent-row" onClick={() => onOpenSession(item)}><div className="file-symbol"><Code2 size={16} /></div><div className="recent-file"><strong>{item.filename}</strong><span>{formatDate(item.createdAt)}</span></div><span className={`recent-count ${item.result.total_issues ? 'has-findings' : ''}`}>{item.result.total_issues} {item.result.total_issues === 1 ? 'finding' : 'findings'}</span><ArrowRight size={14} className="recent-arrow" /></button>)}</div> : <EmptyState icon={<History size={20} />} title="Nothing reviewed yet" body="Your recent checks will appear here. This history is not saved after the session ends." />}
      </div>
    </section>
    <section className="panel score-history-panel"><div className="panel-heading"><div><h3>Quality score history</h3><p>Scores from analyses completed in this browser session</p></div><span className="catalog-count"><TrendingUp size={14} /> Session trend</span></div>
      {scoreHistory.length >= 2 ? <><div className="score-history-stats"><span>Highest <strong>{highestScore}</strong></span><span>Lowest <strong>{lowestScore}</strong></span></div><div className="score-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={scoreHistory} margin={{ top: 10, right: 12, bottom: 2, left: -14 }}><CartesianGrid stroke="#273244" strokeDasharray="3 4" vertical={false} /><XAxis dataKey="label" tick={{ fill: '#8490a5', fontSize: 9 }} axisLine={{ stroke: '#303b4d' }} tickLine={false} /><YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tick={{ fill: '#8490a5', fontSize: 9 }} axisLine={false} tickLine={false} /><Tooltip formatter={(value: number) => [`${value}/100`, 'Score']} labelFormatter={(_, payload) => payload?.[0]?.payload?.filename ?? ''} contentStyle={{ background: '#151c2a', border: '1px solid #2b3547', borderRadius: 8, color: '#ecf1fb' }} /><Line type="monotone" dataKey="score" stroke="#84a1ff" strokeWidth={2} dot={{ r: 3, fill: '#9bb2ff', stroke: '#151c2a', strokeWidth: 2 }} activeDot={{ r: 5 }} /></LineChart></ResponsiveContainer></div></> : scoreHistory.length === 1 ? <div className="score-history-single"><div className="score-history-number">{scoreHistory[0].score}<small>/100</small></div><span>One scored analysis so far. Run another analysis to see a trend.</span><div className="score-history-stats"><span>Highest <strong>{highestScore}</strong></span><span>Lowest <strong>{lowestScore}</strong></span></div></div> : <EmptyState icon={<TrendingUp size={19} />} title="No scored analyses yet" body="Scores and trends will appear here after actual analyses are completed." action={<button className="button-secondary small" onClick={() => onNavigate('analyzer')}>Analyze code <ArrowRight size={14} /></button>} />}
    </section>
    <section className="info-strip"><div className="info-strip-icon"><ShieldAlert size={17} /></div><div><strong>Analysis runs locally through your backend</strong><span>Source is parsed by the existing Python AST rules and is not executed.</span></div><button className="quiet-link" onClick={() => onNavigate('rules')}>Explore rules <ArrowRight size={14} /></button></section>
  </div>
}

function MetricCard({ label, value, icon, foot, accent }: { label: string; value: string | number; icon: React.ReactNode; foot: string; accent: string }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon metric-${accent}`}>{icon}</span></div><div className="metric-value">{value}</div><div className="metric-foot"><span className={`metric-status ${accent}`} />{foot}</div></div>
}
