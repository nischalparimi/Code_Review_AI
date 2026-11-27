"""Unit tests for deterministic score calculation and exact grade boundaries."""

import pytest

from backend.app.services.scoring import (
    calculate_quality_score,
    calculate_quality_score_from_counts,
    grade_for_score,
)


def findings(critical=0, warning=0, info=0):
    return ([{"severity": "critical"}] * critical
            + [{"severity": "warning"}] * warning
            + [{"severity": "info"}] * info)


@pytest.mark.parametrize(
    ("items", "expected_score", "expected_grade", "expected_label"),
    [
        ([], 100, "A", "Excellent"),
        (findings(critical=1), 85, "B", "Good"),
        (findings(warning=1), 95, "A", "Excellent"),
        (findings(info=1), 99, "A", "Excellent"),
        (findings(critical=2, warning=3, info=4), 51, "D", "Poor"),
        (findings(critical=1, warning=1, info=1), 79, "B", "Good"),
        (findings(critical=20), 0, "F", "Critical"),
    ],
)
def test_score_examples_and_floor(items, expected_score, expected_grade, expected_label):
    result = calculate_quality_score(items)
    assert result["score"] == expected_score
    assert result["grade"] == expected_grade
    assert result["grade_label"] == expected_label
    assert result["score"] == max(0, result["initial_score"] - result["total_penalty"])
    assert result["total_penalty"] == sum(result["penalties"].values())
    assert isinstance(result["score"], int)
    assert 0 <= result["score"] <= 100


def test_very_large_finding_counts_are_clamped_without_expanding_individual_findings():
    result = calculate_quality_score_from_counts({"critical": 10**9, "warning": 10**9, "info": 10**9})
    assert result["score"] == 0
    assert result["total_penalty"] == 21 * 10**9


@pytest.mark.parametrize(
    ("score", "grade", "label"),
    [
        (100, "A", "Excellent"), (90, "A", "Excellent"),
        (89, "B", "Good"), (75, "B", "Good"),
        (74, "C", "Fair"), (60, "C", "Fair"),
        (59, "D", "Poor"), (40, "D", "Poor"),
        (39, "F", "Critical"), (0, "F", "Critical"),
    ],
)
def test_exact_grade_boundaries(score, grade, label):
    assert grade_for_score(score) == (grade, label)


def test_parse_errors_are_reported_without_being_counted_as_findings():
    result = calculate_quality_score([], parse_error_count=2)
    assert result["score"] == 100
    assert result["parse_error_count"] == 2
    assert "could not be parsed" in result["explanation"]


def test_severity_counts_are_derived_from_findings():
    result = calculate_quality_score(findings(critical=2, warning=1, info=5))
    assert result["severity_counts"] == {"critical": 2, "warning": 1, "info": 5}
    assert (result["critical_penalty"], result["warning_penalty"], result["info_penalty"]) == (30, 5, 5)
    assert result["total_penalty"] == 40
    assert result["score"] == 60
