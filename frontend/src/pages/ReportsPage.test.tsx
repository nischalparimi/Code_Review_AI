// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import ReportsPage from './ReportsPage'
import type { AnalysisSession } from '../types'

const session: AnalysisSession = {
  id: 'session-1', filename: 'sample.py', createdAt: '2026-01-01T00:00:00.000Z',
  result: {
    summary: { critical: 1, warning: 0, info: 0 }, total_issues: 1,
    files: [{ file: 'sample.py', parse_error: null, issues: [{
      rule_id: 'SEC005', severity: 'critical', file: 'sample.py', line: 9,
      message: 'Potential SQL injection.', remediation: 'Use parameterized queries.',
    }] }],
    quality_gate: { blocking_severities: ['critical'], passed: false },
    quality_score: {
      initial_score: 100, critical_count: 1, warning_count: 0, info_count: 0,
      severity_counts: { critical: 1, warning: 0, info: 0 },
      critical_penalty: 15, warning_penalty: 0, info_penalty: 0,
      penalties: { critical: 15, warning: 0, info: 0 }, total_penalty: 15,
      score: 85, grade: 'B', grade_label: 'Good', parse_error_count: 0,
      explanation: 'The score starts at 100 and deducts by severity.',
    },
  },
}

async function readBlob(blob: Blob) {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

describe('ReportsPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('exports actual JSON and CSV results including advanced findings and remediation', async () => {
    let exported: Blob | undefined
    vi.stubGlobal('URL', {
      createObjectURL: (blob: Blob) => { exported = blob; return 'blob:report' },
      revokeObjectURL: vi.fn(),
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    render(<ReportsPage sessions={[session]} />)

    fireEvent.click(screen.getByRole('button', { name: 'Download JSON' }))
    const json = JSON.parse(await readBlob(exported!))
    expect(json.files[0].issues[0]).toMatchObject({ rule_id: 'SEC005', remediation: 'Use parameterized queries.' })
    expect(json.quality_score).toMatchObject({ score: 85, grade: 'B' })

    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
    const csv = await readBlob(exported!)
    expect(csv).toContain('SEC005')
    expect(csv).toContain('Use parameterized queries.')
  })
})
