"""Adapter that safely analyzes submitted source using the existing engine."""

import os
import tempfile
from pathlib import PurePosixPath

from analyzer.engine import analyze_file

MAX_SOURCE_BYTES = 1_048_576


class SourceTooLargeError(ValueError):
    """Raised when submitted UTF-8 source exceeds the configured limit."""


def display_filename(filename: str) -> str:
    """Return a safe display-only basename and require a Python extension."""
    name = (filename or "").replace("\\", "/").strip()
    name = PurePosixPath(name).name
    if not name or name in {".", ".."} or not name.lower().endswith(".py"):
        raise ValueError("filename must be a non-empty .py filename")
    return name


def analyze_source(source_code: str, filename: str = "submitted.py", fail_on=None) -> dict:
    """Write source to an isolated temporary file, invoke analyze_file, then remove it."""
    shown_name = display_filename(filename)
    try:
        encoded = source_code.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("source_code must be valid UTF-8 text") from exc
    if len(encoded) > MAX_SOURCE_BYTES:
        raise SourceTooLargeError(f"source exceeds the {MAX_SOURCE_BYTES}-byte limit")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".py", prefix="code_review_", delete=False) as temp:
            temp_path = temp.name
            temp.write(encoded)

        result = analyze_file(temp_path)
        # The temporary path is an implementation detail and must never leak in responses.
        issues = [
            {
                "rule_id": issue.rule_id,
                "severity": issue.severity,
                "file": shown_name,
                "line": issue.line,
                "message": issue.message,
                "remediation": issue.remediation,
            }
            for issue in result.issues
        ]
        counts = {"info": 0, "warning": 0, "critical": 0}
        for issue in issues:
            counts[issue["severity"]] = counts.get(issue["severity"], 0) + 1
        blockers = list(fail_on if fail_on is not None else ["critical"])
        return {
            "summary": counts,
            "total_issues": len(issues),
            "files": [{"file": shown_name, "parse_error": result.parse_error, "issues": issues}],
            "quality_gate": {
                "blocking_severities": blockers,
                "passed": not any(issue["severity"] in blockers for issue in issues),
            },
        }
    finally:
        if temp_path is not None:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
