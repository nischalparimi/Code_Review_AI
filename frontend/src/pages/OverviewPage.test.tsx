// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage'
import type { AnalysisSession } from '../types'

vi.mock('recharts', () => ({
  CartesianGrid: () => null, Cell: () => null, Line: () => null, LineChart: () => <div data-testid="trend-chart" />,
  Pie: () => null, PieChart: () => null, ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => null, XAxis: () => null, YAxis: () => null,
}))

function session(id: string, score?: number): AnalysisSession {
  return {
    id, filename: `${id}.py`, createdAt: '2026-01-01T00:00:00.000Z',
    result: {
      summary: { critical: 0, warning: 0, info: 0 }, total_issues: 0, files: [],
      quality_gate: { blocking_severities: ['critical'], passed: true },
      ...(score === undefined ? {} : { quality_score: {
        initial_score: 100, critical_count: 0, warning_count: 0, info_count: 0,
        severity_counts: { critical: 0, warning: 0, info: 0 },
        critical_penalty: 0, warning_penalty: 0, info_penalty: 0,
        penalties: { critical: 0, warning: 0, info: 0 }, total_penalty: 0,
        score, grade: score >= 90 ? 'A' : 'B', grade_label: score >= 90 ? 'Excellent' : 'Good',
        parse_error_count: 0, explanation: 'Real score.',
      } }),
    },
  }
}

const props = { onNavigate: vi.fn(), onOpenSession: vi.fn() }

describe('OverviewPage quality scores', () => {
  afterEach(cleanup)

  it('shows an empty score state when there are no real scored analyses', () => {
    render(<OverviewPage sessions={[]} {...props} />)
    expect(screen.getByText('No scored analyses yet')).toBeTruthy()
    expect(screen.queryByTestId('trend-chart')).toBeNull()
  })

  it('shows latest score and a trend only from multiple scored sessions', () => {
    render(<OverviewPage sessions={[session('latest', 80), session('older', 95)]} {...props} />)
    expect(screen.getByText('80/100')).toBeTruthy()
    expect(screen.getByTestId('trend-chart')).toBeTruthy()
    expect(screen.getByText('95')).toBeTruthy()
    expect(screen.getByText('80')).toBeTruthy()
  })

  it('waits for a second real data point before rendering a trend', () => {
    const { container } = render(<OverviewPage sessions={[session('only', 80)]} {...props} />)
    expect(screen.getByText(/One scored analysis so far/)).toBeTruthy()
    expect(container.querySelector('.score-chart')).toBeNull()
  })
})
