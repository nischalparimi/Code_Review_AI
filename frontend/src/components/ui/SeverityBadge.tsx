import type { Severity } from '../../types'

export function SeverityBadge({ severity }: { severity: string }) {
  const normalized = severity.toLowerCase() as Severity
  return <span className={`severity-badge severity-${normalized}`}>{severity}</span>
}

export function EmptyState({ icon, title, body, action }: { icon: React.ReactNode; title: string; body: string; action?: React.ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon}</div><h3>{title}</h3><p>{body}</p>{action}</div>
}
