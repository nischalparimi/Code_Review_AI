import { BadgeCheck, CircleAlert, Gauge } from 'lucide-react'
import type { QualityScore } from '../../types'

export default function QualityScoreCard({ score }: { score?: QualityScore | null }) {
  if (!score) return <section className="panel score-panel score-unavailable"><div className="score-panel-title"><span className="score-icon"><Gauge size={17} /></span><div><h3>Code quality score</h3><p>Score unavailable</p></div></div><span className="score-unavailable-note">This result was returned by a backend version without scoring data.</span></section>

  return <section className="panel score-panel" aria-label="Code quality score">
    <div className="score-panel-header"><div className="score-panel-title"><span className="score-icon"><Gauge size={17} /></span><div><h3>Code quality score</h3><p>Calculated from this analysis</p></div></div><div className={`grade-chip grade-${score.grade.toLowerCase()}`}><strong>{score.grade}</strong><span>{score.grade_label}</span></div></div>
    <div className="score-main"><div className="score-value"><strong>{score.score}</strong><span>/ {score.initial_score}</span></div><div className="score-progress" role="progressbar" aria-label="Quality score" aria-valuemin={0} aria-valuemax={100} aria-valuenow={score.score}><span style={{ width: `${score.score}%` }} /></div></div>
    <div className="score-breakdown" aria-label="Score deductions">
      <div><span><i className="score-dot critical" />Critical ({score.severity_counts.critical ?? score.critical_count})</span><strong>−{score.penalties.critical ?? score.critical_penalty}</strong></div>
      <div><span><i className="score-dot warning" />Warning ({score.severity_counts.warning ?? score.warning_count})</span><strong>−{score.penalties.warning ?? score.warning_penalty}</strong></div>
      <div><span><i className="score-dot info" />Info ({score.severity_counts.info ?? score.info_count})</span><strong>−{score.penalties.info ?? score.info_penalty}</strong></div>
      <div className="score-deduction-total"><span>Total deductions</span><strong>−{score.total_penalty}</strong></div>
    </div>
    <p className="score-explanation"><BadgeCheck size={14} />{score.explanation}</p>
    {!!score.parse_error_count && <p className="score-parse-note"><CircleAlert size={14} />{score.parse_error_count} file(s) could not be parsed and are excluded from finding penalties.</p>}
  </section>
}
