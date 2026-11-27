// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import AnalyzerPage from './AnalyzerPage'
import { analyzeFile, analyzeSource } from '../services/api'
import type { AnalysisResult } from '../types'

vi.mock('../services/api', () => ({ analyzeFile: vi.fn(), analyzeSource: vi.fn() }))

const result: AnalysisResult = {
  summary: { critical: 1, warning: 0, info: 0 },
  total_issues: 1,
  files: [{ file: 'input.py', parse_error: null, issues: [{ rule_id: 'SEC001', severity: 'critical', file: 'input.py', line: 1, message: 'eval call' }] }],
  quality_gate: { blocking_severities: ['critical'], passed: false },
  quality_score: {
    initial_score: 100, critical_count: 1, warning_count: 0, info_count: 0,
    severity_counts: { critical: 1, warning: 0, info: 0 },
    critical_penalty: 15, warning_penalty: 0, info_penalty: 0,
    penalties: { critical: 15, warning: 0, info: 0 }, total_penalty: 15,
    score: 85, grade: 'B', grade_label: 'Good', parse_error_count: 0,
    explanation: 'Score based on actual findings.',
  },
}

describe('AnalyzerPage', () => {
  afterEach(cleanup)
  beforeEach(() => { vi.mocked(analyzeFile).mockReset(); vi.mocked(analyzeSource).mockReset() })

  it('submits pasted code to the source endpoint and forwards real results', async () => {
    vi.mocked(analyzeSource).mockResolvedValue(result)
    const onAnalyzed = vi.fn()
    render(<AnalyzerPage session={null} onAnalyzed={onAnalyzed} onNewAnalysis={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Python source code'), { target: { value: 'eval(value)' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze code/ }))
    await waitFor(() => expect(analyzeSource).toHaveBeenCalledWith('eval(value)', 'main.py'))
    expect(analyzeFile).not.toHaveBeenCalled()
    expect(onAnalyzed).toHaveBeenCalledWith('input.py', result, 'eval(value)')
  })

  it('uploads a selected Python file through the file endpoint', async () => {
    vi.mocked(analyzeFile).mockResolvedValue(result)
    const onAnalyzed = vi.fn()
    render(<AnalyzerPage session={null} onAnalyzed={onAnalyzed} onNewAnalysis={vi.fn()} />)
    fireEvent.click(screen.getByRole('tab', { name: /Upload file/ }))
    const file = new File(['eval(value)'], 'upload.py', { type: 'text/x-python' })
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze code/ }))
    await waitFor(() => expect(analyzeFile).toHaveBeenCalledWith(file))
    expect(analyzeSource).not.toHaveBeenCalled()
    expect(onAnalyzed).toHaveBeenCalledWith('input.py', result, 'eval(value)')
  })

  it('shows backend errors without fabricating results', async () => {
    vi.mocked(analyzeSource).mockRejectedValue(new Error('Backend unavailable'))
    const onAnalyzed = vi.fn()
    render(<AnalyzerPage session={null} onAnalyzed={onAnalyzed} onNewAnalysis={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Python source code'), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze code/ }))
    expect((await screen.findByRole('alert')).textContent).toContain('Backend unavailable')
    expect(onAnalyzed).not.toHaveBeenCalled()
  })

  it('shows an in-progress state while analysis is pending', async () => {
    let resolveAnalysis!: (value: AnalysisResult) => void
    vi.mocked(analyzeSource).mockImplementation(() => new Promise(resolve => { resolveAnalysis = resolve }))
    render(<AnalyzerPage session={null} onAnalyzed={vi.fn()} onNewAnalysis={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Python source code'), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /Analyze code/ }))
    expect(screen.getByRole('button', { name: /Analyzing/ })).toBeTruthy()
    resolveAnalysis(result)
    await waitFor(() => expect(screen.queryByRole('button', { name: /Analyzing/ })).toBeNull())
  })
})
