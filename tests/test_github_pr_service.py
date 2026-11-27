"""Offline tests for pull request inspection and static analysis."""

import base64

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, get_github_pr_service
from backend.app.services.github_pr_service import (
    GitHubPRService,
    PRSnapshotCache,
    parse_github_pr_url,
    pr_snapshot_cache,
)
from backend.app.services.github_service import GitHubIntegrationError

URL = "https://github.com/octo/demo/pull/12"
HEAD = "a" * 40
BASE = "b" * 40


def pr_payload(**overrides):
    payload = {
        "number": 12, "title": "Improve parser", "body": "Review this change", "state": "open",
        "draft": False, "html_url": URL, "user": {"login": "octocat"},
        "head": {"ref": "feature/parser", "sha": HEAD},
        "base": {"ref": "main", "sha": BASE},
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z",
        "changed_files": 1,
    }
    payload.update(overrides)
    return payload


def pr_file(path, status="modified", size=25, **overrides):
    item = {"filename": path, "status": status, "additions": 2, "deletions": 1, "size": size}
    item.update(overrides)
    return item


def encoded_source(source):
    return base64.b64encode(source.encode("utf-8")).decode("ascii")


def service_for(handler, token=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GitHubPRService(client=client, token=token), client


def test_parse_supported_pr_url_and_normalize_trailing_slash():
    assert parse_github_pr_url("https://github.com/octo/demo/pull/12/") == (
        "octo", "demo", 12, URL,
    )


@pytest.mark.parametrize("url", [
    "http://github.com/octo/demo/pull/12", "https://example.com/octo/demo/pull/12",
    "https://github.com/octo", "https://github.com/octo/demo", "https://github.com/octo/demo/pull/0",
    "https://github.com/octo/demo/pull/nope", "https://github.com/octo/demo/pulls/12",
    "https://github.com/octo/demo/issues/12", "https://gist.github.com/octo/hash/pull/12",
    "https://api.github.com/repos/octo/demo/pulls/12", "https://github.com/octo/demo/pull/12/files",
    "https://github.com/octo/demo/pull/12?tab=files", "https://github.com//octo/demo/pull/12",
    "https://github.com/octo/demo/pull/١٢",
])
def test_reject_invalid_pr_urls(url):
    with pytest.raises(GitHubIntegrationError) as error:
        parse_github_pr_url(url)
    assert error.value.status_code == 422


def test_inspect_returns_actual_metadata_and_changed_files():
    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file("src/parser.py", "renamed", previous_filename="parser.py")])
        return httpx.Response(200, json=pr_payload())

    service, client = service_for(handler)
    try:
        snapshot = service.inspect_pr(URL)
    finally:
        client.close()
    assert snapshot.pull_request == {
        "number": 12, "title": "Improve parser", "description": "Review this change", "author": "octocat",
        "state": "open", "draft": False, "html_url": URL, "repository_full_name": "octo/demo",
        "head_branch": "feature/parser", "base_branch": "main", "head_sha": HEAD, "base_sha": BASE,
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z", "changed_files_total": 1,
    }
    assert snapshot.changed_files[0]["filename"] == "src/parser.py"
    assert snapshot.changed_files[0]["previous_filename"] == "parser.py"
    assert snapshot.changed_files[0]["eligible_for_analysis"] is True


def test_pr_not_found_private_auth_rate_limit_and_timeout():
    for response, expected_status, expected_phrase in [
        (httpx.Response(404, json={"message": "Not Found"}), 404, "not found or inaccessible"),
        (httpx.Response(401, json={"message": "Bad credentials"}), 502, "authentication failed"),
        (httpx.Response(403, headers={"X-RateLimit-Remaining": "0"}, json={"message": "API rate limit exceeded"}), 429, "rate limit"),
    ]:
        service, client = service_for(lambda request, response=response: response)
        try:
            with pytest.raises(GitHubIntegrationError) as error:
                service.inspect_pr(URL)
        finally:
            client.close()
        assert error.value.status_code == expected_status
        assert expected_phrase in error.value.detail.lower()

    service, client = service_for(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("private timeout", request=request)))
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.inspect_pr(URL)
    finally:
        client.close()
    assert error.value.status_code == 504
    assert "private timeout" not in error.value.detail


