# Automated Code Review and Static Analysis System

A lightweight static analysis engine that scans Python source code for
style violations, common bug patterns, and basic security issues — the
core prototype for the Capstone-1 deliverable.

## What it checks right now

| Rule ID | Severity | Category | Description |
|---|---|---|---|
| STYLE001 | info | Style | Line exceeds 100 characters |
| STYLE002 | info | Style | Public function/class missing a docstring |
| BUG001 | warning | Bug | Bare `except:` clause |
| BUG002 | warning | Bug | Mutable default argument (list/dict/set) |
| SEC001 | critical | Security | Use of `eval()` / `exec()` |
| SEC002 | critical | Security | Possible hardcoded credential based on variable name or recognizable key format |
| SMELL001 | info | Smell | Function has more than five positional parameters |
| MAINT001 | info | Maintainability | Unresolved `TODO` / `FIXME` comment |
| SEC003 | critical | Security | `shell=True` or suspicious dynamic command passed to subprocess |
| SEC004 | warning | Security | Use of weak MD5/SHA-1 hashing APIs |
| SEC005 | critical | Security | Dynamic SQL construction passed to `execute()` / `executemany()` |
| MAINT002 | info | Maintainability | Imported name has no apparent module reference |
| SMELL002 | warning | Smell | Function has control-flow nesting deeper than four levels |
| SMELL003 | warning | Smell | Approximate cyclomatic complexity exceeds ten |

Rules implement the shared `Rule` interface in `analyzer/base.py` and are
registered in `analyzer/rules.py`; advanced security and maintainability rules
are kept in `analyzer/advanced_rules.py`.

## Project structure

```
code-review-engine/
├── analyzer/
│   ├── __init__.py
│   ├── rules.py      # all rule definitions
│   ├── engine.py      # file discovery + AST parsing + rule execution
│   └── report.py      # console and JSON report formatting
├── cli.py              # command-line entry point
├── samples/
│   ├── bad_example.py   # intentionally flawed file used for testing/demo
│   └── good_example.py  # clean file, should report zero issues
├── tests/
│   └── test_engine.py  # automated test suite (pytest)
└── requirements.txt
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Analyze a single file or a whole directory:

```bash
python cli.py samples/bad_example.py
python cli.py samples/
```

Write a JSON report (for future CI/dashboard integration):

```bash
python cli.py samples/ --json report.json
```

Control which severities fail the build (the CI "quality gate"):

```bash
python cli.py samples/ --fail-on critical,warning
```

Generate a visual summary chart (issues by severity + by category) as a PNG:

```bash
python cli.py samples/bad_example.py --chart report_chart.png
```

Exercise several advanced rules with the intentionally flawed static-analysis
sample (the quality gate is expected to fail):

```bash
python cli.py samples/advanced_example.py --fail-on critical,warning
```

Exit code is `0` if the quality gate passes, `1` if it fails — this is
what a CI/CD pipeline stage checks to decide whether to block a merge.

## Running the tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Quality scoring

The API adds a deterministic quality score to each analysis response. Scoring starts at 100, subtracts 15 points for each critical finding, 5 for each warning, and 1 for each informational finding, then clamps the result at zero. Grades are A (90–100, Excellent), B (75–89, Good), C (60–74, Fair), D (40–59, Poor), and F (0–39, Critical). For example, two critical findings, three warnings, and four informational findings produce 100 − 30 − 15 − 4 = 51 (D, Poor).

The score aggregates findings from the full analysis response and does not change the independent quality gate, which still uses the requested `fail_on` severities to decide pass/fail. Parse errors are reported separately and do not incur a finding penalty; a result with parse errors includes an explanation so the score is not mistaken for a complete review. The score is a heuristic based on the findings this static analyzer currently detects. It is not proof that code is secure or bug-free, nor a substitute for review. The CLI's existing report and behavior are unchanged.

The React dashboard displays each result's score and keeps score history for analyses in the current browser session. History is not persisted after the session ends.

## Phase 4.3: inline source review and fix suggestions

Analysis results retain the submitted source in frontend session memory and show it in a read-only, line-numbered code viewer. Findings are highlighted by their analyzer-provided severity, and selecting a finding navigates to its source line, shows the relevant snippet and details, and keeps the existing analyzer remediation visible. Filtered findings do not change the quality score or the selected finding identity.

Rule-based guidance is provided for the existing analyzer rule IDs. A limited before/after example is shown for hardcoded credential assignments; other cases receive contextual guidance when a reliable general replacement cannot be derived. SQL parameter syntax depends on the database driver, and subprocess examples are not treated as universal replacements. Unknown rules use their analyzer remediation when available, otherwise a general fallback.

Suggestions are informational only: the viewer renders source as text, no submitted code or suggestion is executed, and the application never applies edits automatically. Suggestions are not guaranteed fixes and should be reviewed and tested by a developer. Saved results without retained source can still show finding details, but cannot navigate to or preview the original source.

## Phase 5.1: GitHub repository browser

The GitHub page accepts repository page URLs in the form `https://github.com/owner/repository` (a trailing slash is allowed). It uses GitHub's REST API to show repository metadata and list Python file paths from the default branch. It does not fetch file contents, clone repositories, or analyze repository code in this phase.

