// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CodeViewer from './CodeViewer'
import type { CodeFinding } from './CodeViewer'

const finding = (overrides: Partial<CodeFinding> = {}): CodeFinding => ({
  id: 'finding-1', rule_id: 'SEC001', severity: 'critical', file: 'sample.py', line: 2,
  message: 'Dynamic evaluation.', ...overrides,
})

describe('CodeViewer', () => {
  afterEach(cleanup)

  it('shows line numbers and preserves source indentation and whitespace', () => {
    render(<CodeViewer source={'def f():\n    return 1  \n'} findings={[]} />)
    expect(screen.getByText('1')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
    expect(document.querySelector('[data-line="2"] .code-line-content')?.textContent).toBe('    return 1  ')
    expect(screen.getByText('3')).toBeTruthy()
  })

  it('highlights actual findings, distinguishes the selected line, and supports same-line findings', () => {
    const onSelect = vi.fn()
    const findings = [finding(), finding({ id: 'finding-2', rule_id: 'BUG001', severity: 'warning' })]
    render(<CodeViewer source={['pass', 'eval(value)'].join('\n')} findings={findings} selectedFindingId="finding-2" onSelectFinding={onSelect} />)
    const line = document.querySelector('[data-line="2"]')
    expect(line?.className).toContain('finding-critical')
    expect(line?.className).toContain('code-line-selected')
    expect(line?.getAttribute('data-finding-count')).toBe('2')
    fireEvent.click(screen.getByRole('button', { name: /2 findings on line 2/ }))
    expect(onSelect).toHaveBeenCalledWith('finding-1')
    expect(document.querySelector('[data-line="1"]')?.className).not.toContain('finding-')
  })

  it('scrolls a valid selected finding into the code viewer', () => {
    const scrollIntoView = vi.fn()
    const original = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
    render(<CodeViewer source={['one', 'two'].join('\n')} findings={[finding()]} selectedFindingId="finding-1" />)
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' })
    if (original) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', original)
    else Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
  })

  it('renders empty source and ignores invalid finding line numbers', () => {
    render(<CodeViewer source="" findings={[finding({ line: -1 })]} />)
    expect(screen.getByText('No source text was retained for this result. Findings remain available below.')).toBeTruthy()
    expect(document.querySelector('.finding-critical')).toBeNull()
  })
})
