"""
report.py

Turns a Report (from engine.py) into human-readable console output or
a machine-readable JSON file. The JSON format is what a future CI/CD
stage or dashboard would consume.
"""

import json
from dataclasses import asdict

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SEVERITY_TAG = {"critical": "[CRITICAL]", "warning": "[WARNING] ", "info": "[INFO]    "}


def print_console_report(report):
    """Pretty-print the report to stdout, grouped by file."""
    total = len(report.all_issues)
    counts = report.counts_by_severity

    print("=" * 70)
    print("AUTOMATED CODE REVIEW REPORT")
    print("=" * 70)

    for file_result in report.files:
        if file_result.parse_error:
            print(f"\n{file_result.filepath}")
            print(f"  !! Could not analyze: {file_result.parse_error}")
            continue

        if not file_result.issues:
            continue

        print(f"\n{file_result.filepath}")
        sorted_issues = sorted(
            file_result.issues, key=lambda i: (i.line, SEVERITY_ORDER.get(i.severity, 9))
        )
        for issue in sorted_issues:
            tag = SEVERITY_TAG.get(issue.severity, issue.severity.upper())
            print(f"  {tag} L{issue.line:<5} {issue.rule_id:<10} {issue.message}")
            if issue.remediation:
                print(f"           Remediation: {issue.remediation}")

    print("\n" + "-" * 70)
    print(f"Total issues: {total}  "
          f"(critical={counts['critical']}, warning={counts['warning']}, info={counts['info']})")
    print("=" * 70)


def write_json_report(report, output_path):
    """Serialize the report to a JSON file for CI artifacts / dashboards."""
    data = {
        "summary": report.counts_by_severity,
        "total_issues": len(report.all_issues),
        "files": [
            {
                "file": f.filepath,
                "parse_error": f.parse_error,
                "issues": [asdict(i) for i in f.issues],
            }
            for f in report.files
        ],
    }
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2)
    return output_path
