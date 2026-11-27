import { useEffect, useMemo, useRef } from 'react'
import type { Issue } from '../../types'

export interface CodeFinding extends Issue { id: string }

const severityOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 }

export default function CodeViewer({ source, findings, selectedFindingId, onSelectFinding }: {
  source: string
  findings: CodeFinding[]
  selectedFindingId?: string | null
  onSelectFinding?: (findingId: string) => void
}) {
  const codeRef = useRef<HTMLDivElement>(null)
  const lines = useMemo(() => source.split(/\r\n|\n|\r/), [source])
  const selected = findings.find(finding => finding.id === selectedFindingId)
  const selectedLine = selected && Number.isInteger(selected.line) && selected.line > 0 && selected.line <= lines.length
    ? selected.line : null

  useEffect(() => {
    if (!selectedLine) return
    const target = codeRef.current?.querySelector<HTMLElement>(`[data-line="${selectedLine}"]`)
    if (target && typeof target.scrollIntoView === 'function') target.scrollIntoView({ block: 'center' })
  }, [selectedFindingId, selectedLine])

  const findingsByLine = useMemo(() => {
    const grouped = new Map<number, CodeFinding[]>()
    findings.forEach(finding => {
      if (!Number.isInteger(finding.line) || finding.line < 1 || finding.line > lines.length) return
      grouped.set(finding.line, [...(grouped.get(finding.line) ?? []), finding])
    })
    return grouped
  }, [findings, lines.length])

  return <section className="panel code-viewer-panel" aria-label="Submitted source code">
    <div className="code-viewer-heading"><div><h3>Source code</h3><p>Read-only source with analyzer findings</p></div><span>{lines.length} {lines.length === 1 ? 'line' : 'lines'}</span></div>
    <div className="code-viewer-scroll" ref={codeRef} role="region" aria-label="Source code with line numbers" tabIndex={0}>
      <div className="code-viewer" role="list">
        {lines.map((line, index) => {
          const lineNumber = index + 1
          const lineFindings = findingsByLine.get(lineNumber) ?? []
          const highest = lineFindings.slice().sort((a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3))[0]
          const selectedOnLine = lineFindings.some(finding => finding.id === selectedFindingId)
          const classes = ['code-line', highest ? `finding-${highest.severity}` : '', selectedOnLine ? 'code-line-selected' : ''].filter(Boolean).join(' ')
          const label = lineFindings.length ? `${lineFindings.length} finding${lineFindings.length === 1 ? '' : 's'} on line ${lineNumber}: ${lineFindings.map(item => `${item.rule_id}, ${item.severity}`).join('; ')}` : `Line ${lineNumber}`
          return <div key={lineNumber} className={classes} data-line={lineNumber} data-finding-count={lineFindings.length} aria-current={selectedOnLine ? 'location' : undefined} role="listitem">
            <span className="code-line-number" aria-hidden="true">{lineNumber}</span>
            {lineFindings.length > 0 ? <button type="button" className="code-line-indicator" aria-label={label} title={label} onClick={() => onSelectFinding?.(lineFindings[0].id)}><span className={`severity-marker ${highest?.severity}`} />{lineFindings.length > 1 && <small>{lineFindings.length}</small>}</button> : <span className="code-line-spacer" aria-hidden="true" />}
            <code className="code-line-content">{line.length ? line : ' '}</code>
          </div>
        })}
      </div>
    </div>
    {!source && <p className="code-viewer-empty">No source text was retained for this result. Findings remain available below.</p>}
    {!!findingsByLine.size && <div className="code-legend" aria-label="Finding severity legend"><span><i className="critical" />Critical</span><span><i className="warning" />Warning</span><span><i className="info" />Info</span></div>}
  </section>
}
