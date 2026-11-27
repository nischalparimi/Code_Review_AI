#!/usr/bin/env python3
"""
cli.py

Command-line entry point for the Automated Code Review and Static
Analysis System.

Usage:
    python cli.py <path> [--json report.json] [--fail-on critical]

Examples:
    python cli.py samples/
    python cli.py samples/bad_example.py --json report.json
    python cli.py samples/ --fail-on critical,warning
"""

import argparse
import os
import sys

from analyzer.ci import (
    CIAnalysisError,
    QualityGateConfig,
    analyze_changed_files,
    detect_changed_python_files,
    evaluate_quality_gate,
    render_ci_report,
    write_step_summary,
)
from analyzer.engine import Report, analyze_path
from analyzer.report import print_console_report, write_json_report
from backend.app.services.scoring import calculate_quality_score


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _parse_optional_count(value):
    if value in {None, "", "none", "off"}:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("expected a non-negative integer or unset") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer or unset")
    return parsed


def _run_ci(args):
    if args.fail_on is not None:
        raise CIAnalysisError("--fail-on is for the legacy CLI mode; configure CI using --fail-on-critical.")
    if not args.base_ref or not args.head_ref:
        raise CIAnalysisError("CI mode requires --base-ref and --head-ref Git refs.")
    try:
        config = QualityGateConfig(
            min_score=args.min_score,
            fail_on_critical=args.fail_on_critical,
            max_critical=args.max_critical,
            max_warnings=args.max_warnings,
        )
    except ValueError as exc:
        raise CIAnalysisError(str(exc)) from exc

    paths = detect_changed_python_files(args.base_ref, args.head_ref, args.repository_root)
    report, skipped = analyze_changed_files(paths, args.repository_root)
    score = calculate_quality_score(
        report.all_issues,
        parse_error_count=sum(item.parse_error is not None for item in report.files),
    )
    passed, reasons = evaluate_quality_gate(report, score, config, skipped)
    analyzed = sum(item.parse_error is None for item in report.files)
    markdown, logs = render_ci_report(
        args.repository_name or os.environ.get("GITHUB_REPOSITORY", ""),
        args.pull_request_number or os.environ.get("CODE_REVIEW_PR_NUMBER", ""),
        analyzed,
        skipped,
        report,
        score,
        passed,
        reasons,
    )
    print(logs)
    write_step_summary(markdown, args.summary_file)
    if args.json:
        written_to = write_json_report(report, args.json)
        print(f"JSON report written to: {written_to}")
    if args.chart:
        from analyzer.chart import save_summary_chart
        chart_path = save_summary_chart(report, args.chart)
        print(f"Summary chart written to: {chart_path}")
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run static analysis against a Python file, directory, or changed pull-request files."
    )
    parser.add_argument("path", nargs="?", help="File or directory to analyze (omit when using --ci)")
    parser.add_argument("--json", metavar="FILE", help="Write a JSON report to FILE")
    parser.add_argument("--chart", metavar="FILE", nargs="?", const="report_chart.png",
                         help="Save a bar-chart summary (severity + category) as an image. "
                              "Defaults to report_chart.png if no filename given.")
    parser.add_argument(
        "--fail-on",
        default=None,
        help="Comma-separated severities that should cause a non-zero exit "
             "code (used as the CI quality gate). Default: critical",
    )
    parser.add_argument("--ci", action="store_true", help="Analyze only added, modified, and renamed Python files between Git refs")
    parser.add_argument("--base-ref", default=os.environ.get("CODE_REVIEW_BASE_REF"), help="Base branch or commit for --ci")
    parser.add_argument("--head-ref", default=os.environ.get("CODE_REVIEW_HEAD_REF"), help="Head branch or commit for --ci")
    parser.add_argument("--repository-root", default=".", help="Git checkout root (default: current directory)")
    parser.add_argument("--repository-name", default=os.environ.get("GITHUB_REPOSITORY", ""), help="Repository label in the CI report")
    parser.add_argument("--pull-request-number", default=os.environ.get("CODE_REVIEW_PR_NUMBER", ""), help="PR number in the CI report")
    parser.add_argument("--summary-file", default=None, help="Append Markdown report to this GitHub step-summary file")
    parser.add_argument("--min-score", type=int, default=os.environ.get("CODE_REVIEW_MIN_SCORE") or "75", help="Minimum passing score, 0-100 (default: 75)")
    parser.add_argument("--fail-on-critical", type=_parse_bool, default=os.environ.get("CODE_REVIEW_FAIL_ON_CRITICAL") or "true", metavar="BOOL", help="Fail when any critical finding exists (default: true)")
    parser.add_argument("--max-critical", type=_parse_optional_count, default=os.environ.get("CODE_REVIEW_MAX_CRITICAL", ""), metavar="COUNT", help="Maximum critical findings; unset means no limit")
    parser.add_argument("--max-warnings", type=_parse_optional_count, default=os.environ.get("CODE_REVIEW_MAX_WARNINGS", ""), metavar="COUNT", help="Maximum warning findings; unset means no limit")
    args = parser.parse_args(argv)

    if args.ci:
        if args.path:
            parser.error("do not provide PATH with --ci; changed files are detected from the Git refs")
        try:
            exit_code = _run_ci(args)
        except CIAnalysisError as exc:
            print(f"CI analysis error: {str(exc).replace(chr(10), ' ').replace(chr(13), ' ')}", file=sys.stderr)
            raise SystemExit(2) from exc
        raise SystemExit(exit_code)

    if not args.path:
        parser.error("PATH is required unless --ci is used")

    report = analyze_path(args.path)
    print_console_report(report)

    if args.json:
        written_to = write_json_report(report, args.json)
        print(f"\nJSON report written to: {written_to}")

    if args.chart:
        from analyzer.chart import save_summary_chart
        chart_path = save_summary_chart(report, args.chart)
        print(f"Summary chart written to: {chart_path}")

    block_on = tuple(s.strip() for s in (args.fail_on or "critical").split(",") if s.strip())
    if report.has_blocking_issues(block_on=block_on):
        print(f"\nQuality gate FAILED: found issues at severity {block_on}.")
        sys.exit(1)

    print("\nQuality gate PASSED.")
    sys.exit(0)


if __name__ == "__main__":
    main()