Public repositories work without credentials. Private repository access is
disabled on the unauthenticated public API, even if `GITHUB_TOKEN` happens to
be present in the backend environment. Do not configure a token until
authenticated and repository-authorized access has been implemented.

Start the backend as usual:

```powershell
python -m uvicorn backend.app.main:app --reload
```

The repository endpoints are `GET /api/github/repository?url=<repository-url>` and `GET /api/github/files?url=<repository-url>`. The file-list endpoint returns up to 1,000 paths. GitHub may truncate very large recursive trees; the response marks this and reports that the list may be incomplete. Rate limits are imposed by GitHub and depend on authentication and current account/IP usage; consult [GitHub REST API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api). The listing uses GitHub's [Git Trees API](https://docs.github.com/en/rest/git/trees).

Repository URLs are validated independently by the backend and API requests are sent only to `api.github.com` with a timeout and bounded response size. No token is used by the public API, and no OAuth flow is included. This phase does not analyze repositories, inspect file contents, comment on pull requests, or apply changes. A truncated tree or the 1,000-file display limit can mean that some Python paths are not shown.

The advanced rule tests include positive, negative, boundary, alias, and
source-line cases. The analyzer parses submitted source with `ast.parse()`;
it never imports or executes the analyzed module.

## Advanced rule methodology and limitations

`SMELL002` counts nested `if`/`elif`, `for`/`async for`, `while`, `try`, and
`with`/`async with` blocks independently within each function. `elif` branches
do not add an artificial extra level. The default limit is four; a finding is
reported at the first control-flow line that enters level five. Sequential
blocks do not add to one another. Nested functions are assessed separately.

`SMELL003` reports approximate cyclomatic complexity using a base score of 1,
then adds one for each `if` (including `elif`), loop, `except` handler, and
conditional expression. Each additional operand in a boolean `and`/`or`
expression adds one. The default threshold is 10, and a finding points to the
function definition. This is a decision-path estimate, not a runtime or
performance complexity measurement. Nested functions are scored separately.

The security checks are syntax heuristics, not proof of exploitability:

- `SEC003` flags `shell=True` and selected dynamic command expressions. A
  command list with `shell=False` is not flagged by this rule. It does not
  perform general interprocedural taint tracking.
- `SEC004` identifies common MD5/SHA-1 APIs. These algorithms can be used in
  legacy interoperability or non-adversarial checks; the finding is a warning
  and does not claim every use is vulnerable.
- `SEC005` looks for SQL keywords in dynamically built strings passed to
  `execute()`/`executemany()`. It recognizes concatenation, f-strings,
  `.format()`, and percent formatting, and leaves ordinary parameterized query
  strings alone. It does not track SQL through variables or function calls, and
  cannot establish whether data is attacker-controlled.
- `SEC002` uses sensitive assignment names and a small set of recognizable
  credential formats. It omits the value from its message, ignores empty and
  common placeholder values, and can still miss secrets with innocuous names
  or flag unusual legitimate values.
- `MAINT002` checks whether an imported binding appears as a loaded name or in
  `__all__`. Reflection, plugin registries, deliberate re-exports, and imports
  kept only for their initialization side effects can make an apparently
  unused import intentional. Star imports and `__future__` imports are skipped.

