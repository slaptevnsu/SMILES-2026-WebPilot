from __future__ import annotations

from pathlib import Path

from webpilot.schemas import BrowserRunResult, RunSummary


def executability_score(browser: BrowserRunResult | None) -> float:
    """Return 1.0 when the browser run completed successfully, otherwise 0.0."""
    if browser is None:
        return 0.0

    return 1.0 if browser.status == "ok" else 0.0


def interaction_correctness_score(browser: BrowserRunResult | None) -> float:
    """Return the fraction of passed oracle interaction checks."""
    if browser is None:
        return 0.0

    total = browser.passed_test_count + browser.failed_test_count
    if total == 0:
        return 0.0

    return round(browser.passed_test_count / total, 4)


def project_edit_applied(summary: RunSummary) -> bool:
    """Return whether the initial project edit/generation step applied changes."""
    return summary.project_edit is not None and summary.project_edit.status == "applied"


def repair_applied(summary: RunSummary) -> bool:
    """Return whether a true repair step applied changes."""
    return summary.repair is not None and summary.repair.status == "applied"


def project_edit_touched_files_count(summary: RunSummary) -> int:
    """Return the number of files changed by the project edit/generation step."""
    if summary.project_edit is None:
        return 0

    return len(summary.project_edit.changed_files)


def repair_touched_files_count(summary: RunSummary) -> int:
    """Return the number of files changed by the repair step."""
    if summary.repair is None:
        return 0

    return len(summary.repair.changed_files)


def total_touched_files_count(summary: RunSummary) -> int:
    """Return the number of unique files touched by project_edit and repair together."""
    touched_files = set()

    if summary.project_edit is not None:
        touched_files.update(summary.project_edit.changed_files)

    if summary.repair is not None:
        touched_files.update(summary.repair.changed_files)

    return len(touched_files)


def visual_sanity_score(browser: BrowserRunResult | None) -> float:
    """Compute a lightweight non-LLM visual sanity score.

    This is not a visual quality score. It only checks browser-level artifacts and
    simple runtime signals:
    - browser status is ok;
    - no page errors were reported;
    - screenshot artifact exists when provided;
    - DOM snapshot artifact exists and is non-empty when provided.
    """
    if browser is None:
        return 0.0

    checks = [
        browser.status == "ok",
        browser.page_error_count == 0,
        _artifact_exists(browser, "screenshot"),
        _artifact_exists(browser, "dom_snapshot") and _artifact_non_empty(browser, "dom_snapshot"),
    ]

    return round(sum(checks) / len(checks), 4)


def _artifact_exists(browser: BrowserRunResult, key: str) -> bool:
    path = browser.artifacts.get(key)
    if not path:
        return False

    return Path(path).exists()


def _artifact_non_empty(browser: BrowserRunResult, key: str) -> bool:
    path = browser.artifacts.get(key)
    if not path:
        return False

    artifact_path = Path(path)
    return artifact_path.exists() and artifact_path.stat().st_size > 0
