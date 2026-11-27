// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PullRequestPage, { normalizePullRequestUrl } from './PullRequestPage'
import { analyzeGitHubPullRequest, inspectGitHubPullRequest } from '../services/api'
import type { GitHubPRAnalysis, GitHubPRInspection } from '../types'

vi.mock('../services/api', () => ({ inspectGitHubPullRequest: vi.fn(), analyzeGitHubPullRequest: vi.fn() }))

const url = 'https://github.com/octo/demo/pull/12'
const sha = 'a'.repeat(40)
const metadata = {
  number: 12, title: 'Improve parser', description: 'Review this change', author: 'octocat', state: 'open', draft: false,
  html_url: url, repository_full_name: 'octo/demo', head_branch: 'feature/parser', base_branch: 'main',
  head_sha: sha, base_sha: 'b'.repeat(40), created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z', changed_files_total: 3,
}
const changedFiles = [
  { filename: 'src/main.py', status: 'modified', additions: 4, deletions: 1, extension: 'py', is_python: true, eligible_for_analysis: true, size: 20, previous_filename: null },
  { filename: 'src/old.py', status: 'removed', additions: 0, deletions: 8, extension: 'py', is_python: true, eligible_for_analysis: false, size: 0, previous_filename: null },
  { filename: 'README.md', status: 'modified', additions: 1, deletions: 0, extension: 'md', is_python: false, eligible_for_analysis: false, size: 10, previous_filename: null },
]
const inspection: GitHubPRInspection = {
  snapshot_id: 'snapshot-123', pull_request: metadata, changed_files: changedFiles, changed_files_total: 3,
  changed_files_complete: true, limitation: null, max_analysis_files: 25,
}
const review: GitHubPRAnalysis = {
  pull_request: metadata,
  changed_files: changedFiles.map(file => ({ ...file, selected_for_analysis: file.filename === 'src/main.py' })),
  changed_files_total: 3, changed_files_complete: true, limitation: 'One file was removed.',
  selected_files: ['src/main.py'], skipped_files: [{ filename: 'src/old.py', reason: 'File was removed by this pull request.' }],
  files: [{ filename: 'src/main.py', source_code: "x = eval('input')\n", parse_error: null, issues: [{
    rule_id: 'SEC001', severity: 'critical', file: 'src/main.py', line: 1, message: 'Dynamic evaluation found.', remediation: 'Avoid evaluating untrusted input.',
  }] }],
  summary: { critical: 1, warning: 0, info: 0 }, total_findings: 1,
  quality_score: {
    initial_score: 100, critical_count: 1, warning_count: 0, info_count: 0,
    severity_counts: { critical: 1, warning: 0, info: 0 }, critical_penalty: 15, warning_penalty: 0, info_penalty: 0,
    penalties: { critical: 15, warning: 0, info: 0 }, total_penalty: 15, score: 85, grade: 'B', grade_label: 'Good',
    parse_error_count: 0, explanation: 'The score starts at 100 and applies analyzer severity penalties.',
  },
  analysis_coverage: { changed_python_files: 2, python_file_count_complete: true, selected_python_files: 1, analyzed_python_files: 1, skipped_python_files: 1, coverage_percent: 50, complete: false },
  analyzed_at: '2026-01-02T00:00:00Z',
}

