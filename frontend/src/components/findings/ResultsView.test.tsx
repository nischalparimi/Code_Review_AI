// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import ResultsView from './ResultsView'
import type { AnalysisResult } from '../../types'

const result: AnalysisResult = {
  summary: { critical: 1, warning: 1, info: 1 },
  total_issues: 3,
  files: [{
    file: 'review.py',
    parse_error: null,
    issues: [
      { rule_id: 'SEC003', severity: 'critical', file: 'review.py', line: 4, message: 'Unsafe shell invocation.', remediation: 'Use shell=False.' },
      { rule_id: 'SEC004', severity: 'warning', file: 'review.py', line: 6, message: 'Weak hash usage.' },
      { rule_id: 'FUTURE999', severity: 'info', file: 'review.py', line: 9, message: 'Unknown future rule.' },
    ],
  }],
  quality_gate: { blocking_severities: ['critical'], passed: false },
  quality_score: {
    initial_score: 100, critical_count: 1, warning_count: 1, info_count: 1,
    severity_counts: { critical: 1, warning: 1, info: 1 },
    critical_penalty: 15, warning_penalty: 5, info_penalty: 1,
    penalties: { critical: 15, warning: 5, info: 1 }, total_penalty: 21,
    score: 79, grade: 'B', grade_label: 'Good', parse_error_count: 0,
    explanation: 'The score starts at 100 and deducts by severity.',
  },
}

describe('ResultsView', () => {
  afterEach(cleanup)

  it('filters findings by severity and rule and displays optional remediation', () => {
    render(<ResultsView result={result} filename="review.py" />)
    expect(screen.getByText('79')).toBeTruthy()
    const body = () => within(screen.getByRole('table').querySelector('tbody') as HTMLElement)
    expect(body().getByText('Unknown future rule.')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Filter by severity'), { target: { value: 'warning' } })
    expect(screen.getByText('79')).toBeTruthy()
    expect(body().getByText('Weak hash usage.')).toBeTruthy()
    expect(body().queryByText('Unsafe shell invocation.')).toBeNull()

    fireEvent.change(screen.getByLabelText('Filter by rule'), { target: { value: 'SEC004' } })
    expect(body().getByText('Weak hash usage.')).toBeTruthy()
    expect(body().queryByText('Unknown future rule.')).toBeNull()
  })

  it('opens a finding detail and handles absent remediation from older responses', () => {
    const source = 'import subprocess\n\n\nsubprocess.run(command, shell=True)\n\nhashlib.md5(data)\n\n\nprint(1)'
    render(<ResultsView result={result} filename="review.py" sourceCode={source} />)
    fireEvent.click(screen.getByText('Unsafe shell invocation.'))
    expect(screen.getByLabelText('Finding details')).toBeTruthy()
    expect(screen.getByText('Source snippet · line 4')).toBeTruthy()
    expect(screen.getByText('Use shell=False.')).toBeTruthy()
    expect(document.querySelector('[data-line="4"]')?.className).toContain('code-line-selected')

    fireEvent.change(screen.getByLabelText('Filter by severity'), { target: { value: 'warning' } })
    expect(screen.getByText('Unsafe shell invocation.')).toBeTruthy()
    expect(document.querySelector('[data-line="4"]')?.className).toContain('code-line-selected')
    fireEvent.change(screen.getByLabelText('Filter by severity'), { target: { value: 'all' } })

    fireEvent.click(screen.getByText('Weak hash usage.'))
    expect(screen.getByText('Source snippet · line 6')).toBeTruthy()
    expect(document.querySelector('[data-line="6"]')?.className).toContain('code-line-selected')
  })

  it('clears selected finding state when a new analysis replaces the result', () => {
    const source = ['a', 'b', 'c', 'subprocess.run(command, shell=True)'].join('\n')
    const { rerender } = render(<ResultsView result={result} filename="review.py" sourceCode={source} />)
    fireEvent.click(screen.getByText('Unsafe shell invocation.'))
    expect(screen.getByText('FINDING DETAIL')).toBeTruthy()
    const nextResult: AnalysisResult = { ...result, files: [{ file: 'next.py', parse_error: null, issues: [] }] }
    rerender(<ResultsView result={nextResult} filename="next.py" sourceCode="pass" />)
    expect(screen.getByText('Select a finding to inspect its source and guidance.')).toBeTruthy()
    expect(document.querySelector('.code-line-selected')).toBeNull()
  })

  it('keeps source navigation stable while filtering and handles invalid line numbers', () => {
    const invalidResult: AnalysisResult = {
      ...result,
      files: [{ ...result.files[0], issues: [{ ...result.files[0].issues[0], line: 0 }] }],
    }
    render(<ResultsView result={invalidResult} filename="review.py" sourceCode="pass" />)
    fireEvent.click(screen.getByText('Unsafe shell invocation.'))
    expect(screen.getByText(/source line unavailable/)).toBeTruthy()
    expect(screen.getByText('A source snippet is unavailable for this finding.')).toBeTruthy()
    expect(document.querySelector('.code-line-selected')).toBeNull()
  })

  it('shows original source without highlights for clean analysis results', () => {
    const clean = { ...result, summary: { critical: 0, warning: 0, info: 0 }, total_issues: 0, files: [{ file: 'clean.py', parse_error: null, issues: [] }] }
    render(<ResultsView result={clean} filename="clean.py" sourceCode={['def greet():', "    return 'hello'"].join('\n')} />)
    expect(screen.getByText('def greet():')).toBeTruthy()
    expect(document.querySelector('[data-line="2"] .code-line-content')?.textContent).toBe("    return 'hello'")
    expect(document.querySelector('.finding-critical')).toBeNull()
  })
})
