import { useEffect, useState } from 'react'
import { CheckCircle2, CircleAlert, Code2, ExternalLink, Info, ShieldCheck } from 'lucide-react'
import { fetchRules } from '../services/api'

export default function SettingsPage({ connected }: { connected: boolean | null }) {
  const [ruleCount, setRuleCount] = useState<string>('Loading…')

  useEffect(() => {
    let active = true
    fetchRules()
      .then(rules => { if (active) setRuleCount(String(rules.length)) })
      .catch(() => { if (active) setRuleCount('Unavailable') })
    return () => { active = false }
  }, [])

  return <div className="page-stack"><section className="page-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> WORKSPACE CONFIGURATION</div><h2>Settings</h2><p>Application and backend status for this workspace.</p></div></section>
    <section className="panel settings-panel"><div className="settings-section-title"><span className="settings-section-icon"><Code2 size={17} /></span><div><h3>Backend connection</h3><p>API target used by this frontend.</p></div></div><div className="settings-row"><div><strong>FastAPI service</strong><span>API requests use the current application origin.</span></div><div className={`settings-status ${connected === true ? 'online' : connected === false ? 'offline' : ''}`}>{connected === true ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}{connected === true ? 'Connected' : connected === false ? 'Unavailable' : 'Checking'}</div></div><div className="settings-row"><div><strong>API documentation</strong><span>Interactive OpenAPI docs served by the backend.</span></div><a className="external-link" href="/docs" target="_blank" rel="noreferrer">Open docs <ExternalLink size={13} /></a></div></section>
    <section className="panel settings-panel"><div className="settings-section-title"><span className="settings-section-icon violet"><ShieldCheck size={17} /></span><div><h3>Analyzer</h3><p>Capabilities reported by the current project.</p></div></div><div className="settings-row"><div><strong>Analysis engine</strong><span>Python standard-library AST parser</span></div><span className="settings-value">{ruleCount} registered rules</span></div><div className="settings-row"><div><strong>Supported input</strong><span>Pasted Python text or a single uploaded .py file</span></div><span className="settings-value">Up to 1 MiB</span></div><div className="settings-row"><div><strong>Code execution</strong><span>Submitted source is parsed and never executed</span></div><span className="settings-status online"><CheckCircle2 size={15} /> Disabled</span></div></section>
    <div className="settings-note"><Info size={15} /><span>There are no user accounts, persistent history, or remote settings configured in this version.</span></div>
  </div>
}
