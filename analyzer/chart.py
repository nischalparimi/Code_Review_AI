"""
chart.py

Generates a visual summary of an analysis Report using matplotlib.
This is what turns a wall of text into something you can put on a
slide or show a reviewer at a glance.

Two charts are produced, side by side in one image:
    1. Issue count by severity (critical / warning / info)
    2. Issue count by rule category (Style / Bug / Security / Smell / Maint.)
"""

import matplotlib
matplotlib.use("Agg")  # no GUI needed — just save to a file
import matplotlib.pyplot as plt

SEVERITY_COLORS = {"critical": "#C00000", "warning": "#BF8F00", "info": "#2E75B6"}

CATEGORY_PREFIX_MAP = {
    "STYLE": "Style",
    "BUG": "Bug Pattern",
    "SEC": "Security",
    "SMELL": "Code Smell",
    "MAINT": "Maintainability",
}


def _category_for(rule_id: str) -> str:
    for prefix, label in CATEGORY_PREFIX_MAP.items():
        if rule_id.startswith(prefix):
            return label
    return "Other"


def save_summary_chart(report, output_path="report_chart.png"):
    """
    Save a two-panel PNG chart summarizing the report:
    left = issues by severity, right = issues by category.
    Returns the path written to.
    """
    counts = report.counts_by_severity
    severities = ["critical", "warning", "info"]
    severity_values = [counts.get(s, 0) for s in severities]
    severity_colors = [SEVERITY_COLORS[s] for s in severities]

    category_counts = {}
    for issue in report.all_issues:
        cat = _category_for(issue.rule_id)
        category_counts[cat] = category_counts.get(cat, 0) + 1
    categories = list(category_counts.keys())
    category_values = [category_counts[c] for c in categories]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    # Panel 1: by severity
    bars1 = ax1.bar(severities, severity_values, color=severity_colors, edgecolor="black")
    ax1.set_title("Issues by Severity", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Count")
    ax1.set_ylim(0, max(severity_values + [1]) + 1)
    for bar in bars1:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2, h + 0.05, str(int(h)),
                  ha="center", va="bottom", fontsize=10)

    # Panel 2: by category
    if categories:
        bars2 = ax2.bar(categories, category_values, color="#548235", edgecolor="black")
        for bar in bars2:
            h = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, h + 0.05, str(int(h)),
                      ha="center", va="bottom", fontsize=10)
    ax2.set_title("Issues by Category", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Count")
    plt.setp(ax2.get_xticklabels(), rotation=20, ha="right")

    total = len(report.all_issues)
    fig.suptitle(f"Static Analysis Report Summary — {total} issue(s) found",
                 fontsize=13, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path