describe('PullRequestPage', () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
  beforeEach(() => { vi.mocked(inspectGitHubPullRequest).mockReset(); vi.mocked(analyzeGitHubPullRequest).mockReset() })

  it('validates exact GitHub pull request URL formats', () => {
    expect(normalizePullRequestUrl(`${url}/`)).toBe(url)
    expect(normalizePullRequestUrl('https://github.com/octo/demo')).toBeNull()
    expect(normalizePullRequestUrl('https://github.com/octo/demo/pull/0')).toBeNull()
    expect(normalizePullRequestUrl('https://github.com/octo/demo/pull/nope')).toBeNull()
    expect(normalizePullRequestUrl('https://api.github.com/repos/octo/demo/pulls/12')).toBeNull()
    expect(normalizePullRequestUrl('https://github.com/octo/demo/pull/12/files')).toBeNull()
  })

  it('shows validation errors locally and does not call the API', async () => {
    render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: 'https://github.com/octo/demo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Enter a GitHub pull request URL')
    expect(inspectGitHubPullRequest).not.toHaveBeenCalled()
  })

  it('loads PR metadata and changed files, then analyzes selected paths at the cached snapshot', async () => {
    vi.mocked(inspectGitHubPullRequest).mockResolvedValue(inspection)
    vi.mocked(analyzeGitHubPullRequest).mockResolvedValue(review)
    render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: `${url}/` } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    expect(await screen.findByText('Improve parser')).toBeTruthy()
    expect(screen.getByText('feature/parser')).toBeTruthy()
    expect(screen.getByText('src/main.py')).toBeTruthy()
    expect((screen.getByLabelText('Select PR file src/main.py') as HTMLInputElement).checked).toBe(true)
    expect((screen.getByLabelText('Select PR file src/old.py') as HTMLInputElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /Analyze selected/ }))
    expect(await screen.findByText('85')).toBeTruthy()
    expect(screen.getByText('Dynamic evaluation found.')).toBeTruthy()
    expect(screen.getByText(/50%/)).toBeTruthy()
    expect(screen.getAllByText('src/old.py').length).toBeGreaterThan(0)
    expect(analyzeGitHubPullRequest).toHaveBeenCalledWith(url, 'snapshot-123', ['src/main.py'])
  })

  it('preserves overall score while filtering findings by severity, rule, and file', async () => {
    vi.mocked(inspectGitHubPullRequest).mockResolvedValue(inspection)
    vi.mocked(analyzeGitHubPullRequest).mockResolvedValue(review)
    render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    await screen.findByText('Improve parser')
    fireEvent.click(screen.getByRole('button', { name: /Analyze selected/ }))
    await screen.findByText('Dynamic evaluation found.')
    fireEvent.change(screen.getByLabelText('Filter PR findings by severity'), { target: { value: 'warning' } })
    expect(screen.getByText('85')).toBeTruthy()
    expect(screen.getByText('No findings match these filters.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Filter PR findings by severity'), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText('Filter PR findings by rule'), { target: { value: 'SEC001' } })
    fireEvent.change(screen.getByLabelText('Filter PR findings by file path'), { target: { value: 'src/main.py' } })
    expect(screen.getByText('Dynamic evaluation found.')).toBeTruthy()
    expect(screen.getByText('85')).toBeTruthy()
  })

  it('shows partial coverage and empty Python-change state', async () => {
    const partial = { ...inspection, changed_files_complete: false, limitation: 'GitHub limited the returned PR file list.', changed_files: [changedFiles[2]] }
    vi.mocked(inspectGitHubPullRequest).mockResolvedValueOnce(partial).mockResolvedValueOnce({ ...inspection, changed_files: [changedFiles[2]], changed_files_total: 1 })
    const { rerender } = render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    expect(await screen.findByText('GitHub limited the returned PR file list.')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: `${url}?bad=1` } })
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    expect(await screen.findByText('No Python files changed in this pull request.')).toBeTruthy()
    rerender(<PullRequestPage />)
  })

  it('shows loading, prevents duplicate inspect calls, and reports API errors', async () => {
    let release!: (value: GitHubPRInspection) => void
    vi.mocked(inspectGitHubPullRequest).mockImplementation(() => new Promise(resolve => { release = resolve }))
    render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    fireEvent.click(screen.getByRole('button', { name: /Loading PR/ }))
    expect(inspectGitHubPullRequest).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status').textContent).toContain('Retrieving pull request metadata')
    release(inspection)
    expect(await screen.findByText('Improve parser')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: `${url}?x=1` } })
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    vi.mocked(inspectGitHubPullRequest).mockRejectedValueOnce(new Error('GitHub request timed out.'))
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    expect((await screen.findByRole('alert')).textContent).toContain('GitHub request timed out.')
  })

  it('exports a JSON report without embedding source contents', async () => {
    vi.mocked(inspectGitHubPullRequest).mockResolvedValue(inspection)
    vi.mocked(analyzeGitHubPullRequest).mockResolvedValue(review)
    let downloaded: Blob | undefined
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    render(<PullRequestPage />)
    fireEvent.change(screen.getByLabelText('GitHub pull request URL'), { target: { value: url } })
    fireEvent.click(screen.getByRole('button', { name: 'Load pull request' }))
    await screen.findByText('Improve parser')
    fireEvent.click(screen.getByRole('button', { name: /Analyze selected/ }))
    await screen.findByRole('button', { name: 'Export JSON' })
    vi.stubGlobal('URL', { createObjectURL: (blob: Blob) => { downloaded = blob; return 'blob:pr' }, revokeObjectURL: vi.fn() })
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))
    const exportedText = await new Promise<string>(resolve => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.readAsText(downloaded!)
    })
    const exported = JSON.parse(exportedText)
    expect(exported.pull_request.number).toBe(12)
    expect(exported.quality_score.score).toBe(85)
    expect(exported.files[0].issues[0].rule_id).toBe('SEC001')
    expect(exported.files[0].source_code).toBeUndefined()
  })
})
