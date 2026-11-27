// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsPage from './SettingsPage'
import { fetchRules } from '../services/api'

vi.mock('../services/api', () => ({ fetchRules: vi.fn() }))

describe('SettingsPage', () => {
  afterEach(cleanup)

  it('loads the registered rule count from the API and uses deployment-neutral links', async () => {
    vi.mocked(fetchRules).mockResolvedValue(Array.from({ length: 14 }, (_, index) => ({
      rule_id: `RULE${index}`,
      severity: 'warning',
      description: 'Registered analyzer rule',
    })))

    render(<SettingsPage connected />)
    await waitFor(() => expect(screen.getByText('14 registered rules')).toBeTruthy())
    expect(screen.getByText('API requests use the current application origin.')).toBeTruthy()
    expect(screen.getByRole('link', { name: /open docs/i }).getAttribute('href')).toBe('/docs')
  })
})
