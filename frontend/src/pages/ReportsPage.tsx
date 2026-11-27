import { Download, FileJson2, FileSpreadsheet, FileText } from 'lucide-react'
import type { AnalysisSession } from '../types'
import { EmptyState } from '../components/ui/SeverityBadge'

function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000)
}

export default function ReportsPage({ sessions }: { sessions: AnalysisSession[] }) {
  const latest = sessions[0]
  const exportJson = () => latest && download(`${latest.filename.replace(/\.py$/i, '')}-analysis.json`, JSON.stringify(latest.result, null, 2), 'application/json')
  const exportCsv = () => {
    if (!latest) return
    const findings = latest.result.files.flatMap(file => file.issues)
    const quote = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`
    const rows = [['Rule ID', 'Severity', 'File', 'Line', 'Message', 'Remediation'], ...findings.map(issue => [issue.rule_id, issue.severity, issue.file, issue.line, issue.message, issue.remediation ?? ''])]
    download(`${latest.filename.replace(/\.py$/i, '')}-findings.csv`, rows.map(row => row.map(quote).join(',')).join('\r\n'), 'text/csv;charset=utf-8')
  }

  return <div className="page-stack"><section className="page-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> EXPORT CENTER</div><h2>Reports</h2><p>Download machine-readable reports from real analysis results.</p></div></section>
    {latest ? <><div className="report-current"><div className="report-current-icon"><FileText size={19} /></div><div><span className="eyebrow">LATEST ANALYSIS</span><strong>{latest.filename}</strong><small>{latest.result.total_issues} findings · {new Date(latest.createdAt).toLocaleString()}</small></div><span className={`history-gate ${latest.result.quality_gate.passed ? 'passed' : 'failed'}`}>{latest.result.quality_gate.passed ? 'Gate passed' : 'Gate failed'}</span></div>
      <div className="report-export-grid"><ExportCard icon={<FileJson2 size={20} />} title="JSON report" description="Full backend response including summary, file results, parse errors, and quality gate." button="Download JSON" onClick={exportJson} /><ExportCard icon={<FileSpreadsheet size={20} />} title="Findings CSV" description="Spreadsheet-ready list of findings with rule, severity, filename, line, and message." button="Download CSV" onClick={exportCsv} /></div>
      <p className="report-disclaimer">Exports include only the latest analysis held in this session. No PDF report is provided by the backend.</p>
    </> : <section className="panel report-empty"><EmptyState icon={<FileBarIcon />} title="No report to export" body="Run an analysis first. Reports are created from actual backend responses and stay in session memory." /></section>}
  </div>
}

function ExportCard({ icon, title, description, button, onClick }: { icon: React.ReactNode; title: string; description: string; button: string; onClick: () => void }) { return <article className="panel export-card"><div className="export-icon">{icon}</div><h3>{title}</h3><p>{description}</p><button className="button-secondary" onClick={onClick}><Download size={15} />{button}</button></article> }
function FileBarIcon() { return <FileText size={20} /> }
