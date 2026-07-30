from pathlib import Path

from webpilot.metrics import (
    executability_score,
    interaction_correctness_score,
    project_edit_applied,
    project_edit_touched_files_count,
    repair_applied,
    repair_touched_files_count,
    total_touched_files_count,
    visual_sanity_score,
)
from webpilot.schemas import BrowserRunResult, RepairResult, RunSummary


def test_executability_score_returns_one_for_ok_browser() -> None:
    browser = _browser_result(status="ok")

    assert executability_score(browser) == 1.0


def test_executability_score_returns_zero_for_failed_or_missing_browser() -> None:
    assert executability_score(None) == 0.0
    assert executability_score(_browser_result(status="failed")) == 0.0


def test_interaction_correctness_score_returns_pass_fraction() -> None:
    browser = _browser_result(
        status="ok",
        passed_test_count=3,
        failed_test_count=1,
    )

    assert interaction_correctness_score(browser) == 0.75


def test_interaction_correctness_score_returns_zero_without_checks() -> None:
    browser = _browser_result(
        status="ok",
        passed_test_count=0,
        failed_test_count=0,
    )

    assert interaction_correctness_score(None) == 0.0
    assert interaction_correctness_score(browser) == 0.0


def test_project_edit_and_repair_applied_are_separate() -> None:
    editing_summary = RunSummary(
        task_id="sample_editing_newsletter",
        task_type="editing",
        variant="base",
        status="edited_and_verified",
        run_dir="outputs/editing/run",
        message="Editing passed.",
        project_edit=RepairResult(
            status="applied",
            reason="Applied LLM-generated frontend edit.",
            changed_files=["src/App.jsx"],
        ),
        repair=None,
    )

    repair_summary = RunSummary(
        task_id="sample_nav_repair",
        task_type="diagnostic_repair",
        variant="llm-browser-feedback",
        status="repaired_and_verified",
        run_dir="outputs/repair/run",
        message="Repair passed.",
        project_edit=None,
        repair=RepairResult(
            status="applied",
            reason="Applied browser-grounded repair.",
            changed_files=["src/App.jsx"],
        ),
    )

    assert project_edit_applied(editing_summary) is True
    assert repair_applied(editing_summary) is False

    assert project_edit_applied(repair_summary) is False
    assert repair_applied(repair_summary) is True


def test_touched_files_counts_project_edit_and_repair_separately() -> None:
    summary = RunSummary(
        task_id="sample_generated_repaired",
        task_type="text_generation",
        variant="llm-browser-feedback",
        status="generated_repaired_and_verified",
        run_dir="outputs/generated/run",
        message="Generated and repaired.",
        project_edit=RepairResult(
            status="applied",
            reason="Applied LLM-generated frontend implementation.",
            changed_files=["src/App.jsx", "src/App.css"],
        ),
        repair=RepairResult(
            status="applied",
            reason="Applied LLM-generated repair.",
            changed_files=["src/App.jsx"],
        ),
    )

    assert project_edit_touched_files_count(summary) == 2
    assert repair_touched_files_count(summary) == 1
    assert total_touched_files_count(summary) == 2


def test_visual_sanity_score_uses_browser_artifacts(tmp_path: Path) -> None:
    screenshot = tmp_path / "screenshot.png"
    dom_snapshot = tmp_path / "dom_snapshot.html"

    screenshot.write_bytes(b"fake-image")
    dom_snapshot.write_text("<html><body><main>Hello</main></body></html>", encoding="utf-8")

    browser = _browser_result(
        status="ok",
        page_error_count=0,
        artifacts={
            "screenshot": str(screenshot),
            "dom_snapshot": str(dom_snapshot),
        },
    )

    assert visual_sanity_score(browser) == 1.0


def test_visual_sanity_score_penalizes_missing_or_bad_signals(tmp_path: Path) -> None:
    dom_snapshot = tmp_path / "dom_snapshot.html"
    dom_snapshot.write_text("", encoding="utf-8")

    browser = _browser_result(
        status="loaded_with_test_failures",
        page_error_count=2,
        artifacts={
            "screenshot": str(tmp_path / "missing.png"),
            "dom_snapshot": str(dom_snapshot),
        },
    )

    assert visual_sanity_score(browser) == 0.0


def _browser_result(
    *,
    status: str,
    test_status: str | None = "passed",
    passed_test_count: int = 0,
    failed_test_count: int = 0,
    page_error_count: int = 0,
    artifacts: dict[str, str] | None = None,
) -> BrowserRunResult:
    return BrowserRunResult(
        repo_path="workspace",
        url="http://127.0.0.1:3000/",
        port=3000,
        status=status,
        artifacts=artifacts or {},
        console_log_count=0,
        page_error_count=page_error_count,
        test_status=test_status,
        passed_test_count=passed_test_count,
        failed_test_count=failed_test_count,
    )
