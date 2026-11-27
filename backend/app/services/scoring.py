"""Deterministic quality scoring derived exclusively from analyzer findings."""

from collections.abc import Iterable, Mapping

INITIAL_SCORE = 100
SEVERITY_PENALTIES = {"critical": 15, "warning": 5, "info": 1}
GRADE_BANDS = (
    (90, "A", "Excellent"),
    (75, "B", "Good"),
    (60, "C", "Fair"),
    (40, "D", "Poor"),
    (0, "F", "Critical"),
)
SCORING_EXPLANATION = (
    "The score starts at 100. Each critical finding deducts 15 points, "
    "each warning deducts 5 points, and each informational finding deducts 1 point."
)


def grade_for_score(score: int) -> tuple[str, str]:
    """Return the grade and label for a score in the inclusive 0–100 range."""
    bounded = max(0, min(100, int(score)))
    for minimum, grade, label in GRADE_BANDS:
        if bounded >= minimum:
            return grade, label
    return "F", "Critical"


def _severity_of(finding) -> str:
    if isinstance(finding, Mapping):
        return str(finding.get("severity", "")).lower()
    return str(getattr(finding, "severity", "")).lower()


def calculate_quality_score(findings: Iterable, parse_error_count: int = 0) -> dict:
    """Calculate an aggregate score from findings; parse errors are surfaced separately.

    Unknown severities do not receive an invented penalty. Built-in analyzer
    rules use only critical, warning, and info, and all findings remain in the
    response even if a future custom rule introduces another severity.
    """
    counts = {severity: 0 for severity in SEVERITY_PENALTIES}
    for finding in findings:
        severity = _severity_of(finding)
        if severity in counts:
            counts[severity] += 1

    return calculate_quality_score_from_counts(counts, parse_error_count)


def calculate_quality_score_from_counts(severity_counts: Mapping, parse_error_count: int = 0) -> dict:
    """Score pre-counted severities, also useful for large-count boundary tests."""
    counts = {
        severity: max(0, int(severity_counts.get(severity, 0)))
        for severity in SEVERITY_PENALTIES
    }

    penalties = {
        severity: counts[severity] * penalty
        for severity, penalty in SEVERITY_PENALTIES.items()
    }
    total_penalty = sum(penalties.values())
    score = max(0, INITIAL_SCORE - total_penalty)
    grade, grade_label = grade_for_score(score)
    explanation = SCORING_EXPLANATION
    if parse_error_count:
        explanation += (
            f" {parse_error_count} file(s) could not be parsed; parse errors are shown separately "
            "and are not included as findings in this score. Resolve them before relying on the score."
        )

    return {
        "initial_score": INITIAL_SCORE,
        "critical_count": counts["critical"],
        "warning_count": counts["warning"],
        "info_count": counts["info"],
        "severity_counts": counts,
        "critical_penalty": penalties["critical"],
        "warning_penalty": penalties["warning"],
        "info_penalty": penalties["info"],
        "penalties": penalties,
        "total_penalty": total_penalty,
        "score": score,
        "grade": grade,
        "grade_label": grade_label,
        "parse_error_count": max(0, int(parse_error_count)),
        "explanation": explanation,
    }
