"""Stable request and response models for the analysis API."""

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    source_code: str = Field(description="Python source text to analyze")
    filename: str = Field(default="submitted.py", description="Display filename; must end in .py")
    fail_on: list[str] = Field(default_factory=lambda: ["critical"])


class IssueResponse(BaseModel):
    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    remediation: str | None = None


class FileResultResponse(BaseModel):
    file: str
    parse_error: str | None
    issues: list[IssueResponse]


class QualityGateResponse(BaseModel):
    blocking_severities: list[str]
    passed: bool


class QualityScoreResponse(BaseModel):
    initial_score: int
    critical_count: int
    warning_count: int
    info_count: int
    severity_counts: dict[str, int]
    critical_penalty: int
    warning_penalty: int
    info_penalty: int
    penalties: dict[str, int]
    total_penalty: int
    score: int
    grade: str
    grade_label: str
    parse_error_count: int = 0
    explanation: str


class AnalysisResponse(BaseModel):
    summary: dict[str, int]
    total_issues: int
    files: list[FileResultResponse]
    quality_gate: QualityGateResponse
    quality_score: QualityScoreResponse | None = None


class RuleResponse(BaseModel):
    rule_id: str
    severity: str
    description: str


class HealthResponse(BaseModel):
    status: str


class GitHubRepositoryResponse(BaseModel):
    normalized_url: str
    name: str
    full_name: str
    owner: str
    description: str | None = None
    html_url: str
    default_branch: str
    visibility: str | None = None
    private: bool
    stargazers_count: int | None = None
    fork: bool | None = None
    updated_at: str | None = None


class GitHubFilesResponse(BaseModel):
    normalized_url: str
    repository: GitHubRepositoryResponse
    default_branch: str
    total_python_files: int | None = None
    python_files: list[str]
    truncated: bool
    file_list_limited: bool
    file_limit: int
    limitation: str | None = None


class GitHubPRRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class GitHubPRAnalyzeRequest(GitHubPRRequest):
    snapshot_id: str | None = Field(default=None, min_length=1, max_length=64)
    selected_files: list[str] | None = Field(default=None, max_length=25)


class GitHubPRMetadataResponse(BaseModel):
    number: int
    title: str
    description: str | None = None
    author: str | None = None
    state: str
    draft: bool | None = None
    html_url: str
    repository_full_name: str
    head_branch: str | None = None
    base_branch: str | None = None
    head_sha: str
    base_sha: str
    created_at: str | None = None
    updated_at: str | None = None
    changed_files_total: int | None = None


class GitHubPRChangedFileResponse(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    extension: str
    is_python: bool
    eligible_for_analysis: bool
    size: int | None = None
    previous_filename: str | None = None
    selected_for_analysis: bool | None = None


class GitHubPRInspectResponse(BaseModel):
    snapshot_id: str
    pull_request: GitHubPRMetadataResponse
    changed_files: list[GitHubPRChangedFileResponse]
    changed_files_total: int | None = None
    changed_files_complete: bool
    limitation: str | None = None
    max_analysis_files: int


class GitHubPRIssueResponse(BaseModel):
    rule_id: str
    severity: str
    file: str
    line: int
    column: int | None = None
    message: str
    remediation: str | None = None


class GitHubPRAnalyzedFileResponse(BaseModel):
    filename: str
    source_code: str
    parse_error: str | None = None
    issues: list[GitHubPRIssueResponse]


class GitHubPRSkippedFileResponse(BaseModel):
    filename: str
    reason: str


class GitHubPRCoverageResponse(BaseModel):
    changed_python_files: int
    python_file_count_complete: bool
    selected_python_files: int
    analyzed_python_files: int
    skipped_python_files: int
    coverage_percent: float
    complete: bool


class GitHubPRAnalysisResponse(BaseModel):
    pull_request: GitHubPRMetadataResponse
    changed_files: list[GitHubPRChangedFileResponse]
    changed_files_total: int | None = None
    changed_files_complete: bool
    limitation: str | None = None
    selected_files: list[str]
    skipped_files: list[GitHubPRSkippedFileResponse]
    files: list[GitHubPRAnalyzedFileResponse]
    summary: dict[str, int]
    total_findings: int
    quality_score: QualityScoreResponse
    analysis_coverage: GitHubPRCoverageResponse
    analyzed_at: str