All findings keep the existing `rule_id`, `severity`, `file`, `line`, and
`message` fields. An optional `remediation` field adds concise guidance to API
and JSON results; consumers that do not use it can ignore it. The frontend
shows guidance when present and remains compatible with responses that omit it.

## Running the API backend on Windows (VS Code)

Open this project folder (`code-review-engine`) in VS Code. In **Terminal → New
Terminal**, run the following PowerShell commands from the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation
is at `http://127.0.0.1:8000/docs`; use `GET /health`, `GET /api/rules`,
`POST /api/analyze` for pasted source, or `POST /api/analyze/file` for a `.py`
upload. Requests are limited to 1 MiB of UTF-8 source. Submitted source is
parsed by the existing AST analyzer and is never executed. The temporary source
file is removed after analysis.

If PowerShell blocks virtual-environment activation, use the VS Code Command
Prompt terminal instead and activate with:

```bat
.venv\Scripts\activate.bat
```

## Running the React frontend on Windows (VS Code)

Open a second VS Code terminal from the project root and run:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://127.0.0.1:5173`). Keep the
FastAPI server running in the first terminal. Vite proxies `/api` and `/health`
to `http://127.0.0.1:8000`. To use a different backend address, create
`frontend/.env.local` with
`VITE_API_PROXY_TARGET=http://your-backend-host:8000` and restart Vite.

Create and type-check a production frontend bundle with:

```powershell
cd frontend
npm run build
```

The frontend keeps analyses in browser memory for the current session only.
Its JSON and CSV downloads are generated from actual backend analysis results.
Run the frontend component tests with `npm test` from the `frontend` folder.

## Reviewing a GitHub pull request

The Pull Request Review page accepts a GitHub pull request URL and uses the
read-only GitHub REST API to inspect changed files. Select changed `.py` files
and analyze their contents at the pull request's head commit. The existing
analyzer and quality scorer are reused; submitted source is parsed statically
and is never executed. Findings can be filtered in the page and exported as a
JSON report (source contents are not included in the export).

The API exposes `POST /api/github/pr/inspect` to validate the pull request and
list its changed files, and `POST /api/github/pr/analyze` to analyze selected
Python paths. `GET /health` and `GET /api/rules` remain available. Public pull
requests can be inspected without a token; private repository access is
disabled on the unauthenticated API. GitHub's rate limits
apply. PR file listings are bounded to 300 paths and each review analyzes at
most 25 selected Python files. Individual source files are limited to 1 MiB,
and aggregate fetched source is limited to 8 MiB. Deleted files, non-Python
files, unsafe paths, binary or invalid UTF-8 content, oversized files, and
unavailable source are reported as skipped. An incomplete GitHub file listing
is surfaced as partial coverage. The inspect snapshot is held in process memory
for 10 minutes, so inspect and analyze requests must reach the same running
backend process.

The integration does not clone repositories, post comments, or make writes to
GitHub. It only requests PR metadata, changed-file metadata, and source blobs
at the PR head SHA. Analysis is limited to the repository's existing static
rules and should be treated as heuristic guidance.

## GitHub Actions CI Integration

The `CodeReview AI PR Analysis` workflow in
`.github/workflows/codereview-ai.yml` analyzes only added, modified, and renamed
`.py` files in a pull request. Deleted and non-Python files are excluded. A PR
with no changed Python files produces a passing report with zero findings.
Renames are resolved to their new path. Filenames are read from Git's
NUL-delimited diff output and are passed to Python without shell expansion.

The workflow runs when a pull request is opened, updated with new commits,
reopened, or marked ready for review. It also supports manual runs from the
repository's **Actions** tab using **Run workflow**. For a manual run, choose
the base branch/commit; the head defaults to the selected workflow commit.
The workflow uses Ubuntu and Python 3.12. The analyzer, scoring service, and CI
reporting path use Python's standard library, so this workflow does not install
the analyzed project's dependencies or execute its code. Its token permissions
are read-only (`contents: read`); it does not post PR comments or modify GitHub.

The CI command reuses the 14 registered analyzer rules and the existing score
calculation: `max(0, 100 - 15 × critical - 5 × warning - 1 × informational)`.
The default quality gate requires a score of at least 75 and fails when any
critical finding exists. Parse errors and changed Python files that cannot be
safely read also fail the gate so an incomplete analysis is not reported as a
pass. The existing CLI behavior and its `--fail-on` severity gate are
unchanged.