def test_pagination_and_file_type_status_classification():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/files"):
            if request.url.params.get("page") == "1":
                return httpx.Response(200, json=[pr_file(f"pkg/file_{index}.py") for index in range(100)])
            return httpx.Response(200, json=[
                pr_file("README.md"), pr_file("removed.py", "removed"),
                pr_file("new.py", "added"), pr_file("renamed.py", "renamed"),
            ])
        return httpx.Response(200, json=pr_payload(changed_files=104))

    service, client = service_for(handler)
    try:
        snapshot = service.inspect_pr(URL)
    finally:
        client.close()
    assert len(snapshot.changed_files) == 104
    assert snapshot.changed_files_complete is True
    assert snapshot.changed_files[100]["is_python"] is False
    assert snapshot.changed_files[101]["eligible_for_analysis"] is False
    assert snapshot.changed_files[102]["eligible_for_analysis"] is True
    assert snapshot.changed_files[103]["eligible_for_analysis"] is True
    assert requests[1].url.params["page"] == "1"
    assert requests[2].url.params["page"] == "2"


def test_changed_file_list_limit_is_marked_incomplete():
    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file(f"src/{request.url.params['page']}_{index}.py") for index in range(100)])
        return httpx.Response(200, json=pr_payload(changed_files=450))

    service, client = service_for(handler)
    try:
        snapshot = service.inspect_pr(URL)
    finally:
        client.close()
    assert len(snapshot.changed_files) == 300
    assert snapshot.changed_files_complete is False
    assert "450 changed files" in snapshot.limitation


def test_source_uses_validated_head_ref_and_existing_analyzer_and_score():
    requested_content = []
    sources = {"one.py": "x = eval('1')\n", "two.py": "first = eval('1')\nsecond = eval('2')\n"}

    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file(path, size=len(source)) for path, source in sources.items()])
        if "/contents/" in request.url.path:
            requested_content.append(request)
            path = request.url.path.rsplit("/contents/", 1)[1]
            return httpx.Response(200, json={"type": "file", "encoding": "base64", "content": encoded_source(sources[path])})
        return httpx.Response(200, json=pr_payload(changed_files=2))

    service, client = service_for(handler)
    try:
        snapshot = service.inspect_pr(URL)
        result = service.analyze_pr(snapshot)
    finally:
        client.close()
    assert [request.url.params["ref"] for request in requested_content] == [HEAD, HEAD]
    assert result["summary"] == {"critical": 3, "warning": 0, "info": 0}
    assert result["total_findings"] == 3
    assert result["quality_score"]["score"] == 55
    assert result["quality_score"]["severity_counts"] == result["summary"]
    assert {issue["file"] for file in result["files"] for issue in file["issues"]} == {"one.py", "two.py"}
    assert result["analysis_coverage"]["complete"] is True


@pytest.mark.parametrize("status,encoding,content,expected", [
    ("removed", "base64", encoded_source("pass\n"), "removed by this pull request"),
    ("modified", "none", "", "binary or uses an unsupported"),
    ("modified", "base64", base64.b64encode(b"\xff").decode("ascii"), "not valid UTF-8"),
])
def test_removed_binary_and_invalid_utf8_files_are_skipped(status, encoding, content, expected):
    calls = []

    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file("bad.py", status)])
        if "/contents/" in request.url.path:
            calls.append(request)
            return httpx.Response(200, json={"type": "file", "encoding": encoding, "content": content})
        return httpx.Response(200, json=pr_payload())

    service, client = service_for(handler)
    try:
        result = service.analyze_pr(service.inspect_pr(URL))
    finally:
        client.close()
    assert result["files"] == []
    assert expected in result["skipped_files"][0]["reason"]
    assert not calls if status == "removed" else calls


def test_large_source_is_skipped_before_fetch_and_unselected_files_are_visible():
    requested = []

    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file("large.py", size=2_000_000), pr_file("other.py", size=5)])
        if "/contents/" in request.url.path:
            requested.append(request)
            return httpx.Response(200, json={"type": "file", "encoding": "base64", "content": encoded_source("pass\n")})
        return httpx.Response(200, json=pr_payload(changed_files=2))

    service, client = service_for(handler)
    try:
        snapshot = service.inspect_pr(URL)
        result = service.analyze_pr(snapshot, ["other.py"])
    finally:
        client.close()
    assert len(requested) == 1
    assert "Not selected" in result["skipped_files"][0]["reason"] or "exceeds" in result["skipped_files"][0]["reason"]
    assert result["analysis_coverage"]["complete"] is False


