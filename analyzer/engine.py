"""
engine.py

The core analysis engine: given a file or directory, it parses each
Python source file into an AST, runs every registered rule against it,
and collects the resulting Issues into a Report.

This module intentionally has no CI/CD or web-framework dependencies —
it is a pure, testable library. The CLI (cli.py) and any future
CI pipeline stage import and call `analyze_path()`.
"""

import ast
import os
from dataclasses import dataclass, field

from analyzer.rules import ALL_RULES, Issue


@dataclass
class FileResult:
    filepath: str
    issues: list = field(default_factory=list)
    parse_error: str = None


@dataclass
class Report:
    files: list = field(default_factory=list)  # list[FileResult]

    @property
    def all_issues(self):
        return [issue for f in self.files for issue in f.issues]

    @property
    def counts_by_severity(self):
        counts = {"info": 0, "warning": 0, "critical": 0}
        for issue in self.all_issues:
            counts[issue.severity] = counts.get(issue.severity, 0) + 1
        return counts

    def has_blocking_issues(self, block_on=("critical",)):
        """Used by the CI quality gate: True if the pipeline should fail."""
        return any(issue.severity in block_on for issue in self.all_issues)


def _discover_python_files(path: str) -> list:
    """Return a sorted list of .py files under `path` (file or directory)."""
    if os.path.isfile(path):
        return [path] if path.endswith(".py") else []

    found = []
    for root, _dirs, files in os.walk(path):
        # Skip common noise directories.
        _dirs[:] = [d for d in _dirs if d not in (".git", "__pycache__", "venv", ".venv")]
        for fname in files:
            if fname.endswith(".py"):
                found.append(os.path.join(root, fname))
    return sorted(found)


def analyze_file(filepath: str, rules=None) -> FileResult:
    """Run all rules against a single Python file."""
    rules = rules if rules is not None else ALL_RULES
    result = FileResult(filepath=filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        result.parse_error = f"Could not read file: {e}"
        return result

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        result.parse_error = f"Syntax error: {e}"
        return result

    for rule in rules:
        try:
            result.issues.extend(rule.check(filepath, source, tree))
        except Exception as e:
            # A single misbehaving rule should never crash the whole run.
            result.issues.append(Issue(
                rule_id="ENGINE000", severity="warning", file=filepath, line=0,
                message=f"Rule '{rule.rule_id}' raised an internal error: {e}"
            ))

    return result


def analyze_path(path: str, rules=None) -> Report:
    """Run all rules against every Python file found under `path`."""
    report = Report()
    for filepath in _discover_python_files(path):
        report.files.append(analyze_file(filepath, rules=rules))
    return report
