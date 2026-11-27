import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, BookOpen, LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import { fetchRules } from '../services/api'
import type { Rule } from '../types'
import { categoryForRule } from '../utils/rules'
import { SeverityBadge, EmptyState } from '../components/ui/SeverityBadge'

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [severity, setSeverity] = useState('all')
  const load = async () => { setLoading(true); setError(''); try { setRules(await fetchRules()) } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load rules.') } finally { setLoading(false) } }
  useEffect(() => { void load() }, [])
  const visible = useMemo(() => rules.filter(rule => (severity === 'all' || rule.severity === severity) && `${rule.rule_id} ${rule.description} ${categoryForRule(rule.rule_id)}`.toLowerCase().includes(query.toLowerCase())), [rules, severity, query])

  return <div className="page-stack"><section className="page-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> RULE CATALOG</div><h2>Analysis rules</h2><p>Live definitions loaded from the FastAPI backend.</p></div><span className="catalog-count"><ShieldCheck size={15} /> {rules.length} registered</span></section>
    <section className="panel rules-panel"><div className="rules-toolbar"><label className="search-control"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search rules…" aria-label="Search rules" /></label><select aria-label="Filter rules by severity" value={severity} onChange={event => setSeverity(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option><option value="info">Info</option></select></div>
      {loading ? <div className="loading-state"><LoaderCircle size={19} className="spin" /> Loading rules from backend…</div> : error ? <div className="error-state"><AlertCircle size={19} /><div><strong>Could not load analyzer rules</strong><span>{error}</span></div><button className="button-secondary small" onClick={() => void load()}>Try again</button></div> : visible.length ? <div className="rule-grid">{visible.map(rule => <article className="rule-card" key={rule.rule_id}><div className="rule-card-top"><code>{rule.rule_id}</code><SeverityBadge severity={rule.severity} /></div><span className="rule-category"><BookOpen size={12} /> {categoryForRule(rule.rule_id)}</span><p>{rule.description}</p></article>)}</div> : <EmptyState icon={<Search size={19} />} title="No rules match" body="Try another search term or severity filter." />}
    </section>
  </div>
}