For bounded CI work, at most 300 changed Python paths are analyzed and a source
file larger than 1 MiB is skipped and fails the gate. Skipped paths and reasons
appear in the report.

Configure optional repository **Actions variables** under **Settings → Secrets
and variables → Actions → Variables**. These are thresholds, not credentials:

| Variable | Default | Meaning |
| --- | --- | --- |
| `CODE_REVIEW_MIN_SCORE` | `75` | Minimum quality score from 0 to 100. |
| `CODE_REVIEW_FAIL_ON_CRITICAL` | `true` | Fail if one or more critical findings exist. Set to `false` to disable this check. |
| `CODE_REVIEW_MAX_CRITICAL` | unset | Optional maximum critical finding count. |
| `CODE_REVIEW_MAX_WARNINGS` | unset | Optional maximum warning finding count. |

Every configured condition must pass. For example, set `CODE_REVIEW_MIN_SCORE`
to `90` and `CODE_REVIEW_MAX_WARNINGS` to `3` to require a score of at least
90 and no more than three warnings. The minimum-score gate applies to the
existing score, including its informational finding penalty.

**Passing example:** a changed Python file has no findings, scores 100 (A),
and the report marks the quality gate as passed. **Failing example:** a changed
file calls `eval()`, producing a critical `SEC001` finding; with the default
configuration, the report lists the finding and remediation and fails the job.

View the readable summary under the workflow run's **Summary** tab. The step
logs also contain a bounded list of findings grouped by severity. Set
`CODE_REVIEW_MAX_CRITICAL` or `CODE_REVIEW_MAX_WARNINGS` to an integer to cap
those severities. Large reports include totals and state when details were
omitted.

To try the same integration locally from a checkout containing both refs,
run:

```powershell
python cli.py --ci --base-ref main --head-ref feature/my-change
```

Thresholds can also be passed as CLI options, such as
`--min-score 90 --fail-on-critical true --max-warnings 3`. The CI mode exits
with code 0 when the gate passes, 1 when it fails, and 2 for invalid
configuration or Git-ref errors.

To disable the workflow, open **Actions → CodeReview AI PR Analysis → … →
Disable workflow**, or remove `.github/workflows/codereview-ai.yml` from the
repository. Re-enable it from the same Actions page if it was disabled there.

Troubleshooting:

- **Git cannot compare the refs:** the workflow fetches full history. For a
  local run, fetch both refs and pass branch names or commit SHAs.
- **Invalid quality-gate configuration:** score must be 0–100, and optional
  finding limits must be non-negative integers.
- **A Python file is skipped:** check the report for missing files, symlinks,
  invalid Python syntax, or other read errors. Symlinks are skipped to avoid
  reading outside the checked-out source.
- **The check does not block merging:** add this workflow's job as a required
  status check in the repository's branch protection or ruleset settings.

Run the analyzer and API tests from the project root with:

```powershell
python -m pytest tests/ -v
```

## Roadmap (Capstone-2)

- Extend GitHub Actions analysis to pushes or scheduled repository scans
- Add a webhook receiver so analysis triggers automatically
- Persist reports to a database instead of just JSON files
- Build the web dashboard to browse historical reports
- Select a hosting platform and configure its container services
- Add Prometheus/Grafana monitoring for pipeline health

## Running with Docker

The local container setup runs the FastAPI backend and React frontend as
separate services. Nginx serves the production React build and reverse-proxies
`/api`, `/health`, and the API documentation to FastAPI over the private
Compose network. The browser uses same-origin relative API paths, so it does
not need a hardcoded backend URL or cross-origin configuration.

### Prerequisites

- Docker Desktop with Docker Compose v2, or Docker Engine with the Compose
  plugin.
- A terminal opened in the project root.

### Configure and start

Copy the example environment file to `.env` (PowerShell):

```powershell
Copy-Item .env.example .env
```

Edit `.env` if needed. Private GitHub access is disabled on the unauthenticated
public API; do not configure a token. Docker Compose reads `.env` for local
runtime values. `.env` is ignored by Git and the Docker build context.

