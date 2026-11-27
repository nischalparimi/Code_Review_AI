// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import RulesPage from './RulesPage'
import { fetchRules } from '../services/api'

vi.mock('../services/api', () => ({ fetchRules: vi.fn() }))

describe('RulesPage', () => {
  afterEach(cleanup)
  beforeEach(() => vi.mocked(fetchRules).mockReset())

  it('loads rules from the API and searches and filters unknown/new rule IDs', async () => {
    vi.mocked(fetchRules).mockResolvedValue([
      { rule_id: 'SEC003', severity: 'critical', description: 'Unsafe subprocess usage' },
      { rule_id: 'SMELL003', severity: 'warning', description: 'High complexity' },
      { rule_id: 'FUTURE999', severity: 'info', description: 'Future extension rule' },
    ])
    render(<RulesPage />)
    await waitFor(() => expect(screen.getByText('3 registered')).toBeTruthy())
    expect(screen.getByText('FUTURE999')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Filter rules by severity'), { target: { value: 'warning' } })
    expect(screen.getByText('SMELL003')).toBeTruthy()
    expect(screen.queryByText('SEC003')).toBeNull()

    fireEvent.change(screen.getByLabelText('Search rules'), { target: { value: 'no matching text' } })
    expect(screen.getByText('No rules match')).toBeTruthy()
  })

})
