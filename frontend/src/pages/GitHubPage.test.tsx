// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GitHubPage, { normalizeGitHubUrl } from './GitHubPage'
import { fetchGitHubFiles, fetchGitHubRepository } from '../services/api'
import type { GitHubFiles, GitHubRepository } from '../types'

vi.mock('../services/api', () => ({ fetchGitHubFiles: vi.fn(), fetchGitHubRepository: vi.fn() }))

const repository: GitHubRepository = {
  normalized_url: 'https://github.com/octo/demo', name: 'demo', full_name: 'octo/demo', owner: 'octo',
  description: 'Example repository', html_url: 'https://github.com/octo/demo', default_branch: 'main',
  visibility: 'public', private: false, stargazers_count: 42, fork: true, updated_at: '2026-01-02T00:00:00Z',
}

const files: GitHubFiles = {
  normalized_url: repository.normalized_url, repository, default_branch: 'main', total_python_files: 2,
  python_files: ['src/main.py', 'tests/test_main.py'], truncated: false, file_list_limited: false,
  file_limit: 1000, limitation: null,
}

describe('GitHubPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks() })
  beforeEach(() => { vi.mocked(fetchGitHubRepository).mockReset(); vi.mocked(fetchGitHubFiles).mockReset() })

  it('normalizes accepted URLs and rejects unsupported URL formats', () => {
    expect(normalizeGitHubUrl('https://github.com/octo/demo/')).toBe('https://github.com/octo/demo')
    expect(normalizeGitHubUrl('https://github.com/octo')).toBeNull()
    expect(normalizeGitHubUrl('https://gist.github.com/octo/hash')).toBeNull()
    expect(normalizeGitHubUrl('https://example.com/octo/demo')).toBeNull()
    expect(normalizeGitHubUrl('https://github.com/octo/demo/tree/main')).toBeNull()
  })

  it('shows validation feedback before making any API request', async () => {
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: 'https://github.com/octo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Enter a valid GitHub repository URL')
    expect(fetchGitHubRepository).not.toHaveBeenCalled()
  })

  it('disables duplicate connects and displays real metadata and nested Python paths', async () => {
    let release!: (value: GitHubRepository) => void
    vi.mocked(fetchGitHubRepository).mockImplementation(() => new Promise(resolve => { release = resolve }))
    vi.mocked(fetchGitHubFiles).mockResolvedValue(files)
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: 'https://github.com/octo/demo/' } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    fireEvent.click(screen.getByRole('button', { name: /Connecting/ }))
    expect(fetchGitHubRepository).toHaveBeenCalledTimes(1)
    release(repository)
    expect(await screen.findByText('Example repository')).toBeTruthy()
    expect(screen.getByText('main')).toBeTruthy()
    expect(screen.getByText('42')).toBeTruthy()
    expect(screen.getByText('Fork')).toBeTruthy()
    expect(screen.getByText('src/main.py')).toBeTruthy()
    expect(screen.getByText('tests/test_main.py')).toBeTruthy()
    expect(fetchGitHubFiles).toHaveBeenCalledWith(repository.normalized_url)
  })

  it('selects all visible paths and clears the selection', async () => {
    vi.mocked(fetchGitHubRepository).mockResolvedValue(repository)
    vi.mocked(fetchGitHubFiles).mockResolvedValue(files)
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: repository.normalized_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    await screen.findByText('src/main.py')
    fireEvent.click(screen.getByRole('button', { name: 'Select all visible' }))
    expect(screen.getByText('2 selected')).toBeTruthy()
    expect((screen.getByLabelText('Select src/main.py') as HTMLInputElement).checked).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }))
    expect(screen.getByText('0 selected')).toBeTruthy()
  })

  it('shows empty repository state when the tree has no Python files', async () => {
    vi.mocked(fetchGitHubRepository).mockResolvedValue(repository)
    vi.mocked(fetchGitHubFiles).mockResolvedValue({ ...files, total_python_files: 0, python_files: [] })
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: repository.normalized_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    expect(await screen.findByText('No Python files found')).toBeTruthy()
  })

  it('shows truncation details and only permits selecting the returned file paths', async () => {
    vi.mocked(fetchGitHubRepository).mockResolvedValue(repository)
    vi.mocked(fetchGitHubFiles).mockResolvedValue({ ...files, total_python_files: null, truncated: true, limitation: 'The file tree may be incomplete.' })
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: repository.normalized_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    expect(await screen.findByText('The file tree may be incomplete.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Select all visible' }))
    expect(screen.getByText('2 selected')).toBeTruthy()
  })

  it('clears previous repository state on reconnect and shows API errors', async () => {
    vi.mocked(fetchGitHubRepository).mockResolvedValueOnce(repository).mockRejectedValueOnce(new Error('Repository not found or inaccessible.'))
    vi.mocked(fetchGitHubFiles).mockResolvedValueOnce(files)
    render(<GitHubPage />)
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: repository.normalized_url } })
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    await screen.findByText('Example repository')
    fireEvent.change(screen.getByLabelText('Repository URL'), { target: { value: 'https://github.com/other/missing' } })
    expect(screen.queryByText('Example repository')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Connect repository' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Repository not found or inaccessible.')
    await waitFor(() => expect(screen.queryByText('Example repository')).toBeNull())
    expect(fetchGitHubFiles).toHaveBeenCalledTimes(1)
  })
})
