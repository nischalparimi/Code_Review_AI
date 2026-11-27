"""Tests for changed-file CI integration using temporary local Git repositories."""

from pathlib import Path
import shutil
import subprocess

import pytest

from analyzer.ci import (
    CIAnalysisError,
    QualityGateConfig,
    _parse_name_status_z,
    analyze_changed_files,
    detect_changed_python_files,
    evaluate_quality_gate,
    render_ci_report,
)
from analyzer.engine import Report
from backend.app.services.scoring import calculate_quality_score
from cli import main


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Git is required for CI integration tests")


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def create_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.email", "ci-test@example.invalid")
    git(root, "config", "user.name", "CI Test")
    (root / "edit.py").write_text("value = 1\n", encoding="utf-8")
    (root / "delete.py").write_text("value = 2\n", encoding="utf-8")
    (root / "move me.py").write_text("def renamed():\n    return 3\n", encoding="utf-8")
    (root / "notes.txt").write_text("before\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-c", "feature")
    (root / "edit.py").write_text("value = eval('1')\n", encoding="utf-8")
    (root / "delete.py").unlink()
    (root / "new special [file] & name.py").write_text("def renamed():\n    return 3\n", encoding="utf-8")
    (root / "move me.py").unlink()
    (root / "added.py").write_text("def added():\n    return None\n", encoding="utf-8")
    (root / "notes.txt").write_text("after\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "changed files")
    head = git(root, "rev-parse", "HEAD")
    return root, base, head


def test_detect_changed_python_paths_handles_add_modify_rename_delete_and_special_names(tmp_path):
    root, base, head = create_repo(tmp_path)
    changed = detect_changed_python_files(base, head, root)
    assert set(changed) == {"edit.py", "added.py", "new special [file] & name.py"}
    assert "delete.py" not in changed
    assert "notes.txt" not in changed


def test_nul_parser_preserves_newline_and_tab_in_paths_and_excludes_deletes():
    output = b"A\0line\nfeed.py\0M\0tab\tfile.py\0D\0deleted.py\0R100\0old.py\0renamed & new.py\0"
    assert _parse_name_status_z(output) == ["line\nfeed.py", "tab\tfile.py", "renamed & new.py"]


def test_no_python_changes_returns_empty_list_and_ci_passes(tmp_path, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.email", "ci-test@example.invalid")
    git(root, "config", "user.name", "CI Test")
    (root / "notes.txt").write_text("before\n", encoding="utf-8")
    git(root, "add", "--all")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "switch", "-c", "feature")
    (root / "notes.txt").write_text("after\n", encoding="utf-8")
    git(root, "commit", "-am", "docs only")
    head = git(root, "rev-parse", "HEAD")
    assert detect_changed_python_files(base, head, root) == []
    with pytest.raises(SystemExit) as result:
        main(["--ci", "--base-ref", base, "--head-ref", head, "--repository-root", str(root)])
    assert result.value.code == 0
    assert "Findings: 0" in capsys.readouterr().out


def test_analysis_reuses_rules_scoring_and_returns_remediation(tmp_path):
    source = tmp_path / "with spaces & special.py"
    source.write_text("value = eval('input')\n", encoding="utf-8")
    report, skipped = analyze_changed_files([source.name], tmp_path)
    assert skipped == []
    assert len(report.all_issues) == 1
    issue = report.all_issues[0]
    assert (issue.rule_id, issue.severity, issue.file, issue.line) == ("SEC001", "critical", source.name, 1)
    assert issue.remediation
    score = calculate_quality_score(report.all_issues)
    assert (score["score"], score["grade"]) == (85, "B")


def test_quality_gate_pass_and_fail_thresholds():
    report = Report()
    score = calculate_quality_score(report.all_issues)
    passed, reasons = evaluate_quality_gate(report, score, QualityGateConfig(min_score=75))
    assert passed and reasons == []

    from analyzer.engine import analyze_file
    source_path = Path(__file__).parent / ".." / "samples" / "bad_example.py"
    bad_report = Report(files=[analyze_file(str(source_path.resolve()))])
    bad_score = calculate_quality_score(bad_report.all_issues)
    passed, reasons = evaluate_quality_gate(bad_report, bad_score, QualityGateConfig(min_score=90))
    assert not passed
    assert any("below the configured minimum" in reason for reason in reasons)
    assert any("critical finding" in reason for reason in reasons)

    pass_with_nonzero_critical = QualityGateConfig(min_score=0, fail_on_critical=False, max_critical=100)
    passed, reasons = evaluate_quality_gate(bad_report, bad_score, pass_with_nonzero_critical)
    assert passed and reasons == []
    warning_limit = QualityGateConfig(min_score=0, fail_on_critical=False, max_warnings=0)
    passed, reasons = evaluate_quality_gate(bad_report, bad_score, warning_limit)
    assert not passed
    assert any("Warning count" in reason for reason in reasons)


@pytest.mark.parametrize("kwargs", [
    {"min_score": -1}, {"min_score": 101}, {"max_critical": -1}, {"max_warnings": -1},
    {"fail_on_critical": "yes"},
])
def test_quality_gate_rejects_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        QualityGateConfig(**kwargs)


def test_ci_report_groups_findings_and_escapes_workflow_command_text(tmp_path):
    source = tmp_path / "finding.py"
    source.write_text("# TODO ::error:: injected\nvalue = eval('x')\n", encoding="utf-8")
    report, skipped = analyze_changed_files([source.name], tmp_path)
    score = calculate_quality_score(report.all_issues)
    markdown, logs = render_ci_report("owner/repo", "7", 1, skipped, report, score, False, ["Gate failed"])
    assert "Repository | owner/repo" in markdown
    assert "### Critical (1)" in markdown
    assert "Suggestion:" in markdown
    assert "&#58;&#58;error&#58;&#58;" in logs
    assert not logs.splitlines()[-1].startswith("::")


def test_cli_ci_mode_returns_gate_exit_codes_and_writes_summary(tmp_path, monkeypatch, capsys):
    root, base, head = create_repo(tmp_path)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/project")
    with pytest.raises(SystemExit) as passed:
        main(["--ci", "--base-ref", base, "--head-ref", head, "--repository-root", str(root), "--min-score", "0", "--fail-on-critical", "false", "--summary-file", str(summary)])
    assert passed.value.code == 0
    assert "quality gate PASSED" in capsys.readouterr().out
    assert "Quality score" in summary.read_text(encoding="utf-8")

    with pytest.raises(SystemExit) as failed:
        main(["--ci", "--base-ref", base, "--head-ref", head, "--repository-root", str(root), "--min-score", "100"])
    assert failed.value.code == 1
    assert "quality gate FAILED" in capsys.readouterr().out


def test_cli_ci_invalid_configuration_and_refs_have_nonzero_exit_codes(tmp_path, monkeypatch, capsys):
    root, base, head = create_repo(tmp_path)
    with pytest.raises(SystemExit) as invalid_config:
        main(["--ci", "--base-ref", base, "--head-ref", head, "--repository-root", str(root), "--min-score", "101"])
    assert invalid_config.value.code == 2
    with pytest.raises(CIAnalysisError):
        detect_changed_python_files("--output=report", head, root)
    monkeypatch.setenv("CODE_REVIEW_FAIL_ON_CRITICAL", "sometimes")
    with pytest.raises(SystemExit) as invalid_env:
        main(["--ci", "--base-ref", base, "--head-ref", head, "--repository-root", str(root)])
    assert invalid_env.value.code == 2


def test_legacy_cli_still_accepts_path_and_preserves_quality_gate(capsys):
    sample = Path(__file__).parent.parent / "samples" / "good_example.py"
    with pytest.raises(SystemExit) as result:
        main([str(sample)])
    assert result.value.code == 0
    assert "Quality gate PASSED" in capsys.readouterr().out
