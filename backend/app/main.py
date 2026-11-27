"""FastAPI application exposing the existing static analyzer."""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from analyzer.rules import ALL_RULES
from backend.app.schemas import (
    AnalysisRequest,
    AnalysisResponse,
    HealthResponse,
    GitHubFilesResponse,
    GitHubPRAnalyzeRequest,
    GitHubPRAnalysisResponse,
    GitHubPRInspectResponse,
    GitHubPRRequest,
    GitHubRepositoryResponse,
    RuleResponse,
)
from backend.app.services.analysis import (
    MAX_SOURCE_BYTES,
    SourceTooLargeError,
    analyze_source,
    display_filename,
)
from backend.app.services.scoring import calculate_quality_score
from backend.app.services.github_service import GitHubIntegrationError, GitHubService
from backend.app.services.github_pr_service import (
    MAX_PR_ANALYSIS_FILES,
    GitHubPRService,
    parse_github_pr_url,
    pr_snapshot_cache,
)
from backend.app.middleware import InMemoryRateLimitMiddleware, RequestBodyLimitMiddleware

app = FastAPI(
    title="Automated Code Review API",
    version="1.0.0",
    debug=False,
)
app.add_middleware(InMemoryRateLimitMiddleware)
app.add_middleware(RequestBodyLimitMiddleware)
ALLOWED_SEVERITIES = {"info", "warning", "critical"}


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_request, exc: RequestValidationError):
    """Avoid echoing submitted source or credentials in Pydantic error payloads."""
    errors = [{"loc": error.get("loc", []), "msg": error.get("msg", "Invalid input"), "type": error.get("type", "value_error")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


def _validate_fail_on(values: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
    invalid = sorted(set(normalized) - ALLOWED_SEVERITIES)
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown severity value(s): {', '.join(invalid)}")
    return normalized


def _run_analysis(source: str, filename: str, fail_on: list[str]) -> dict:
    try:
        safe_name = display_filename(filename)
        report = analyze_source(source, safe_name, fail_on)
        findings = [issue for file_result in report["files"] for issue in file_result["issues"]]
        parse_error_count = sum(file_result["parse_error"] is not None for file_result in report["files"])
        report["quality_score"] = calculate_quality_score(findings, parse_error_count)
        return report
    except SourceTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Do not expose local paths or internal exception details to API clients.
        raise HTTPException(status_code=500, detail="Analysis failed unexpectedly") from exc


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok"}


def get_github_service() -> GitHubService:
    """Public API is intentionally unauthenticated and must never use a backend token."""
    return GitHubService(token="")


def _github_error(exc: GitHubIntegrationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@app.get("/api/github/repository", response_model=GitHubRepositoryResponse)
def github_repository(
    url: str = Query(..., min_length=1, max_length=2048),
    service: GitHubService = Depends(get_github_service),
):
    try:
        return service.get_repository(url)
    except GitHubIntegrationError as exc:
        raise _github_error(exc) from exc


@app.get("/api/github/files", response_model=GitHubFilesResponse)
def github_python_files(
    url: str = Query(..., min_length=1, max_length=2048),
    service: GitHubService = Depends(get_github_service),
):
    try:
        return service.get_python_files(url)
    except GitHubIntegrationError as exc:
        raise _github_error(exc) from exc


def get_github_pr_service() -> GitHubPRService:
    """Dependency factory for mockable pull request operations."""
    # PR analysis returns repository source code. Do not grant anonymous callers
    # private-repository access through a server-side credential.
    return GitHubPRService(token="")


@app.post("/api/github/pr/inspect", response_model=GitHubPRInspectResponse)
def inspect_github_pr(request: GitHubPRRequest, service: GitHubPRService = Depends(get_github_pr_service)):
    try:
        snapshot = service.inspect_pr(request.url)
        pr_snapshot_cache.put(snapshot)
        return {
            "snapshot_id": snapshot.snapshot_id,
            "pull_request": snapshot.pull_request,
            "changed_files": snapshot.changed_files,
            "changed_files_total": snapshot.changed_files_total,
            "changed_files_complete": snapshot.changed_files_complete,
            "limitation": snapshot.limitation,
            "max_analysis_files": MAX_PR_ANALYSIS_FILES,
        }
    except GitHubIntegrationError as exc:
        raise _github_error(exc) from exc


@app.post("/api/github/pr/analyze", response_model=GitHubPRAnalysisResponse)
def analyze_github_pr(request: GitHubPRAnalyzeRequest, service: GitHubPRService = Depends(get_github_pr_service)):
    try:
        if request.snapshot_id:
            snapshot = pr_snapshot_cache.get(request.snapshot_id)
            if snapshot is None:
                raise HTTPException(status_code=410, detail="Pull request selection expired. Inspect the PR again before analysis.")
            _owner, _repository, _number, normalized = parse_github_pr_url(request.url)
            if normalized != snapshot.normalized_url:
                raise HTTPException(status_code=422, detail="The selected PR snapshot does not match this pull request URL.")
        else:
            snapshot = service.inspect_pr(request.url)
        return service.analyze_pr(snapshot, request.selected_files)
    except GitHubIntegrationError as exc:
        raise _github_error(exc) from exc


@app.get("/api/rules", response_model=list[RuleResponse])
def list_rules():
    return [
        {"rule_id": rule.rule_id, "severity": rule.severity, "description": rule.description}
        for rule in ALL_RULES
    ]


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze_code(request: AnalysisRequest):
    fail_on = _validate_fail_on(request.fail_on)
    return _run_analysis(request.source_code, request.filename, fail_on)


@app.post("/api/analyze/file", response_model=AnalysisResponse)
async def analyze_uploaded_file(
    file: UploadFile = File(...),
    fail_on: str = Form("critical"),
):
    try:
        filename = display_filename(file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chunks = []
    size = 0
    try:
        while True:
            chunk = await file.read(min(65_536, MAX_SOURCE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SOURCE_BYTES:
                raise HTTPException(status_code=413, detail=f"file exceeds the {MAX_SOURCE_BYTES}-byte limit")
            chunks.append(chunk)
    finally:
        await file.close()

    try:
        source = b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="uploaded file must contain UTF-8 Python source") from exc
    blockers = _validate_fail_on(fail_on.split(","))
    return _run_analysis(source, filename, blockers)
