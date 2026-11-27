"""
test_engine.py

Unit tests for the analysis engine. Run with:
    python -m pytest tests/ -v

These tests are exactly what "Test runs of individual modules" (a
Review-2 diary deliverable) refers to — real, automated, repeatable
checks rather than manual eyeballing.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyzer.engine import analyze_file, analyze_path
from analyzer.rules import (
    LineTooLongRule, MissingDocstringRule, BareExceptRule,
    MutableDefaultArgRule, EvalExecUsageRule, HardcodedSecretRule,
    TooManyArgumentsRule, TodoCommentRule,
)

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
BAD_FILE = os.path.join(SAMPLES_DIR, "bad_example.py")
GOOD_FILE = os.path.join(SAMPLES_DIR, "good_example.py")


def _issue_ids(result):
    return {issue.rule_id for issue in result.issues}


def test_bad_example_triggers_expected_rules():
    result = analyze_file(BAD_FILE)
    ids = _issue_ids(result)

    assert "SEC002" in ids, "hardcoded API key should be flagged"
    assert "SMELL001" in ids, "too many parameters should be flagged"
    assert "BUG002" in ids, "mutable default argument should be flagged"
    assert "SEC001" in ids, "eval() usage should be flagged"
    assert "BUG001" in ids, "bare except should be flagged"
    assert "MAINT001" in ids, "TODO comment should be flagged"
    assert "STYLE001" in ids, "overly long line should be flagged"
    assert result.parse_error is None


def test_good_example_has_no_bug_or_security_issues():
    result = analyze_file(GOOD_FILE)
    ids = _issue_ids(result)

    # The clean file should trigger none of the bug/security rules.
    assert "SEC001" not in ids
    assert "SEC002" not in ids
    assert "BUG001" not in ids
    assert "BUG002" not in ids


def test_analyze_path_walks_directory():
    report = analyze_path(SAMPLES_DIR)
    analyzed_files = {f.filepath for f in report.files}

    assert BAD_FILE in analyzed_files
    assert GOOD_FILE in analyzed_files


def test_quality_gate_blocks_on_critical():
    report = analyze_path(SAMPLES_DIR)
    # bad_example.py has SEC001/SEC002 (critical), so the gate must fail.
    assert report.has_blocking_issues(block_on=("critical",)) is True


def test_quality_gate_passes_when_only_info_present():
    report = analyze_path(SAMPLES_DIR)
    # No file in this suite should trigger a "made up" severity like "fatal".
    assert report.has_blocking_issues(block_on=("fatal",)) is False


def test_syntax_error_is_reported_not_raised():
    broken_path = os.path.join(SAMPLES_DIR, "_broken_temp.py")
    with open(broken_path, "w") as f:
        f.write("def broken(:\n    pass\n")
    try:
        result = analyze_file(broken_path)
        assert result.parse_error is not None
        assert result.issues == []
    finally:
        os.remove(broken_path)


def test_individual_rule_classes_are_independently_callable():
    """Each rule can be run in isolation — useful for targeted debugging."""
    with open(BAD_FILE) as f:
        source = f.read()
    import ast
    tree = ast.parse(source, filename=BAD_FILE)

    for rule_cls in [LineTooLongRule, MissingDocstringRule, BareExceptRule,
                      MutableDefaultArgRule, EvalExecUsageRule,
                      HardcodedSecretRule, TooManyArgumentsRule, TodoCommentRule]:
        rule = rule_cls()
        issues = rule.check(BAD_FILE, source, tree)
        assert isinstance(issues, list)
