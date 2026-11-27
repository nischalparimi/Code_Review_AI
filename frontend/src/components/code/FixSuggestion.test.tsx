// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import FixSuggestion from './FixSuggestion'
import type { Issue } from '../../types'

const issue = (rule_id: string, remediation?: string): Issue => ({ rule_id, severity: 'critical', file: 'sample.py', line: 1, message: 'Example finding.', remediation })

describe('FixSuggestion', () => {
  afterEach(cleanup)

  it('shows a safe before and after credential preview without mutating the original line', () => {
    const original = 'API_KEY = "secret-value"'
    render(<FixSuggestion issue={issue('SEC002')} sourceLine={original} />)
    expect(screen.getByText('Before · original line')).toBeTruthy()
    expect(screen.getByText('API_KEY = "secret-value"')).toBeTruthy()
    expect(containerPreview()).toBe('import os\n\nAPI_KEY = os.getenv("API_KEY")')
    expect(screen.getByText(/never applied automatically/)).toBeTruthy()
    expect(original).toBe('API_KEY = "secret-value"')
  })

  it('provides rule-based guidance and an unknown-rule fallback', () => {
    const { rerender } = render(<FixSuggestion issue={issue('BUG002')} />)
    expect(screen.getByText(/Mutable default objects are created once/)).toBeTruthy()
    rerender(<FixSuggestion issue={issue('NEW999', 'Check the custom rule remediation.')} />)
    expect(screen.getByText('Check the custom rule remediation.')).toBeTruthy()
    rerender(<FixSuggestion issue={issue('NEW998')} />)
    expect(screen.getByText(/No rule-specific suggestion is available/)).toBeTruthy()
  })

  it('does not invent a code preview for unknown commands or complex findings', () => {
    const { container } = render(<FixSuggestion issue={issue('SEC003')} sourceLine="subprocess.run(command, shell=True)" />)
    expect(screen.getByText(/correct executable and arguments depend/)).toBeTruthy()
    expect(container.querySelector('.fix-preview')).toBeNull()
  })
})

function containerPreview() {
  return document.querySelector('.fix-preview > div:last-child code')?.textContent
}