Build and start both services with:

```powershell
docker compose up --build
```

Open the app at `http://localhost:8081`. The API health endpoint is
`http://localhost:8081/health`, and interactive API documentation is
`http://localhost:8081/docs`. Docker maps
host port 8081 to the frontend container's Nginx port 8080. Backend port 8000
is available only to services on the Docker network; it is not published
directly on the host. Code analysis, quality scores, findings, GitHub
repository/PR analysis, and JSON/CSV exports use the same application API and
frontend behavior as the development setup.

### Environment variables

| Variable | Default | Used by | Purpose |
| --- | --- | --- | --- |
| `API_UPSTREAM` | `backend:8000` | Frontend Nginx | Backend host and port reachable from the frontend container. Keep this value for local Compose. |
| `GITHUB_TOKEN` | Unset | Not consumed by public API routes | Do not configure until private repository access has authenticated and authorized callers. |
| `PORT` | `8000` backend / `8080` frontend | Container runtime | Listening port; Compose sets both values. Container platforms can provide their assigned port. |

The Vite `VITE_API_PROXY_TARGET` remains for local development only. The
production frontend bundle uses relative paths and contains no backend URL or
GitHub token. For Railway, set frontend `API_UPSTREAM` to the backend's
private domain and runtime port, with no URL scheme.

### Stop, rebuild, and troubleshoot

Stop the services with `Ctrl+C`, or from another project terminal run:

```powershell
docker compose down
```

Rebuild after changing dependencies or container configuration:

```powershell
docker compose up --build
```

Useful checks:

```powershell
docker compose ps
docker compose logs backend frontend
```

- **The frontend is unhealthy or API calls fail:** make sure the backend is
  healthy with `docker compose ps`; the frontend waits for backend health
  before starting. Check that `API_UPSTREAM` is a hostname/port reachable from
  the frontend container (default: `backend:8000`).
- **Port 8081 is already in use:** stop the other application using it. If
  you need a different host port, change only the left side of the frontend
  mapping in `docker-compose.yml`; keep the container port on the right at
  `8080`.
- **A private GitHub repository is unavailable:** private access is disabled
  for the unauthenticated public API. No token is used by those endpoints.
- **A Docker build appears to use old files:** run `docker compose build --no-cache`
  and then `docker compose up`.

### Deployment preparation

The images are separated so Railway can run frontend and backend services
independently. Configure each service to build from the repository root (the
Docker build context) and select `frontend/Dockerfile` or `backend/Dockerfile`
respectively. The backend listens on Railway's injected `PORT`; set its
Railway health check path to `/health`. The frontend Nginx listens on its
injected `PORT`, serves SPA routes, and proxies API requests to `API_UPSTREAM`.
Set the frontend variable to
`${{Backend.RAILWAY_PRIVATE_DOMAIN}}:${{Backend.PORT}}` (replace `Backend`
with the exact Railway service name). Only the frontend needs a public domain;
keep the backend private. Local Compose retains `API_UPSTREAM=backend:8000`,
host port 8081, and frontend container port 8080.

The interactive API docs and OpenAPI schema remain public and contain no
credentials; restrict them at the edge if a future deployment requires that.
`PORT` is platform-provided; do not hardcode a Railway port.
No `GITHUB_TOKEN` is needed for public repositories. Private repositories are
unavailable through the unauthenticated API; adding a token alone would expose
private source to public callers, so do not configure one. In-memory limits
are 20 code analyses/minute, 30 repository lookups/minute, and 8 PR operations
per minute per forwarded client address. They reset on restart and are not
shared across replicas; they are abuse friction, not a substitute for
authentication or edge quotas. Request bodies are capped at 10 MiB, source
files at 1 MiB, and PR aggregate source at 8 MiB.

The backend keeps GitHub pull-request inspection snapshots in process memory
for 10 minutes (up to 64 snapshots). Run exactly one backend replica so PR
inspect and analyze requests share that snapshot. Multi-replica deployments
need a shared snapshot store or stateless selection design. Railway health
checks gate deployment startup and are not continuous monitoring. Nginx adds
a same-origin CSP and browser security headers. Rate limits and the absence of
user authentication remain deployment limitations. No cloud resources or
deployment have been created.
