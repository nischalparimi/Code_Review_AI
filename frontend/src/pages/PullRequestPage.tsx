import { useMemo, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, Check, Download, ExternalLink, GitBranch, GitPullRequest, LoaderCircle, RefreshCw, Search, ShieldAlert, X } from 'lucide-react'
import { analyzeGitHubPullRequest, inspectGitHubPullRequest } from '../services/api'
import type { GitHubPRAnalysis, GitHubPRChangedFile, GitHubPRInspection, Issue } from '../types'
import { SeverityBadge } from '../components/ui/SeverityBadge'
import QualityScoreCard from '../components/score/QualityScoreCard'
import CodeViewer, { type CodeFinding } from '../components/code/CodeViewer'
import FixSuggestion from '../components/code/FixSuggestion'

interface PRFinding extends Issue { id: string; source_file: string; column?: number | null }

export function normalizePullRequestUrl(value: string): string | null {
  if (!value || value.length > 2048) return null
  try {
    const trimmed = value.trim()
    const parsed = new URL(trimmed)
    const authority = trimmed.match(/^https:\/\/([^/?#]+)/i)?.[1]
    if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || authority?.toLowerCase() !== 'github.com' || parsed.username || parsed.password || parsed.search || parsed.hash) return null
    const path = parsed.pathname.endsWith('/') ? parsed.pathname.slice(0, -1) : parsed.pathname
    if (!path.startsWith('/') || path.startsWith('//') || path.includes('%')) return null
    const parts = path.slice(1).split('/')
    if (parts.length !== 4 || parts[2] !== 'pull' || !/^[0-9]{1,10}$/.test(parts[3]) || Number(parts[3]) < 1) return null
    const [owner, repo, , number] = parts
    if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(owner)) return null
    if (!/^[A-Za-z0-9_.-]{1,100}$/.test(repo) || repo === '.' || repo === '..') return null
    return `https://github.com/${owner}/${repo}/pull/${Number(number)}`
  } catch {
    return null
  }
}

export default function PullRequestPage() {
  const [url, setUrl] = useState('')
  const [inspection, setInspection] = useState<GitHubPRInspection | null>(null)
  const [review, setReview] = useState<GitHubPRAnalysis | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(() => new Set())
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedFindingId, setSelectedFindingId] = useState<string | null>(null)
  const [severityFilter, setSeverityFilter] = useState('all')
  const [ruleFilter, setRuleFilter] = useState('all')
  const [fileFilter, setFileFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState<'inspect' | 'analyze' | null>(null)
  const busy = useRef(false)

  const allFindings = useMemo<PRFinding[]>(() => (review?.files ?? []).flatMap(file => file.issues.map((issue, index) => ({
    ...issue,
    source_file: file.filename,
    id: `${file.filename}\u0000${issue.rule_id}\u0000${issue.line}\u0000${issue.message}\u0000${index}`,
  }))), [review])
  const ruleIds = [...new Set(allFindings.map(finding => finding.rule_id))].sort()
  const visibleFindings = useMemo(() => allFindings.filter(finding => {
    const matchesSeverity = severityFilter === 'all' || finding.severity === severityFilter
    const matchesRule = ruleFilter === 'all' || finding.rule_id === ruleFilter
    const matchesFile = fileFilter === 'all' || finding.source_file === fileFilter
    const text = `${finding.rule_id} ${finding.message} ${finding.source_file} ${finding.line}`.toLowerCase()
    return matchesSeverity && matchesRule && matchesFile && text.includes(query.toLowerCase())
  }), [allFindings, fileFilter, query, ruleFilter, severityFilter])
  const selectedFinding = allFindings.find(finding => finding.id === selectedFindingId) ?? null
  const selectedSourceFile = review?.files.find(file => file.filename === selectedPath) ?? review?.files[0] ?? null
  const viewerFindings: CodeFinding[] = selectedSourceFile
    ? allFindings.filter(finding => finding.source_file === selectedSourceFile.filename).map(finding => ({ ...finding, file: finding.source_file }))
    : []
  const pythonChanges = inspection?.changed_files.filter(file => file.is_python) ?? []
  const eligibleFiles = inspection?.changed_files.filter(file => file.eligible_for_analysis) ?? []

  const resetReviewState = () => {
    setInspection(null)
    setReview(null)
    setSelectedPaths(new Set())
    setSelectedPath('')
    setSelectedFindingId(null)
    setSeverityFilter('all')
    setRuleFilter('all')
    setFileFilter('all')
    setQuery('')
  }

  const inspect = async () => {
    if (busy.current) return
    const normalized = normalizePullRequestUrl(url)
    if (!normalized) {
      resetReviewState()
      setError('Enter a GitHub pull request URL such as https://github.com/owner/repository/pull/123.')
      return
    }
    busy.current = true
    setLoading('inspect')
    setError('')
    resetReviewState()
    try {
      const result = await inspectGitHubPullRequest(normalized)
      setInspection(result)
      setUrl(normalized)
      setSelectedPaths(new Set(result.changed_files.filter(file => file.eligible_for_analysis).slice(0, result.max_analysis_files).map(file => file.filename)))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not retrieve this pull request.')
    } finally {
      busy.current = false
      setLoading(null)
    }
  }

  const analyze = async () => {
    if (busy.current || !inspection) return
    busy.current = true
    setLoading('analyze')
    setError('')
    setReview(null)
    setSelectedFindingId(null)
    try {
      const normalized = normalizePullRequestUrl(url) ?? inspection.pull_request.html_url
      const result = await analyzeGitHubPullRequest(normalized, inspection.snapshot_id, [...selectedPaths])
      setReview(result)
      setSelectedPath(result.files[0]?.filename ?? '')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Pull request analysis failed.')
    } finally {
      busy.current = false
      setLoading(null)
    }
  }

  const editUrl = (value: string) => {
    setUrl(value)
    resetReviewState()
    setError('')
  }

  const togglePath = (path: string) => {
    setSelectedPaths(current => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else if (inspection && next.size < inspection.max_analysis_files) next.add(path)
      else setError(`Select at most ${inspection?.max_analysis_files ?? 25} Python files per review.`)
      return next
    })
    setReview(null)
    setSelectedFindingId(null)
  }

  const selectVisible = () => {
    if (!inspection) return
    setSelectedPaths(new Set(eligibleFiles.slice(0, inspection.max_analysis_files).map(file => file.filename)))
    setReview(null)
    setSelectedFindingId(null)
    setError('')
  }

  const clearSelection = () => {
    setSelectedPaths(new Set())
    setReview(null)
    setSelectedFindingId(null)
  }

  const openFinding = (finding: PRFinding) => {
    setSelectedFindingId(finding.id)
    setSelectedPath(finding.source_file)
  }

  return <div className="page-stack pr-page">
    <section className="page-intro pr-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> PULL REQUEST REVIEW</div><h2>Analyze changed Python files.</h2><p>Review a pull request at its head commit with the existing AST rules. Source is analyzed statically and never executed.</p></div><span className="pr-readonly-badge"><GitPullRequest size={14} /> Read-only review</span></section>

    <section className="panel pr-url-panel" aria-label="Pull request input"><label htmlFor="pull-request-url">GitHub pull request URL</label><div className="pr-url-row"><input id="pull-request-url" value={url} onChange={event => editUrl(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void inspect() }} placeholder="https://github.com/owner/repository/pull/123" disabled={loading !== null} /><button className="button-primary" onClick={() => void inspect()} disabled={loading !== null}>{loading === 'inspect' ? <><LoaderCircle size={15} className="spin" /> Loading PR…</> : <><RefreshCw size={15} /> Load pull request</>}</button></div><span className="pr-url-hint">Public pull requests are supported. Private repository access is disabled for this public service.</span>{error && <div className="form-error pr-error" role="alert"><AlertCircle size={16} /><span>{error}</span></div>}</section>

    {loading && <div className="pr-loading" role="status"><LoaderCircle size={16} className="spin" />{loading === 'inspect' ? 'Retrieving pull request metadata and changed files…' : 'Fetching selected source at the PR head and running static analysis…'}</div>}

    {inspection && <>
      <section className="panel pr-overview-panel" aria-label="Pull request information"><div className="pr-overview-main"><div className="pr-mark"><GitPullRequest size={19} /></div><div className="pr-title-block"><div><span>{inspection.pull_request.repository_full_name}</span><b> #{inspection.pull_request.number}</b></div><h3>{inspection.pull_request.title}</h3></div><a className="pr-external-link" href={inspection.pull_request.html_url} target="_blank" rel="noopener noreferrer">Open PR <ExternalLink size={13} /></a></div><div className="pr-meta-row"><span className={`pr-state ${inspection.pull_request.state === 'open' ? 'open' : ''}`}>{inspection.pull_request.draft ? 'Draft' : titleCase(inspection.pull_request.state)}</span>{inspection.pull_request.author && <span>by <strong>{inspection.pull_request.author}</strong></span>}{inspection.pull_request.head_branch && inspection.pull_request.base_branch && <span className="pr-branch-line"><GitBranch size={13} /><strong>{inspection.pull_request.head_branch}</strong><ArrowRight size={12} /><strong>{inspection.pull_request.base_branch}</strong></span>}{inspection.pull_request.created_at && <span>Created {formatDate(inspection.pull_request.created_at)}</span>}</div><div className="pr-sha-line">Analyzing head commit <code>{inspection.pull_request.head_sha.slice(0, 12)}</code></div></section>

      <section className="panel pr-changes-panel" aria-label="Changed files"><div className="pr-panel-heading"><div><h3>Changed files</h3><p>{inspection.changed_files_total === null ? `${inspection.changed_files.length} returned` : `${inspection.changed_files_total.toLocaleString()} changed in this PR`} · {pythonChanges.length} Python path{pythonChanges.length === 1 ? '' : 's'}</p></div><span className="pr-file-limit">Max {inspection.max_analysis_files} per review</span></div>{!inspection.changed_files_complete && <div className="pr-partial-alert" role="status"><AlertCircle size={15} /><span>{inspection.limitation || 'GitHub returned an incomplete changed-file list.'}</span></div>}
        {inspection.changed_files.length === 0 ? <div className="pr-empty-files"><strong>No changed files were returned.</strong><span>Check that this pull request is accessible and has a current file list.</span></div> : <div className="pr-changed-file-list">{inspection.changed_files.map(file => <ChangedFileRow key={file.filename} file={file} checked={selectedPaths.has(file.filename)} disabled={!file.eligible_for_analysis || loading !== null} onToggle={() => togglePath(file.filename)} />)}</div>}
        {inspection.changed_files.length > 0 && <div className="pr-selection-footer"><span>{selectedPaths.size} selected for analysis</span><div><button className="quiet-link" onClick={selectVisible} disabled={!eligibleFiles.length || loading !== null}>Select eligible Python files</button><button className="quiet-link" onClick={clearSelection} disabled={!selectedPaths.size || loading !== null}>Clear selection</button><button className="button-primary small" onClick={() => void analyze()} disabled={!selectedPaths.size || loading !== null}>{loading === 'analyze' ? <><LoaderCircle size={14} className="spin" /> Analyzing…</> : <>Analyze selected <ArrowRight size={13} /></>}</button></div></div>}
      </section>
      {pythonChanges.length === 0 && inspection.changed_files_complete && <div className="pr-empty-python"><ShieldAlert size={17} /><div><strong>No Python files changed in this pull request.</strong><span>Only Python files are analyzed by this static analyzer.</span></div></div>}
    </>}

    {review && <>
      <section className="pr-review-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> REVIEW COMPLETE</div><h3>Pull request findings</h3><p>{review.analysis_coverage.complete ? 'All changed Python files were analyzed successfully.' : 'This review is partial. Check coverage, skipped files, and file-list limitations below.'}</p></div><button className="button-secondary small" onClick={() => downloadReview(review)}><Download size={14} /> Export JSON</button></section>
      {review.limitation && <div className="pr-partial-alert" role="status"><AlertCircle size={15} /><span>{review.limitation}</span></div>}
      <QualityScoreCard score={review.quality_score} />
      <section className="pr-metrics" aria-label="Pull request review metrics"><Metric label="Total findings" value={review.total_findings} /><Metric label="Critical" value={review.summary.critical ?? 0} severity="critical" /><Metric label="Warnings" value={review.summary.warning ?? 0} severity="warning" /><Metric label="Info" value={review.summary.info ?? 0} severity="info" /><Metric label="Files analyzed" value={review.analysis_coverage.analyzed_python_files} /><Metric label="Files skipped" value={review.analysis_coverage.skipped_python_files} /></section>
      <section className="panel pr-coverage-panel"><div><strong>Python file coverage</strong><span>{review.analysis_coverage.analyzed_python_files} of {review.analysis_coverage.changed_python_files} changed Python files analyzed ({review.analysis_coverage.coverage_percent}%)</span></div><div className="pr-coverage-track" role="progressbar" aria-label="Python file analysis coverage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={review.analysis_coverage.coverage_percent}><i style={{ width: `${review.analysis_coverage.coverage_percent}%` }} /></div>{!review.analysis_coverage.python_file_count_complete && <small>The changed-file list is incomplete, so this coverage is only for returned paths.</small>}{review.files.length === 0 && review.analysis_coverage.changed_python_files === 0 && <small>No Python changes were available to analyze.</small>}</section>
      <div className="pr-summary-strip"><Check size={15} /><span>{reviewSummary(review)}</span></div>
      {review.skipped_files.length > 0 && <section className="panel pr-skipped-panel"><div className="pr-panel-heading"><div><h3>Skipped or incomplete Python files</h3><p>These paths are not counted as successfully analyzed.</p></div><span className="pr-file-limit">{review.skipped_files.length}</span></div><div className="pr-skipped-list">{review.skipped_files.map(file => <div key={file.filename}><code>{file.filename}</code><span>{file.reason}</span></div>)}</div></section>}
      <section className="panel pr-findings-panel"><div className="pr-panel-heading"><div><h3>Finding list <span className="count-pill">{visibleFindings.length}</span></h3><p>Filters affect this list only; score and coverage remain based on the full review.</p></div></div><div className="pr-filter-row"><label className="search-control"><Search size={14} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search findings" aria-label="Search PR findings" /></label><select aria-label="Filter PR findings by severity" value={severityFilter} onChange={event => setSeverityFilter(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select><select aria-label="Filter PR findings by rule" value={ruleFilter} onChange={event => setRuleFilter(event.target.value)}><option value="all">All rules</option>{ruleIds.map(rule => <option key={rule} value={rule}>{rule}</option>)}</select><select aria-label="Filter PR findings by file path" value={fileFilter} onChange={event => setFileFilter(event.target.value)}><option value="all">All files</option>{review.files.map(file => <option key={file.filename} value={file.filename}>{file.filename}</option>)}</select></div>
        {visibleFindings.length ? <div className="pr-findings-list">{visibleFindings.map(finding => <button key={finding.id} className={`pr-finding-row ${selectedFindingId === finding.id ? 'active' : ''}`} onClick={() => openFinding(finding)}><code>{finding.rule_id}</code><SeverityBadge severity={finding.severity} /><span className="pr-finding-copy"><strong>{finding.message}</strong><small>{finding.source_file}:{Number.isInteger(finding.line) && finding.line > 0 ? finding.line : 'line unavailable'}</small></span><ArrowRight size={14} /></button>)}</div> : <div className="pr-no-findings">{allFindings.length ? 'No findings match these filters.' : 'No findings were returned for the analyzed source.'}</div>}
      </section>

      <div className="pr-review-workspace"><section className="panel pr-file-tabs" aria-label="Analyzed file navigation"><div className="pr-panel-heading"><div><h3>Analyzed Python files</h3><p>Select a file to inspect its source and findings.</p></div></div>{review.files.length ? review.files.map(file => <button key={file.filename} className={`pr-file-tab ${selectedSourceFile?.filename === file.filename ? 'active' : ''}`} onClick={() => { setSelectedPath(file.filename); setSelectedFindingId(null) }}><span className="pr-file-tab-status">{file.parse_error ? '!' : '✓'}</span><code>{file.filename}</code><small>{file.issues.length} {file.issues.length === 1 ? 'finding' : 'findings'}</small></button>) : <div className="pr-no-analyzed-files">No source file was successfully retrieved for display.</div>}</section>
        {selectedSourceFile && <CodeViewer source={selectedSourceFile.source_code} findings={viewerFindings} selectedFindingId={selectedFindingId} onSelectFinding={id => { setSelectedFindingId(id); const match = viewerFindings.find(item => item.id === id); if (match) setSelectedPath(match.file) }} />}
      </div>
      <section className="panel pr-detail-panel" aria-label="Pull request finding details">{selectedFinding ? <><div className="pr-detail-title"><div><span className="eyebrow">FINDING DETAIL</span><h3>{selectedFinding.rule_id}</h3></div><button className="icon-button" aria-label="Clear selected PR finding" onClick={() => setSelectedFindingId(null)}><X size={17} /></button></div><div className="detail-badges"><SeverityBadge severity={selectedFinding.severity} /><span className="detail-location">{selectedFinding.source_file}{Number.isInteger(selectedFinding.line) && selectedFinding.line > 0 ? ` : ${selectedFinding.line}` : ' · source line unavailable'}</span></div><p className="detail-message">{selectedFinding.message}</p>{selectedSourceFile && selectedFinding.line > 0 && selectedFinding.line <= selectedSourceFile.source_code.split(/\r\n|\n|\r/).length && <div className="detail-source"><strong>Source snippet · line {selectedFinding.line}</strong><pre><code>{selectedSourceFile.source_code.split(/\r\n|\n|\r/)[selectedFinding.line - 1] || ' '}</code></pre></div>}{selectedFinding.remediation && <div className="remediation-box"><strong>Analyzer remediation</strong><span>{selectedFinding.remediation}</span></div>}<FixSuggestion issue={selectedFinding} sourceLine={selectedSourceFile?.source_code.split(/\r\n|\n|\r/)[selectedFinding.line - 1]} /></> : <div className="pr-detail-empty"><span className="eyebrow">FINDING DETAIL</span><strong>Select a finding to inspect its source and remediation guidance.</strong></div>}</section>
    </>}
  </div>
}

