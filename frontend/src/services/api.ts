import type { AnalysisResult, GitHubFiles, GitHubPRAnalysis, GitHubPRInspection, GitHubRepository, Rule } from '../types'

const API_BASE = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new Error('Could not reach the analysis service. Check your connection and try again.')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    const message = Array.isArray(detail)
      ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ')
      : typeof detail === 'string' ? detail : `Request failed (${response.status}).`
    throw new Error(message || `Request failed (${response.status}).`)
  }
  if (payload == null) throw new Error('The backend returned an empty response.')
  return payload as T
}

export function checkHealth() {
  return request<{ status: string }>('/health')
}

export function fetchRules() {
  return request<Rule[]>('/api/rules')
}

export function analyzeSource(source_code: string, filename: string) {
  return request<AnalysisResult>('/api/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_code, filename, fail_on: ['critical'] }),
  })
}

export function analyzeFile(file: File) {
  const body = new FormData()
  body.append('file', file)
  body.append('fail_on', 'critical')
  return request<AnalysisResult>('/api/analyze/file', { method: 'POST', body })
}

export function fetchGitHubRepository(url: string) {
  return request<GitHubRepository>(`/api/github/repository?url=${encodeURIComponent(url)}`)
}

export function fetchGitHubFiles(url: string) {
  return request<GitHubFiles>(`/api/github/files?url=${encodeURIComponent(url)}`)
}

export function inspectGitHubPullRequest(url: string) {
  return request<GitHubPRInspection>('/api/github/pr/inspect', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
  })
}

export function analyzeGitHubPullRequest(url: string, snapshot_id: string, selected_files: string[]) {
  return request<GitHubPRAnalysis>('/api/github/pr/analyze', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, snapshot_id, selected_files }),
  })
}
