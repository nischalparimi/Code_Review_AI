"""Offline unit and API tests for the read-only GitHub integration."""

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, get_github_pr_service, get_github_service
from backend.app.services.github_service import GitHubIntegrationError, GitHubService, parse_github_repository_url


def api_response(handler, *, token=None, file_limit=1000):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GitHubService(client=client, token=token, file_limit=file_limit), client


def repository_payload(**overrides):
    payload = {
        "name": "demo", "full_name": "owner/demo", "owner": {"login": "owner"},
        "description": "A sample project", "html_url": "https://github.com/owner/demo",
        "default_branch": "main", "visibility": "public", "private": False,
        "stargazers_count": 12, "fork": True, "updated_at": "2026-01-01T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_parse_github_urls_and_normalize_trailing_slashes():
    assert parse_github_repository_url("https://github.com/owner/demo/") == (
        "owner", "demo", "https://github.com/owner/demo"
    )
    assert parse_github_repository_url("https://github.com/Owner/repo_name")[:2] == ("Owner", "repo_name")


@pytest.mark.parametrize("url", [
    "http://github.com/owner/repo", "https://notgithub.com/owner/repo",
    "https://github.com/owner", "https://github.com/owner/", "https://github.com/",
    "https://github.com/owner/repo/issues", "https://github.com/owner/repo/tree/main",
    "https://gist.github.com/owner/hash", "https://github.com/owner/repo?tab=readme",
    "https://github.com//owner/repo", "https://user@github.com/owner/repo",
    "https://github.com/owner/%2e%2e",
])
def test_rejects_non_repository_or_unsafe_urls(url):
    with pytest.raises(GitHubIntegrationError) as error:
        parse_github_repository_url(url)
    assert error.value.status_code == 422


def test_metadata_returns_only_selected_github_fields_and_handles_missing_optional_data():
    payload = repository_payload(description=None, visibility=None, updated_at=None, fork=False)
    service, client = api_response(lambda request: httpx.Response(200, json=payload))
    try:
        result = service.get_repository("https://github.com/owner/demo/")
    finally:
        client.close()
    assert result == {
        "normalized_url": "https://github.com/owner/demo", "name": "demo", "full_name": "owner/demo",
        "owner": "owner", "description": None, "html_url": "https://github.com/owner/demo",
        "default_branch": "main", "visibility": None, "private": False,
        "stargazers_count": 12, "fork": False, "updated_at": None,
    }


def test_service_reads_optional_token_from_backend_environment(monkeypatch):
    seen = []
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_backend_only")
    service, client = api_response(lambda request: (seen.append(request.headers.get("Authorization")) or httpx.Response(200, json=repository_payload())))
    try:
        service.get_repository("https://github.com/owner/demo")
    finally:
        client.close()
    assert seen == ["Bearer ghp_backend_only"]


def test_public_api_service_factories_ignore_backend_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_must_not_be_used_by_public_routes")
    assert "Authorization" not in get_github_service()._headers()
    assert "Authorization" not in get_github_pr_service()._headers()


def test_repository_not_found_is_readable():
    service, client = api_response(lambda request: httpx.Response(404, json={"message": "Not Found"}))
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_repository("https://github.com/owner/missing")
    finally:
        client.close()
    assert error.value.status_code == 404
    assert "not found or inaccessible" in error.value.detail


def test_authentication_errors_are_clear_and_never_expose_token():
    secret = "ghp_TEST_SECRET_NEVER_RETURN"
    seen_headers = []

    def handler(request):
        seen_headers.append(request.headers.get("Authorization"))
        return httpx.Response(401, json={"message": f"Bad credentials {secret}"})

    service, client = api_response(handler, token=secret)
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_repository("https://github.com/owner/demo")
    finally:
        client.close()
    assert seen_headers == [f"Bearer {secret}"]
    assert error.value.status_code == 502
    assert secret not in error.value.detail


def test_rate_limit_errors_are_returned_without_retrying():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"}, json={"message": "API rate limit exceeded"})

    service, client = api_response(handler)
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_repository("https://github.com/owner/demo")
    finally:
        client.close()
    assert error.value.status_code == 429
    assert "rate limit" in error.value.detail.lower()
    assert len(calls) == 1


def test_timeout_maps_to_gateway_timeout():
    service, client = api_response(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("private detail", request=request)))
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_repository("https://github.com/owner/demo")
    finally:
        client.close()
    assert error.value.status_code == 504
    assert "timed out" in error.value.detail