function ChangedFileRow({ file, checked, disabled, onToggle }: { file: GitHubPRChangedFile; checked: boolean; disabled: boolean; onToggle: () => void }) {
  return <label className={`pr-changed-file ${!file.is_python ? 'unsupported' : ''} ${file.status === 'removed' ? 'removed' : ''}`}><input type="checkbox" aria-label={`Select PR file ${file.filename}`} checked={checked} disabled={disabled} onChange={onToggle} /><span className={`pr-change-status status-${file.status}`}>{titleCase(file.status)}</span><code>{file.filename}</code><span className="pr-extension">{file.extension ? `.${file.extension}` : 'no extension'}</span><span className="pr-change-stats"><i>+{file.additions}</i><b>−{file.deletions}</b></span>{file.previous_filename && <small>from {file.previous_filename}</small>}{!file.is_python && <small className="pr-unsupported-note">Not a Python file</small>}{file.status === 'removed' && file.is_python && <small className="pr-unsupported-note">Removed · no PR head source</small>}{file.is_python && !file.eligible_for_analysis && file.status !== 'removed' && <small className="pr-unsupported-note">Unsupported path or change status</small>}</label>
}

function Metric({ label, value, severity }: { label: string; value: number; severity?: string }) {
  return <div className="pr-metric"><span>{label}</span><strong className={severity ? `pr-metric-${severity}` : ''}>{value}</strong></div>
}

