"""Read-only GitHub pull-request inspection and existing-engine analysis."""

import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from threading import Lock
import time
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx

from backend.app.services.analysis import MAX_SOURCE_BYTES, SourceTooLargeError, analyze_source
from backend.app.services.github_service import GitHubIntegrationError, GitHubService, GITHUB_WEB, parse_github_repository_url
from backend.app.services.scoring import calculate_quality_score

MAX_PR_CHANGED_FILES = 300
MAX_PR_FILE_PAGES = 3
MAX_PR_ANALYSIS_FILES = 25
MAX_PR_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PR_FILE_LIST_RESPONSE_BYTES = 8 * 1024 * 1024
PR_SNAPSHOT_TTL_SECONDS = 600
PR_SNAPSHOT_LIMIT = 64
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")


class PRFileError(Exception):
    """An expected per-file retrieval limitation with a safe message."""


def parse_github_pr_url(url: str) -> tuple[str, str, int, str]:
    """Validate an exact GitHub pull-request URL and return its canonical identity."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise GitHubIntegrationError(422, "Enter a valid GitHub pull request URL.")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise GitHubIntegrationError(422, "Enter a valid GitHub pull request URL.") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname != "github.com"
        or parsed.netloc.lower() != "github.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "%" in parsed.path
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
    ):
        raise GitHubIntegrationError(422, "Only https://github.com/owner/repository/pull/number URLs are supported.")
    path = parsed.path[:-1] if parsed.path.endswith("/") else parsed.path
    parts = path[1:].split("/")
    if len(parts) != 4 or parts[2] != "pull" or not parts[3].isascii() or not parts[3].isdecimal() or len(parts[3]) > 10:
        raise GitHubIntegrationError(422, "Enter a pull request URL with an owner, repository, and PR number.")
    owner, repository, _ = parse_github_repository_url(f"https://github.com/{parts[0]}/{parts[1]}")
    number = int(parts[3])
    if number < 1:
        raise GitHubIntegrationError(422, "Pull request number must be greater than zero.")
    normalized = f"{GITHUB_WEB}/{owner}/{repository}/pull/{number}"
    return owner, repository, number, normalized


def _safe_repo_path(path: str) -> bool:
    if not isinstance(path, str) or not path or len(path) > 4096 or path.startswith("/") or "\\" in path or any(ord(char) < 32 or ord(char) == 127 for char in path):
        return False
    parts = path.split("/")
    return all(part not in {"", ".", ".."} for part in parts)


def _int_or_none(value: Any) -> int | None:
    return max(0, value) if type(value) is int else None


@dataclass
class PRSnapshot:
    snapshot_id: str
    normalized_url: str
    owner: str
    repository: str
    number: int
    pull_request: dict
    changed_files: list[dict]
    changed_files_total: int | None
    changed_files_complete: bool
    limitation: str | None
    created_monotonic: float


class PRSnapshotCache:
    """Small TTL cache so file selection does not refetch PR metadata and pages."""

    def __init__(self, max_items: int = PR_SNAPSHOT_LIMIT, ttl_seconds: int = PR_SNAPSHOT_TTL_SECONDS):
        self.max_items = max_items
        self.ttl_seconds = ttl_seconds
        self._items: OrderedDict[str, PRSnapshot] = OrderedDict()
        self._lock = Lock()

    def put(self, snapshot: PRSnapshot) -> None:
        with self._lock:
            self._items[snapshot.snapshot_id] = snapshot
            self._items.move_to_end(snapshot.snapshot_id)
            self._purge()
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def get(self, snapshot_id: str) -> PRSnapshot | None:
        with self._lock:
            self._purge()
            snapshot = self._items.get(snapshot_id)
            if snapshot is not None:
                self._items.move_to_end(snapshot_id)
            return snapshot

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [key for key, item in self._items.items() if now - item.created_monotonic > self.ttl_seconds]
        for key in expired:
            self._items.pop(key, None)


pr_snapshot_cache = PRSnapshotCache()


class GitHubPRService(GitHubService):
    """Use fixed GitHub API paths; never clone, execute, or fetch arbitrary URLs."""

    def inspect_pr(self, url: str) -> PRSnapshot:
        owner, repository, number, normalized = parse_github_pr_url(url)
        repo_path = f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
        pr_path = f"{repo_path}/pulls/{number}"
        with self._client() as client:
            raw_pr = self._request_json(client, pr_path)
            if not isinstance(raw_pr, dict):
                raise GitHubIntegrationError(502, "GitHub returned invalid pull request metadata.")
            pull_request = self._normalize_pr(raw_pr, owner, repository, number)
            changed_files, total, complete = self._list_changed_files(client, pr_path, raw_pr)
        limitations = []
        if not complete:
            if total is not None and total > len(changed_files):
                limitations.append(f"GitHub reports {total} changed files, but only the first {len(changed_files)} are included in this review.")
            else:
                limitations.append("GitHub did not return a complete changed-file list; the review may omit files.")
        return PRSnapshot(
            snapshot_id=uuid4().hex,
            normalized_url=normalized,
            owner=owner,
            repository=repository,
            number=number,
            pull_request=pull_request,
            changed_files=changed_files,
            changed_files_total=total,
            changed_files_complete=complete,
            limitation=" ".join(limitations) or None,
            created_monotonic=time.monotonic(),
        )

    @staticmethod
    def _normalize_pr(raw: dict, owner: str, repository: str, number: int) -> dict:
        if raw.get("number") != number:
            raise GitHubIntegrationError(502, "GitHub returned pull request metadata for a different PR number.")
        head = raw.get("head") if isinstance(raw.get("head"), dict) else {}
        base = raw.get("base") if isinstance(raw.get("base"), dict) else {}
        head_sha = head.get("sha")
        base_sha = base.get("sha")
        if not isinstance(head_sha, str) or not _SHA_PATTERN.fullmatch(head_sha) or not isinstance(base_sha, str) or not _SHA_PATTERN.fullmatch(base_sha):
            raise GitHubIntegrationError(502, "GitHub did not provide valid pull request commit identifiers.")
        author_data = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        html_url = raw.get("html_url")
        expected_url = f"{GITHUB_WEB}/{owner}/{repository}/pull/{number}"
        if not isinstance(html_url, str) or html_url.rstrip("/").casefold() != expected_url.casefold():
            raise GitHubIntegrationError(502, "GitHub returned an invalid pull request link.")
        return {
            "number": number,
            "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
            "description": raw.get("body") if isinstance(raw.get("body"), str) else None,
            "author": author_data.get("login") if isinstance(author_data.get("login"), str) else None,
            "state": raw.get("state") if isinstance(raw.get("state"), str) else "unknown",
            "draft": raw.get("draft") if isinstance(raw.get("draft"), bool) else None,
            "html_url": html_url,
            "repository_full_name": f"{owner}/{repository}",
            "head_branch": head.get("ref") if isinstance(head.get("ref"), str) else None,
            "base_branch": base.get("ref") if isinstance(base.get("ref"), str) else None,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "created_at": raw.get("created_at") if isinstance(raw.get("created_at"), str) else None,
            "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
            "changed_files_total": _int_or_none(raw.get("changed_files")),
        }

    def _list_changed_files(self, client: httpx.Client, pr_path: str, raw_pr: dict) -> tuple[list[dict], int | None, bool]:
        reported_total = _int_or_none(raw_pr.get("changed_files"))
        entries: list[dict] = []
        expected_pages = min(MAX_PR_FILE_PAGES, max(1, (reported_total + 99) // 100)) if reported_total is not None else MAX_PR_FILE_PAGES
        pages_read = 0
        last_page_size = 0
        for page in range(1, expected_pages + 1):
            payload = self._request_json(
                client,
                f"{pr_path}/files",
                params={"per_page": 100, "page": page},
                max_response_bytes=MAX_PR_FILE_LIST_RESPONSE_BYTES,
                allow_list=True,
            )
            if not isinstance(payload, list):
                raise GitHubIntegrationError(502, "GitHub returned an invalid pull request file list.")
            pages_read += 1
            last_page_size = len(payload)
            for item in payload:
                if len(entries) >= MAX_PR_CHANGED_FILES:
                    break
                if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
                    continue
                filename = item["filename"]
                status = item.get("status") if isinstance(item.get("status"), str) else "unknown"
                is_python = filename.lower().endswith(".py")
                path_safe = _safe_repo_path(filename)
                extension = filename.rsplit(".", 1)[1].lower() if "." in filename.rsplit("/", 1)[-1] else ""
                entries.append({
                    "filename": filename,
                    "status": status,
                    "additions": _int_or_none(item.get("additions")) or 0,
                    "deletions": _int_or_none(item.get("deletions")) or 0,
                    "extension": extension,
                    "is_python": is_python,
                    "eligible_for_analysis": is_python and status in {"added", "modified", "renamed"} and path_safe,
                    "size": _int_or_none(item.get("size")),
                    "previous_filename": item.get("previous_filename") if isinstance(item.get("previous_filename"), str) else None,
                })
            if len(payload) < 100 or len(entries) >= MAX_PR_CHANGED_FILES:
                break

        limit_hit = len(entries) >= MAX_PR_CHANGED_FILES and (reported_total is None or reported_total > len(entries))
        pages_complete = pages_read < MAX_PR_FILE_PAGES or last_page_size < 100
        total_known = reported_total
        complete = not limit_hit and pages_complete and (total_known is None or len(entries) >= total_known)
        return entries, total_known, complete

    def analyze_pr(self, snapshot: PRSnapshot, selected_files: list[str] | None = None) -> dict:
        changed_python = [item for item in snapshot.changed_files if item["is_python"]]
        eligible_paths = [item["filename"] for item in changed_python if item["eligible_for_analysis"]]
        if selected_files is None:
            selected = eligible_paths[:MAX_PR_ANALYSIS_FILES]
        else:
            if len(selected_files) > MAX_PR_ANALYSIS_FILES:
                raise GitHubIntegrationError(422, f"Select no more than {MAX_PR_ANALYSIS_FILES} Python files per review.")
            if len(selected_files) != len(set(selected_files)):
                raise GitHubIntegrationError(422, "Selected file paths must be unique.")
            invalid = sorted(set(selected_files) - set(eligible_paths))
            if invalid:
                raise GitHubIntegrationError(422, "One or more selected paths are not eligible Python files in this pull request.")
            selected = selected_files

        selected_set = set(selected)
        changed_by_path = {item["filename"]: item for item in changed_python}
        analyzed_files = []
        skipped_by_path: dict[str, str] = {}
        selected_paths = list(selected)
        total_source_bytes = 0
        parsed_count = 0

        for item in changed_python:
            path = item["filename"]
            if item["status"] == "removed":
                skipped_by_path[path] = "File was removed by this pull request and does not exist at the PR head."
            elif not item["eligible_for_analysis"]:
                skipped_by_path[path] = "File path or change status is not supported for safe Python analysis."
            elif path not in selected_set:
                skipped_by_path[path] = "Not selected for this review."

        with self._client() as client:
            for path in selected:
                item = changed_by_path[path]
                reported_size = item.get("size")
                if reported_size is not None and reported_size > MAX_SOURCE_BYTES:
                    skipped_by_path[path] = f"File exceeds the {MAX_SOURCE_BYTES}-byte source limit."
                    continue
                if reported_size is not None and total_source_bytes + reported_size > MAX_PR_TOTAL_SOURCE_BYTES:
                    skipped_by_path[path] = "Review source data limit reached; this file was not fetched."
                    continue
                try:
                    source = self._fetch_source(client, snapshot, path)
                    encoded_size = len(source.encode("utf-8"))
                    if encoded_size > MAX_SOURCE_BYTES:
                        raise PRFileError(f"File exceeds the {MAX_SOURCE_BYTES}-byte source limit.")
                    if total_source_bytes + encoded_size > MAX_PR_TOTAL_SOURCE_BYTES:
                        raise PRFileError("Review source data limit reached; this file was not analyzed.")
                    total_source_bytes += encoded_size
                    report = analyze_source(source, path)
                except PRFileError as exc:
                    skipped_by_path[path] = str(exc)
                    continue
                except SourceTooLargeError:
                    skipped_by_path[path] = f"File exceeds the {MAX_SOURCE_BYTES}-byte source limit."
                    continue
                file_result = report["files"][0]
                file_result["file"] = path
                for issue in file_result["issues"]:
                    issue["file"] = path
                parse_error = file_result["parse_error"]
                if parse_error:
                    skipped_by_path[path] = "Source was retrieved but could not be parsed; see the file parse error."
                else:
                    parsed_count += 1
                analyzed_files.append({
                    "filename": path,
                    "source_code": source,
                    "parse_error": parse_error,
                    "issues": file_result["issues"],
                })

        if selected_files is None:
            for path in eligible_paths[MAX_PR_ANALYSIS_FILES:]:
                skipped_by_path.setdefault(path, f"The per-review analysis limit is {MAX_PR_ANALYSIS_FILES} Python files.")

        findings = [issue for file in analyzed_files for issue in file["issues"]]
        summary = {"critical": 0, "warning": 0, "info": 0}
        for issue in findings:
            if issue["severity"] in summary:
                summary[issue["severity"]] += 1
        parse_error_count = sum(file["parse_error"] is not None for file in analyzed_files)
        score = calculate_quality_score(findings, parse_error_count)
        changed_python_count = len(changed_python)
        coverage_percent = 100.0 if changed_python_count == 0 else round(parsed_count * 100 / changed_python_count, 1)
        skipped_files = [{"filename": path, "reason": reason} for path, reason in skipped_by_path.items()]
        changed_files = [
            {**item, "selected_for_analysis": item["filename"] in selected_set}
            for item in snapshot.changed_files
        ]
        coverage_complete = (
            snapshot.changed_files_complete
            and parsed_count == changed_python_count
            and not skipped_files
        )
        limitations = [text for text in [snapshot.limitation] if text]
        if eligible_paths and selected_files is None and len(eligible_paths) > MAX_PR_ANALYSIS_FILES:
            limitations.append(f"At most {MAX_PR_ANALYSIS_FILES} Python files are analyzed per request.")
        if changed_python_count and parsed_count < changed_python_count:
            limitations.append("Some changed Python files were not successfully parsed or analyzed; see skipped files and parse errors.")
        return {
            "pull_request": snapshot.pull_request,
            "changed_files": changed_files,
            "changed_files_total": snapshot.changed_files_total,
            "changed_files_complete": snapshot.changed_files_complete,
            "limitation": " ".join(limitations) or None,
            "selected_files": selected_paths,
            "skipped_files": skipped_files,
            "files": analyzed_files,
            "summary": summary,
            "total_findings": len(findings),
            "quality_score": score,
            "analysis_coverage": {
                "changed_python_files": changed_python_count,
                "python_file_count_complete": snapshot.changed_files_complete,
                "selected_python_files": len(selected),
                "analyzed_python_files": parsed_count,
                "skipped_python_files": len(skipped_files),
                "coverage_percent": coverage_percent,
                "complete": coverage_complete,
            },
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _fetch_source(self, client: httpx.Client, snapshot: PRSnapshot, path: str) -> str:
        if not _safe_repo_path(path):
            raise PRFileError("GitHub returned an unsafe repository path; this file was not fetched.")
        encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
        api_path = f"/repos/{quote(snapshot.owner, safe='')}/{quote(snapshot.repository, safe='')}/contents/{encoded_path}"
        try:
            payload = self._request_json(
                client,
                api_path,
                params={"ref": snapshot.pull_request["head_sha"]},
                max_response_bytes=2 * 1024 * 1024,
            )
        except GitHubIntegrationError as exc:
            if exc.status_code == 404:
                raise PRFileError("File is unavailable at the pull request head commit.") from exc
            if exc.status_code in {401, 403, 429}:
                raise
            raise PRFileError(exc.detail) from exc
        if not isinstance(payload, dict) or payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise PRFileError("File is binary or uses an unsupported GitHub content encoding.")
        content = payload.get("content")
        if not isinstance(content, str):
            raise PRFileError("GitHub did not provide readable file content.")
        try:
            source_bytes = base64.b64decode("".join(content.split()), validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise PRFileError("GitHub returned invalid encoded file content.") from exc
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise PRFileError(f"File exceeds the {MAX_SOURCE_BYTES}-byte source limit.")
        try:
            return source_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PRFileError("File is not valid UTF-8 and was not analyzed.") from exc