def test_no_python_changes_returns_empty_findings_and_full_neutral_score():
    def handler(request):
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file("README.md"), pr_file("image.png", "added")])
        return httpx.Response(200, json=pr_payload(changed_files=2))

    service, client = service_for(handler)
    try:
        result = service.analyze_pr(service.inspect_pr(URL))
    finally:
        client.close()
    assert result["files"] == []
    assert result["total_findings"] == 0
    assert result["quality_score"]["score"] == 100
    assert result["analysis_coverage"]["changed_python_files"] == 0


def test_file_count_and_total_source_limits_and_invalid_selection():
    from backend.app.services import github_pr_service

    monkeypatch_limit = github_pr_service.MAX_SOURCE_BYTES
    github_pr_service.MAX_SOURCE_BYTES = 4
    try:
        def handler(request):
            if request.url.path.endswith("/files"):
                return httpx.Response(200, json=[pr_file("large.py", size=5)])
            return httpx.Response(200, json=pr_payload())

        service, client = service_for(handler)
        try:
            snapshot = service.inspect_pr(URL)
            result = service.analyze_pr(snapshot)
            with pytest.raises(GitHubIntegrationError):
                service.analyze_pr(snapshot, ["outside.py"])
        finally:
            client.close()
    finally:
        github_pr_service.MAX_SOURCE_BYTES = monkeypatch_limit
    assert "source limit" in result["skipped_files"][0]["reason"]


def test_snapshot_cache_expiration_and_bounded_lifetime(monkeypatch):
    now = [10.0]
    monkeypatch.setattr("backend.app.services.github_pr_service.time.monotonic", lambda: now[0])
    cache = PRSnapshotCache(max_items=1, ttl_seconds=5)
    service, client = service_for(lambda request: httpx.Response(200, json=[] if request.url.path.endswith("/files") else pr_payload()))
    try:
        snapshot = service.inspect_pr(URL)
    finally:
        client.close()
    cache.put(snapshot)
    assert cache.get(snapshot.snapshot_id) is snapshot
    now[0] = 16.0
    assert cache.get(snapshot.snapshot_id) is None


def test_api_inspection_snapshot_analyzes_selected_files_without_refetching_metadata():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json=[pr_file("safe.py", size=6)])
        if "/contents/" in request.url.path:
            return httpx.Response(200, json={"type": "file", "encoding": "base64", "content": encoded_source("pass\n")})
        return httpx.Response(200, json=pr_payload())

    service, mocked_client = service_for(handler)
    app.dependency_overrides[get_github_pr_service] = lambda: service
    pr_snapshot_cache.clear()
    try:
        test_client = TestClient(app)
        inspected = test_client.post("/api/github/pr/inspect", json={"url": URL})
        analyzed = test_client.post("/api/github/pr/analyze", json={
            "url": URL, "snapshot_id": inspected.json()["snapshot_id"], "selected_files": ["safe.py"],
        })
    finally:
        app.dependency_overrides.clear()
        pr_snapshot_cache.clear()
        mocked_client.close()
    assert inspected.status_code == 200
    assert analyzed.status_code == 200
    assert analyzed.json()["selected_files"] == ["safe.py"]
    assert analyzed.json()["quality_score"]["score"] == 100
    assert seen.count(f"/repos/octo/demo/pulls/12") == 1
    assert sum(path.endswith("/files") for path in seen) == 1


def test_api_rejects_invalid_url_and_redacts_token_from_errors():
    secret = "ghp_PRIVATE_PHASE_52_TOKEN"
    service, mocked_client = service_for(lambda request: httpx.Response(401, json={"message": f"Bad credentials {secret}"}), token=secret)
    app.dependency_overrides[get_github_pr_service] = lambda: service
    try:
        test_client = TestClient(app)
        invalid = test_client.post("/api/github/pr/inspect", json={"url": "https://github.com/octo/demo"})
        denied = test_client.post("/api/github/pr/inspect", json={"url": URL})
    finally:
        app.dependency_overrides.clear()
        mocked_client.close()
    assert invalid.status_code == 422
    assert denied.status_code == 502
    assert secret not in denied.text
