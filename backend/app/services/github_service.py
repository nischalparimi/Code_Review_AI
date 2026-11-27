"""Safe, read-only access to GitHub repository metadata and file trees."""

from contextlib import contextmanager
import json
import os
import re
from typing import Iterator
from urllib.parse import quote, unquote, urlsplit

import httpx

GITHUB_API = "https://api.github.com"
GITHUB_WEB = "https://github.com"
GITHUB_API_VERSION = "2022-11-28"
REQUEST_TIMEOUT_SECONDS = 8.0
MAX_GITHUB_RESPONSE_BYTES = 20 * 1024 * 1024
MAX_PYTHON_FILES = 1000

_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class GitHubIntegrationError(Exception):
    """A safe, user-facing error from GitHub URL or API handling."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def parse_github_repository_url(url: str) -> tuple[str, str, str]:
    """Validate a GitHub repository page URL and return owner, repo, canonical URL."""
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise GitHubIntegrationError(422, "Enter a valid GitHub repository URL.")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as exc:
        raise GitHubIntegrationError(422, "Enter a valid GitHub repository URL.") from exc
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
    ):
        raise GitHubIntegrationError(422, "Only https://github.com/owner/repository URLs are supported.")

    if not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise GitHubIntegrationError(422, "Enter a repository URL with exactly an owner and repository name.")
    path = parsed.path
    if path.endswith("/"):
        path = path[:-1]
    parts = path.lstrip("/").split("/")
    if len(parts) != 2:
        raise GitHubIntegrationError(422, "Enter a repository URL with exactly an owner and repository name.")
    owner, repository = parts
    if (
        not _OWNER_PATTERN.fullmatch(owner)
        or len(repository) > 100
        or not _REPOSITORY_PATTERN.fullmatch(repository)
        or repository in {".", ".."}
    ):
        raise GitHubIntegrationError(422, "The GitHub owner or repository name is invalid.")
    return owner, repository, f"{GITHUB_WEB}/{owner}/{repository}"


class GitHubService:
    """Fetch allow-listed GitHub API resources without cloning or reading file contents."""

    def __init__(self, client: httpx.Client | None = None, token: str | None = None, timeout: float = REQUEST_TIMEOUT_SECONDS, file_limit: int = MAX_PYTHON_FILES):
        self._provided_client = client
        self._token = token
        self.timeout = timeout
        self.file_limit = max(1, min(int(file_limit), MAX_PYTHON_FILES))

    @contextmanager
    def _client(self) -> Iterator[httpx.Client]:
        if self._provided_client is not None:
            yield self._provided_client
            return
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            yield client

    def _headers(self) -> dict[str, str]:
        token = self._token if self._token is not None else os.environ.get("GITHUB_TOKEN")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": "CodeReview-AI",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request_json(self, client: httpx.Client, path: str, params: dict | None = None, *, tree: bool = False, max_response_bytes: int | None = None, allow_list: bool = False):
        url = f"{GITHUB_API}{path}"
        limit = max_response_bytes or (MAX_GITHUB_RESPONSE_BYTES if tree else 2 * 1024 * 1024)
        body = bytearray()
        try:
            with client.stream("GET", url, params=params, headers=self._headers()) as response:
                if response.status_code >= 400:
                    error_body = bytearray()
                    for chunk in response.iter_bytes():
                        error_body.extend(chunk)
                        if len(error_body) > 65_536:
                            break
                    error = self._http_error(response, bytes(error_body))
                    if response.status_code == 404 and "/git/trees/" in path:
                        error.detail = "The repository's default branch or its file tree could not be found."
                    raise error
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise GitHubIntegrationError(502, "GitHub returned a response that exceeds the safe size limit.")
        except httpx.TimeoutException as exc:
            raise GitHubIntegrationError(504, "The GitHub request timed out. Try again later.") from exc
        except httpx.RequestError as exc:
            raise GitHubIntegrationError(502, "Could not connect to the GitHub API. Try again later.") from exc
        try:
            payload = httpx.Response(200, content=bytes(body)).json()
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubIntegrationError(502, "GitHub returned an invalid API response.") from exc
        if not isinstance(payload, dict) and not (allow_list and isinstance(payload, list)):
            raise GitHubIntegrationError(502, "GitHub returned an invalid API response.")
        return payload

    @staticmethod
    def _http_error(response: httpx.Response, body: bytes = b"") -> GitHubIntegrationError:
        status = response.status_code
        remaining = response.headers.get("X-RateLimit-Remaining")
        retry_after = response.headers.get("Retry-After")
        try:
            message = str(json.loads(body).get("message", "")).lower()
        except (ValueError, AttributeError, TypeError):
            message = ""
        if status in {403, 429} and (status == 429 or remaining == "0" or "rate limit" in message):
            extra = f" Retry after {retry_after} seconds." if retry_after and retry_after.isdigit() else ""
            return GitHubIntegrationError(429, f"GitHub API rate limit reached.{extra}")
        if status == 401:
            return GitHubIntegrationError(502, "GitHub authentication failed. Check the backend GITHUB_TOKEN configuration.")
        if status == 404:
            return GitHubIntegrationError(404, "Repository not found or inaccessible. Private repositories require a valid backend token with repository read access.")
        if status == 403:
            return GitHubIntegrationError(403, "GitHub denied access. For a private repository, configure GITHUB_TOKEN with read-only repository access.")
        if status in {408, 504}:
            return GitHubIntegrationError(504, "The GitHub request timed out. Try again later.")
        return GitHubIntegrationError(502, "The GitHub API could not complete the repository request.")

    @staticmethod
    def _repository_payload(payload: dict, owner: str, repository: str) -> dict:
        owner_data = payload.get("owner") if isinstance(payload.get("owner"), dict) else {}
        name = payload.get("name")
        full_name = payload.get("full_name")
        github_owner = owner_data.get("login")
        html_url = payload.get("html_url")
        default_branch = payload.get("default_branch")
        is_private = payload.get("private")
        if not all(isinstance(value, str) and value for value in (name, full_name, github_owner, html_url, default_branch)):
            raise GitHubIntegrationError(502, "GitHub omitted required repository metadata.")
        if not isinstance(is_private, bool):
            raise GitHubIntegrationError(502, "GitHub omitted the repository visibility status.")
        try:
            parsed_html_url = urlsplit(html_url)
        except ValueError as exc:
            raise GitHubIntegrationError(502, "GitHub returned an invalid repository link.") from exc
        returned_path = [unquote(part) for part in parsed_html_url.path.strip("/").split("/")]
        if (
            parsed_html_url.scheme != "https"
            or parsed_html_url.hostname != "github.com"
            or parsed_html_url.netloc.lower() != "github.com"
            or len(returned_path) != 2
            or returned_path[0].casefold() != owner.casefold()
            or returned_path[1].casefold() != repository.casefold()
        ):
            raise GitHubIntegrationError(502, "GitHub returned an invalid repository link.")
        stars_value = payload.get("stargazers_count")
        stars = max(0, stars_value) if type(stars_value) is int else None
        fork = payload.get("fork") if isinstance(payload.get("fork"), bool) else None
        return {
            "name": name,
            "full_name": full_name,
            "owner": github_owner,
            "description": payload.get("description") if isinstance(payload.get("description"), str) else None,
            "html_url": html_url,
            "default_branch": default_branch,
            "visibility": payload.get("visibility") if isinstance(payload.get("visibility"), str) else None,
            "private": is_private,
            "stargazers_count": stars,
            "fork": fork,
            "updated_at": payload.get("updated_at") if isinstance(payload.get("updated_at"), str) else None,
        }

    def _get_repository(self, client: httpx.Client, owner: str, repository: str) -> dict:
        path = f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}"
        raw = self._request_json(client, path)
        data = self._repository_payload(raw, owner, repository)
        return data

    def get_repository(self, url: str) -> dict:
        owner, repository, normalized_url = parse_github_repository_url(url)
        with self._client() as client:
            data = self._get_repository(client, owner, repository)
        return {"normalized_url": normalized_url, **data}

    def get_python_files(self, url: str) -> dict:
        owner, repository, normalized_url = parse_github_repository_url(url)
        with self._client() as client:
            repo = self._get_repository(client, owner, repository)
            path = f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/git/trees/{quote(repo['default_branch'], safe='')}"
            tree_data = self._request_json(client, path, params={"recursive": "1"}, tree=True)

        tree = tree_data.get("tree")
        if not isinstance(tree, list):
            raise GitHubIntegrationError(502, "GitHub returned an invalid repository file tree.")
        python_paths = [
            item["path"] for item in tree
            if isinstance(item, dict)
            and item.get("type") == "blob"
            and isinstance(item.get("path"), str)
            and item["path"].lower().endswith(".py")
        ]
        truncated = bool(tree_data.get("truncated"))
        limited = len(python_paths) > self.file_limit
        files = python_paths[:self.file_limit]
        limitations = []
        if truncated:
            limitations.append("GitHub truncated this repository tree; the Python file list may be incomplete.")
        if limited:
            limitations.append(f"Only the first {self.file_limit} Python files are shown.")
        return {
            "normalized_url": normalized_url,
            "repository": {"normalized_url": normalized_url, **repo},
            "default_branch": repo["default_branch"],
            "total_python_files": None if truncated else len(python_paths),
            "python_files": files,
            "truncated": truncated,
            "file_list_limited": limited,
            "file_limit": self.file_limit,
            "limitation": " ".join(limitations) or None,
        }
