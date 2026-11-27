// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import QualityScoreCard from './QualityScoreCard'
import type { QualityScore } from '../../types'

const score: QualityScore = {
  initial_score: 100, critical_count: 1, warning_count: 2, info_count: 3,
  severity_counts: { critical: 1, warning: 2, info: 3 },
  critical_penalty: 15, warning_penalty: 10, info_penalty: 3,
  penalties: { critical: 15, warning: 10, info: 3 }, total_penalty: 28,
  score: 72, grade: 'C', grade_label: 'Fair', parse_error_count: 1,
  explanation: 'The score starts at 100 and deducts by severity.',
}

describe('QualityScoreCard', () => {
  afterEach(cleanup)

  it('shows score, grade, deductions, and parse error details', () => {
    render(<QualityScoreCard score={score} />)
    expect(screen.getByText('72')).toBeTruthy()
    expect(screen.getByText('Fair')).toBeTruthy()
    expect(screen.getByText('−28')).toBeTruthy()
    expect(screen.getByText(/1 file\(s\) could not be parsed/)).toBeTruthy()
  })

  it('handles perfect scores and older responses without scoring data', () => {
    const perfect = { ...score, score: 100, grade: 'A', grade_label: 'Excellent', total_penalty: 0, parse_error_count: 0 }
    const { rerender } = render(<QualityScoreCard score={perfect} />)
    expect(screen.getByRole('progressbar', { name: 'Quality score' }).getAttribute('aria-valuenow')).toBe('100')
    rerender(<QualityScoreCard />)
    expect(screen.getByText('Score unavailable')).toBeTruthy()
  })
})
