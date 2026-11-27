export type Severity = 'critical' | 'warning' | 'info'

export interface Issue {
  rule_id: string
  severity: Severity | string
  file: string
  line: number
  message: string
  remediation?: string | null
}

export interface FileResult {
  file: string
  parse_error: string | null
  issues: Issue[]
}

export interface AnalysisResult {
  summary: Record<string, number>
  total_issues: number
  files: FileResult[]
  quality_gate: {
    blocking_severities: string[]
    passed: boolean
  }
  quality_score?: QualityScore | null
}

export interface QualityScore {
  initial_score: number
  critical_count: number
  warning_count: number
  info_count: number
  severity_counts: Record<string, number>
  critical_penalty: number
  warning_penalty: number
  info_penalty: number
  penalties: Record<string, number>
  total_penalty: number
  score: number
  grade: string
  grade_label: string
  parse_error_count?: number
  explanation: string
}

export interface Rule {
  rule_id: string
  severity: Severity | string
  description: string
}

export interface AnalysisSession {
  id: string
  filename: string
  createdAt: string
  result: AnalysisResult
  source_code?: string
}

export interface GitHubRepository {
  normalized_url: string
  name: string
  full_name: string
  owner: string
  description: string | null
  html_url: string
  default_branch: string
  visibility: string | null
  private: boolean
  stargazers_count: number | null
  fork: boolean | null
  updated_at: string | null
}

export interface GitHubFiles {
  normalized_url: string
  repository: GitHubRepository
  default_branch: string
  total_python_files: number | null
  python_files: string[]
  truncated: boolean
  file_list_limited: boolean
  file_limit: number
  limitation: string | null
}

export interface GitHubPRMetadata {
  number: number
  title: string
  description: string | null
  author: string | null
  state: string
  draft: boolean | null
  html_url: string
  repository_full_name: string
  head_branch: string | null
  base_branch: string | null
  head_sha: string
  base_sha: string
  created_at: string | null
  updated_at: string | null
  changed_files_total: number | null
}

export interface GitHubPRChangedFile {
  filename: string
  status: string
  additions: number
  deletions: number
  extension: string
  is_python: boolean
  eligible_for_analysis: boolean
  size: number | null
  previous_filename: string | null
  selected_for_analysis?: boolean | null
}

export interface GitHubPRInspection {
  snapshot_id: string
  pull_request: GitHubPRMetadata
  changed_files: GitHubPRChangedFile[]
  changed_files_total: number | null
  changed_files_complete: boolean
  limitation: string | null
  max_analysis_files: number
}

export interface GitHubPRAnalyzedFile {
  filename: string
  source_code: string
  parse_error: string | null
  issues: Array<Issue & { column?: number | null }>
}

export interface GitHubPRSkippedFile {
  filename: string
  reason: string
}

export interface GitHubPRAnalysis {
  pull_request: GitHubPRMetadata
  changed_files: GitHubPRChangedFile[]
  changed_files_total: number | null
  changed_files_complete: boolean
  limitation: string | null
  selected_files: string[]
  skipped_files: GitHubPRSkippedFile[]
  files: GitHubPRAnalyzedFile[]
  summary: Record<string, number>
  total_findings: number
  quality_score: QualityScore
  analysis_coverage: {
    changed_python_files: number
    python_file_count_complete: boolean
    selected_python_files: number
    analyzed_python_files: number
    skipped_python_files: number
    coverage_percent: number
    complete: boolean
  }
  analyzed_at: string
}

export type PageId = 'overview' | 'analyzer' | 'history' | 'rules' | 'reports' | 'github' | 'pull-request' | 'settings'
