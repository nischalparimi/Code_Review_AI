"""Changed-file analysis and reporting helpers for GitHub Actions CI."""

from __future__ import annotations

from dataclasses import dataclass
import html
import ntpath
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Sequence

from analyzer.engine import FileResult, Report, analyze_file
from backend.app.services.scoring import calculate_quality_score

MAX_CI_CHANGED_FILES = 300
MAX_CI_SOURCE_BYTES = 1_048_576


class CIAnalysisError(ValueError):
    """A safe configuration or Git error in changed-file CI mode."""


@dataclass(frozen=True)
class QualityGateConfig:
    min_score: int = 75
    fail_on_critical: bool = True
    max_critical: int | None = None
    max_warnings: int | None = None

    def __post_init__(self):
        if type(self.min_score) is not int or not 0 <= self.min_score <= 100:
            raise ValueError("minimum quality score must be an integer from 0 to 100")
        if type(self.fail_on_critical) is not bool:
            raise ValueError("fail_on_critical must be true or false")
        for name in ("max_critical", "max_warnings"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name.replace('_', ' ')} must be a non-negative integer or unset")


_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")


def _validate_ref(ref: str, label: str) -> str:
    if (
        not isinstance(ref, str)
        or not _REF_PATTERN.fullmatch(ref)
        or ".." in ref
        or "//" in ref
        or ref.endswith(("/", ".", ".lock"))
        or "@{" in ref
    ):
        raise CIAnalysisError(f"Invalid {label} Git ref. Use a branch name or commit SHA.")
    return ref


def _parse_name_status_z(output: bytes) -> list[str]:
    """Parse `git diff --name-status -z`, including its two-path rename records."""
    fields = output.split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(fields) - 1:
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                break
            candidate = fields[index + 1]
            index += 2
        else:
            if index >= len(fields):
                break
            candidate = fields[index]
            index += 1
        if status[:1] not in {"A", "M", "R"}:
            continue
        path = os.fsdecode(candidate)
        if path.lower().endswith(".py"):
            paths.append(path)
    return list(dict.fromkeys(paths))