def test_file_listing_filters_blobs_preserves_nested_paths_and_uses_default_branch():
    requested = []

    def handler(request):
        requested.append(request.url)
        if request.url.path.endswith("/git/trees/main"):
            return httpx.Response(200, json={"truncated": False, "tree": [
                {"path": "src/pkg/check.py", "type": "blob"},
                {"path": "root.py", "type": "blob"},
                {"path": "readme.md", "type": "blob"},
                {"path": "directory.py", "type": "tree"},
                {"path": "src/UPPER.PY", "type": "blob"},
            ]})
        return httpx.Response(200, json=repository_payload())

    service, client = api_response(handler)
    try:
        result = service.get_python_files("https://github.com/owner/demo")
    finally:
        client.close()
    assert result["python_files"] == ["src/pkg/check.py", "root.py", "src/UPPER.PY"]
    assert result["total_python_files"] == 3
    assert result["default_branch"] == "main"
    assert requested[1].params["recursive"] == "1"
    assert result["truncated"] is False


def test_truncated_tree_is_never_reported_as_complete():
    def handler(request):
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"truncated": True, "tree": [{"path": "visible.py", "type": "blob"}]})
        return httpx.Response(200, json=repository_payload())

    service, client = api_response(handler)
    try:
        result = service.get_python_files("https://github.com/owner/demo")
    finally:
        client.close()
    assert result["total_python_files"] is None
    assert result["truncated"] is True
    assert "incomplete" in result["limitation"]


def test_python_file_display_limit_is_bounded_and_communicated():
    def handler(request):
        if "/git/trees/" in request.url.path:
            tree = [{"path": f"pkg/file_{index}.py", "type": "blob"} for index in range(8)]
            return httpx.Response(200, json={"truncated": False, "tree": tree})
        return httpx.Response(200, json=repository_payload())

    service, client = api_response(handler, file_limit=3)
    try:
        result = service.get_python_files("https://github.com/owner/demo")
    finally:
        client.close()
    assert len(result["python_files"]) == 3
    assert result["total_python_files"] == 8
    assert result["file_list_limited"] is True
    assert "first 3" in result["limitation"]


def test_oversized_tree_response_is_rejected_safely(monkeypatch):
    from backend.app.services import github_service

    monkeypatch.setattr(github_service, "MAX_GITHUB_RESPONSE_BYTES", 32)

    def handler(request):
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": [{"path": "x" * 100, "type": "blob"}], "truncated": False})
        return httpx.Response(200, json=repository_payload())

    service, client = api_response(handler)
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_python_files("https://github.com/owner/demo")
    finally:
        client.close()
    assert error.value.status_code == 502
    assert "size limit" in error.value.detail


def test_default_branch_tree_404_is_explained():
    def handler(request):
        if "/git/trees/" in request.url.path:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json=repository_payload())

    service, client = api_response(handler)
    try:
        with pytest.raises(GitHubIntegrationError) as error:
            service.get_python_files("https://github.com/owner/demo")
    finally:
        client.close()
    assert error.value.status_code == 404
    assert "default branch" in error.value.detail


def test_api_endpoints_return_repository_and_files_and_do_not_expose_token():
    secret = "ghp_TEST_SECRET_NEVER_RETURN"

    def handler(request):
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"truncated": False, "tree": [{"path": "app.py", "type": "blob"}]})
        return httpx.Response(200, json=repository_payload())

    service, mocked_client = api_response(handler, token=secret)
    app.dependency_overrides[get_github_service] = lambda: service
    try:
        test_client = TestClient(app)
        repo_response = test_client.get("/api/github/repository", params={"url": "https://github.com/owner/demo/"})
        files_response = test_client.get("/api/github/files", params={"url": "https://github.com/owner/demo"})
        assert repo_response.status_code == 200
        assert repo_response.json()["full_name"] == "owner/demo"
        assert "Authorization" not in str(repo_response.json())
        assert secret not in str(files_response.json())
        assert files_response.json()["python_files"] == ["app.py"]
    finally:
        app.dependency_overrides.clear()
        mocked_client.close()


def test_api_rejects_invalid_url_and_redacts_auth_failure():
    secret = "ghp_TEST_SECRET_NEVER_RETURN"
    service, mocked_client = api_response(lambda request: httpx.Response(401, json={"message": "Bad credentials"}), token=secret)
    app.dependency_overrides[get_github_service] = lambda: service
    try:
        test_client = TestClient(app)
        invalid = test_client.get("/api/github/repository", params={"url": "https://example.com/owner/repo"})
        denied = test_client.get("/api/github/repository", params={"url": "https://github.com/owner/repo"})
    finally:
        app.dependency_overrides.clear()
        mocked_client.close()
    assert invalid.status_code == 422
    assert denied.status_code == 502
    assert secret not in denied.text
