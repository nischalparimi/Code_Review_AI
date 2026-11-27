// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from './AppShell'

describe('AppShell GitHub navigation', () => {
  afterEach(cleanup)

  it('adds GitHub navigation while retaining existing workspace destinations', () => {
    const onNavigate = vi.fn()
    render(<AppShell page="github" title="GitHub Repository" connected={true} onNavigate={onNavigate}><div>Repository browser</div></AppShell>)
    const github = screen.getByRole('button', { name: 'GitHub' })
    expect(github.className).toContain('active')
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Code Analyzer' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Analysis History' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Rules' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Reports' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(onNavigate).toHaveBeenCalledWith('settings')
  })
})