def detect_changed_python_files(base_ref: str, head_ref: str, repository: str | os.PathLike = ".") -> list[str]:
    """Return added, modified, and renamed Python paths from a Git three-dot diff.

    Git receives an argument vector and returns NUL-delimited paths, so spaces,
    shell metacharacters, tabs, and newlines in filenames are not interpreted.
    Deleted files and non-Python paths are omitted.
    """
    base_ref = _validate_ref(base_ref, "base")
    head_ref = _validate_ref(head_ref, "head")
    command = ["git", "diff", "--name-status", "-z", "--find-renames", "--no-ext-diff", "--no-textconv", f"{base_ref}...{head_ref}", "--"]
    try:
        result = subprocess.run(command, cwd=repository, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise CIAnalysisError("Git is not installed or could not be found on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = os.fsdecode(exc.stderr or b"").strip().splitlines()
        message = detail[-1] if detail else "Git could not compare the requested refs."
        raise CIAnalysisError(message[:300]) from exc
    return _parse_name_status_z(result.stdout)


def _safe_worktree_file(path: str, root: Path) -> tuple[Path | None, str | None]:
    if not path or "\0" in path:
        return None, "Git returned an invalid path."
    relative = PurePosixPath(path)
    if (relative.is_absolute() or ntpath.isabs(path) or ntpath.splitdrive(path)[0]
            or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/"))):
        return None, "Path is outside the repository or is not a safe relative path."
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, "Symlink paths are skipped to avoid reading outside the checked-out source."
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None, "File is missing or resolves outside the repository."
    if not resolved.is_file():
        return None, "Path is not a regular file."
    return resolved, None


def analyze_changed_files(paths: Sequence[str], repository: str | os.PathLike = ".") -> tuple[Report, list[dict[str, str]]]:
    """Analyze only supplied changed paths with the existing AST engine."""
    root = Path(repository).resolve(strict=True)
    report = Report()
    skipped: list[dict[str, str]] = []
    for path_index, path in enumerate(paths):
        if path_index >= MAX_CI_CHANGED_FILES:
            skipped.append({"file": path, "reason": f"The CI analysis limit of {MAX_CI_CHANGED_FILES} changed Python files was reached."})
            continue
        resolved, reason = _safe_worktree_file(path, root)
        if reason:
            skipped.append({"file": path, "reason": reason})
            continue
        try:
            if resolved.stat().st_size > MAX_CI_SOURCE_BYTES:
                skipped.append({"file": path, "reason": f"File exceeds the {MAX_CI_SOURCE_BYTES}-byte CI analysis limit."})
                continue
        except OSError:
            skipped.append({"file": path, "reason": "File could not be read from the checkout."})
            continue
        result = analyze_file(str(resolved))
        display_path = PurePosixPath(path).as_posix()
        result.filepath = display_path
        for issue in result.issues:
            issue.file = display_path
        report.files.append(result)
        if result.parse_error:
            skipped.append({"file": display_path, "reason": result.parse_error})
    return report, skipped


def evaluate_quality_gate(report: Report, quality_score: dict, config: QualityGateConfig, skipped_files: Sequence[dict] = ()) -> tuple[bool, list[str]]:
    """Evaluate CI thresholds using existing analyzer findings and scoring output."""
    reasons: list[str] = []
    score = quality_score["score"]
    counts = report.counts_by_severity
    if score < config.min_score:
        reasons.append(f"Quality score {score} is below the configured minimum of {config.min_score}.")
    if config.fail_on_critical and counts.get("critical", 0):
        reasons.append(f"Found {counts['critical']} critical finding(s); fail-on-critical is enabled.")
    if config.max_critical is not None and counts.get("critical", 0) > config.max_critical:
        reasons.append(f"Critical finding count {counts['critical']} exceeds the configured maximum of {config.max_critical}.")
    if config.max_warnings is not None and counts.get("warning", 0) > config.max_warnings:
        reasons.append(f"Warning count {counts['warning']} exceeds the configured maximum of {config.max_warnings}.")
    parse_errors = sum(file.parse_error is not None for file in report.files)
    if parse_errors:
        reasons.append(f"{parse_errors} changed Python file(s) could not be parsed.")
    if skipped_files:
        reasons.append(f"{len(skipped_files)} changed Python file(s) were skipped or could not be analyzed.")
    return not reasons, reasons


def _safe_text(value) -> str:
    """Keep untrusted source-derived text on one safe workflow-log line."""
    text = str(value)
    text = text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    text = "".join(char if char >= " " and char != "\x7f" else "?" for char in text)
    return text.replace("::", "&#58;&#58;")


def _markdown_cell(value) -> str:
    text = html.escape(str(value), quote=True).replace("`", "&#96;")
    return text.replace("\r", " ").replace("\n", "<br>").replace("|", "&#124;")


def render_ci_report(repository_name: str, pull_request_number: str, analyzed_count: int, skipped_files: Sequence[dict[str, str]], report: Report, quality_score: dict, gate_passed: bool, gate_reasons: Sequence[str], max_findings: int = 200) -> tuple[str, str]:
    """Render bounded GitHub step-summary Markdown and safe plain workflow logs."""
    counts = report.counts_by_severity
    status = "PASSED" if gate_passed else "FAILED"
    title = "CodeReview AI quality gate " + status
    lines = [
        "## CodeReview AI static analysis",
        "",
        "| Summary | Result |",
        "| --- | ---: |",
        f"| Repository | {_markdown_cell(repository_name or 'Local repository')} |",
        f"| Pull request | {_markdown_cell(pull_request_number or 'Manual run')} |",
        f"| Files analyzed | {analyzed_count} |",
        f"| Files skipped | {len(skipped_files)} |",
        f"| Total findings | {len(report.all_issues)} |",
        f"| Critical | {counts.get('critical', 0)} |",
        f"| Warnings | {counts.get('warning', 0)} |",
        f"| Informational | {counts.get('info', 0)} |",
        f"| Quality score | {quality_score['score']} / 100 |",
        f"| Grade | {_markdown_cell(quality_score['grade'])} — {_markdown_cell(quality_score['grade_label'])} |",
        f"| Quality gate | **{status}** |",
        "",
    ]
    if gate_reasons:
        lines.extend(["### Gate details", ""])
        lines.extend(f"- {_markdown_cell(reason)}" for reason in gate_reasons)
        lines.append("")
    for severity, heading in (("critical", "Critical"), ("warning", "Warnings"), ("info", "Informational")):
        findings = [issue for issue in report.all_issues if issue.severity == severity]
        lines.extend([f"### {heading} ({len(findings)})", ""])
        if not findings:
            lines.extend(["None.", ""])
            continue
        for issue in findings[:max_findings]:
            location = f"{issue.file}:{issue.line}" if issue.line else issue.file
            lines.append(f"- **{_markdown_cell(issue.rule_id)}** `{_markdown_cell(location)}` — {_markdown_cell(issue.message)}")
            if issue.remediation:
                lines.append(f"  - Suggestion: {_markdown_cell(issue.remediation)}")
        if len(findings) > max_findings:
            lines.append(f"- {len(findings) - max_findings} additional findings omitted from this summary.")
        lines.append("")
    if skipped_files:
        lines.extend(["### Skipped files", ""])
        for entry in skipped_files[:max_findings]:
            lines.append(f"- `{_markdown_cell(entry['file'])}` — {_markdown_cell(entry['reason'])}")
        if len(skipped_files) > max_findings:
            lines.append(f"- {len(skipped_files) - max_findings} additional skipped files omitted.")
        lines.append("")

    logs = [title, f"Repository: {_safe_text(repository_name or 'Local repository')} | PR: {_safe_text(pull_request_number or 'manual')}", f"Files analyzed: {analyzed_count}; skipped: {len(skipped_files)}", f"Findings: {len(report.all_issues)} (critical={counts.get('critical', 0)}, warning={counts.get('warning', 0)}, info={counts.get('info', 0)})", f"Quality score: {quality_score['score']}/100 ({quality_score['grade']} - {quality_score['grade_label']})"]
    for reason in gate_reasons:
        logs.append(f"Gate: {_safe_text(reason)}")
    logged_count = 0
    for severity in ("critical", "warning", "info"):
        for issue in report.all_issues:
            if issue.severity != severity:
                continue
            if logged_count >= max_findings:
                break
            logs.append(f"[{severity.upper()}] {_safe_text(issue.rule_id)} {_safe_text(issue.file)}:{issue.line} {_safe_text(issue.message)}")
            if issue.remediation:
                logs.append(f"  Suggestion: {_safe_text(issue.remediation)}")
            logged_count += 1
    if len(report.all_issues) > logged_count:
        logs.append(f"{len(report.all_issues) - logged_count} additional findings omitted from workflow logs.")
    return "\n".join(lines).rstrip() + "\n", "\n".join(logs)


def write_step_summary(markdown: str, summary_file: str | None = None) -> None:
    """Append a report to GitHub Actions' summary file when available."""
    path = summary_file or os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8", newline="\n") as summary:
        summary.write(markdown)
