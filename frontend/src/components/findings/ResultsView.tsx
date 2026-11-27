import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, CircleAlert, Search, ShieldCheck, X } from 'lucide-react'
import type { AnalysisResult } from '../../types'
import { SeverityBadge } from '../ui/SeverityBadge'
import QualityScoreCard from '../score/QualityScoreCard'
import CodeViewer, { type CodeFinding } from '../code/CodeViewer'
import FixSuggestion from '../code/FixSuggestion'

export default function ResultsView({ result, filename, sourceCode = '', compact = false }: { result: AnalysisResult; filename: string; sourceCode?: string; compact?: boolean }) {
  const [query, setQuery] = useState('')
  const [severity, setSeverity] = useState('all')
  const [ruleId, setRuleId] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const findings = useMemo<CodeFinding[]>(() => result.files.flatMap(file => file.issues).map((issue, index) => ({
    ...issue,
    id: `${issue.file}\u0000${issue.rule_id}\u0000${issue.line}\u0000${issue.message}\u0000${index}`,
  })), [result.files])
  const ruleIds = [...new Set(findings.map(issue => issue.rule_id))].sort()
  const visible = useMemo(() => findings.filter(issue => {
    const matchesSeverity = severity === 'all' || issue.severity === severity
    const matchesRule = ruleId === 'all' || issue.rule_id === ruleId
    const text = `${issue.rule_id} ${issue.message} ${issue.file} ${issue.line}`.toLowerCase()
    return matchesSeverity && matchesRule && text.includes(query.toLowerCase())
  }).sort((a, b) => a.line - b.line), [findings, query, ruleId, severity])
  const selected = findings.find(issue => issue.id === selectedId) ?? null
  useEffect(() => { setSelectedId(null) }, [result, sourceCode])
  const parseErrors = result.files.filter(file => file.parse_error)
  const sourceLines = sourceCode.split(/\r\n|\n|\r/)
  const validLine = selected && Number.isInteger(selected.line) && selected.line > 0 && selected.line <= sourceLines.length
  const sourceLine = validLine ? sourceLines[selected!.line - 1] : undefined
  const selectFinding = (id: string) => setSelectedId(id)

  return <div className={`page-stack ${compact ? 'compact-results' : ''}`}>
    {!compact && <section className="result-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> ANALYSIS COMPLETE</div><h2>Analysis results</h2><p>Review findings for <strong>{filename}</strong></p></div><div className={`gate-banner ${result.quality_gate.passed ? 'gate-pass' : 'gate-fail'}`}>{result.quality_gate.passed ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}<div><strong>Quality gate {result.quality_gate.passed ? 'passed' : 'failed'}</strong><span>Blocking: {result.quality_gate.blocking_severities.join(', ') || 'none'}</span></div></div></section>}
    {compact && <div className={`gate-banner ${result.quality_gate.passed ? 'gate-pass' : 'gate-fail'}`}>{result.quality_gate.passed ? <CheckCircle2 size={18} /> : <CircleAlert size={18} />}<div><strong>Quality gate {result.quality_gate.passed ? 'passed' : 'failed'}</strong><span>Blocking: {result.quality_gate.blocking_severities.join(', ') || 'none'}</span></div></div>}
    <QualityScoreCard score={result.quality_score} />
    <section className="result-metrics"><ResultMetric label="Total findings" value={result.total_issues} accent="violet" /><ResultMetric label="Critical" value={result.summary.critical ?? 0} accent="red" /><ResultMetric label="Warnings" value={result.summary.warning ?? 0} accent="amber" /><ResultMetric label="Informational" value={result.summary.info ?? 0} accent="blue" /></section>
    {parseErrors.map(file => <div className="parse-error" key={file.file}><CircleAlert size={17} /><div><strong>Could not parse {file.file}</strong><span>{file.parse_error}</span></div></div>)}
    <div className="review-workspace"><section className="panel findings-panel"><div className="panel-heading findings-title"><div><h3>Findings <span className="count-pill">{visible.length}</span></h3><p>{result.files.length} {result.files.length === 1 ? 'file analyzed' : 'files analyzed'}</p></div></div>
      <div className="filter-row"><label className="search-control"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search findings…" aria-label="Search findings" /></label><select aria-label="Filter by severity" value={severity} onChange={event => setSeverity(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select><select aria-label="Filter by rule" value={ruleId} onChange={event => setRuleId(event.target.value)}><option value="all">All rules</option>{ruleIds.map(id => <option key={id}>{id}</option>)}</select></div>
      {visible.length ? <div className="table-scroll"><table className="findings-table"><thead><tr><th>Rule</th><th>Severity</th><th>File</th><th>Line</th><th>Message</th><th /></tr></thead><tbody>{visible.map(issue => <tr key={issue.id} className={selectedId === issue.id ? 'selected-finding-row' : ''} aria-selected={selectedId === issue.id} onClick={() => selectFinding(issue.id)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); selectFinding(issue.id) } }}><td><code className="rule-code">{issue.rule_id}</code></td><td><SeverityBadge severity={issue.severity} /></td><td className="table-file">{issue.file}</td><td className="line-number">{Number.isInteger(issue.line) && issue.line > 0 ? issue.line : '—'}</td><td className="issue-message">{issue.message}</td><td><span className="row-detail">Details</span></td></tr>)}</tbody></table></div> : <div className="table-empty"><div className="empty-icon"><ShieldCheck size={19} /></div><strong>{findings.length === 0 ? 'No findings in this file' : 'No matching findings'}</strong><span>{findings.length === 0 ? 'The analyzer returned a clean result.' : 'Adjust the search or filters to see more results.'}</span></div>}
    </section><CodeViewer source={sourceCode} findings={findings} selectedFindingId={selectedId} onSelectFinding={selectFinding} /></div>
    <section className="panel finding-details-panel" aria-label="Finding details">
      {selected ? <><div className="detail-header"><div><span className="eyebrow">FINDING DETAIL</span><h3>{selected.rule_id}</h3></div><button className="icon-button" aria-label="Clear selected finding" onClick={() => setSelectedId(null)}><X size={17} /></button></div>
        <div className="detail-badges"><SeverityBadge severity={selected.severity} /><span className="detail-location">{selected.file}{Number.isInteger(selected.line) && selected.line > 0 ? ` : ${selected.line}` : ' · source line unavailable'}</span></div>
        <p className="detail-message">{selected.message}</p>
        {sourceLine !== undefined ? <div className="detail-source"><strong>Source snippet · line {selected!.line}</strong><pre><code>{sourceLine || ' '}</code></pre></div> : <div className="detail-source-unavailable">A source snippet is unavailable for this finding.</div>}
        {selected.remediation && <div className="remediation-box"><strong>Analyzer remediation</strong><span>{selected.remediation}</span></div>}
        <FixSuggestion issue={selected} sourceLine={sourceLine} />
      </> : <div className="detail-empty"><span className="eyebrow">FINDING DETAIL</span><strong>Select a finding to inspect its source and guidance.</strong><span>Use the findings list or a marked source line. Findings without a valid source line still show their details.</span></div>}
    </section>
  </div>
}

function ResultMetric({ label, value, accent }: { label: string; value: number; accent: string }) { return <div className="result-metric"><span>{label}</span><strong className={`value-${accent}`}>{value}</strong></div> }