function titleCase(value: string) { return value ? `${value[0].toUpperCase()}${value.slice(1)}` : 'Unknown' }
function formatDate(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) }

function reviewSummary(review: GitHubPRAnalysis) {
  const critical = review.summary.critical ?? 0
  const warnings = review.summary.warning ?? 0
  const files = review.analysis_coverage.analyzed_python_files
  if (!critical) return `No critical findings were detected in the ${files} Python file${files === 1 ? '' : 's'} successfully analyzed.`
  return `The PR contains ${critical} critical finding${critical === 1 ? '' : 's'}${warnings ? ` and ${warnings} warning${warnings === 1 ? '' : 's'}` : ''} in the analyzed files.`
}

function downloadReview(review: GitHubPRAnalysis) {
  const exported = {
    pull_request: review.pull_request,
    changed_files: review.changed_files,
    selected_files: review.selected_files,
    skipped_files: review.skipped_files,
    files: review.files.map(({ source_code: _sourceCode, ...file }) => file),
    summary: review.summary,
    total_findings: review.total_findings,
    quality_score: review.quality_score,
    analysis_coverage: review.analysis_coverage,
    changed_files_complete: review.changed_files_complete,
    limitation: review.limitation,
    analyzed_at: review.analyzed_at,
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `pr-${review.pull_request.number}-code-review.json`
  anchor.click()
  URL.revokeObjectURL(url)
}
