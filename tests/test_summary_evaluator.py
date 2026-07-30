from pathlib import Path

from webpilot.evaluator import WebPilotEvaluator
from webpilot.schemas import (
    BrowserRunResult,
    EvaluationSummary,
    RepairResult,
    RunSummary,
)


def test_evaluator_record_separates_project_edit_from_repair_for_editing_base(
    tmp_path: Path,
) -> None:
    run_summary = RunSummary(
        task_id="sample_editing_secondary_cta",
        task_type="editing",
        variant="base",
        status="edited_and_verified",
        run_dir="outputs/sample_editing_secondary_cta/run",
        message="Editing passed.",
        browser=_browser_result(
            status="ok",
            test_status="passed",
            passed_test_count=2,
            failed_test_count=0,
        ),
        project_edit=RepairResult(
            status="applied",
            reason="Applied LLM-generated frontend edit.",
            changed_files=["src/App.jsx"],
        ),
        repair=None,
    )

    record = WebPilotEvaluator(project_root=tmp_path)._build_record(run_summary)

    assert record.task_type == "editing"
    assert record.variant == "base"
    assert record.final_test_status == "passed"
    assert record.project_edit_status == "applied"
    assert record.repair_status is None


def test_evaluator_record_tracks_repair_for_diagnostic_repair(
    tmp_path: Path,
) -> None:
    run_summary = RunSummary(
        task_id="sample_nav_repair",
        task_type="diagnostic_repair",
        variant="llm-browser-feedback",
        status="repaired_and_verified",
        run_dir="outputs/sample_nav_repair/run",
        message="Repair passed.",
        initial_browser=_browser_result(
            status="loaded_with_test_failures",
            test_status="failed",
            passed_test_count=0,
            failed_test_count=1,
        ),
        browser=_browser_result(
            status="ok",
            test_status="passed",
            passed_test_count=1,
            failed_test_count=0,
        ),
        project_edit=None,
        repair=RepairResult(
            status="applied",
            reason="Applied browser-grounded repair.",
            changed_files=["src/App.jsx"],
        ),
    )

    record = WebPilotEvaluator(project_root=tmp_path)._build_record(run_summary)

    assert record.task_type == "diagnostic_repair"
    assert record.variant == "llm-browser-feedback"
    assert record.initial_test_status == "failed"
    assert record.final_test_status == "passed"
    assert record.project_edit_status is None
    assert record.repair_status == "applied"


def test_repaired_runs_count_only_repair_status_not_project_edit(
    tmp_path: Path,
) -> None:
    evaluator = WebPilotEvaluator(project_root=tmp_path)

    editing_record = evaluator._build_record(
        RunSummary(
            task_id="sample_editing_newsletter",
            task_type="editing",
            variant="base",
            status="edited_and_verified",
            run_dir="outputs/editing/run",
            message="Editing passed.",
            browser=_browser_result(
                status="ok",
                test_status="passed",
                passed_test_count=4,
                failed_test_count=0,
            ),
            project_edit=RepairResult(
                status="applied",
                reason="Applied LLM-generated frontend edit.",
                changed_files=["src/App.jsx"],
            ),
            repair=None,
        )
    )

    repair_record = evaluator._build_record(
        RunSummary(
            task_id="sample_tabs_repair",
            task_type="diagnostic_repair",
            variant="llm-browser-feedback",
            status="repaired_and_verified",
            run_dir="outputs/repair/run",
            message="Repair passed.",
            initial_browser=_browser_result(
                status="loaded_with_test_failures",
                test_status="failed",
                passed_test_count=0,
                failed_test_count=1,
            ),
            browser=_browser_result(
                status="ok",
                test_status="passed",
                passed_test_count=1,
                failed_test_count=0,
            ),
            project_edit=None,
            repair=RepairResult(
                status="applied",
                reason="Applied LLM-generated repair.",
                changed_files=["src/App.jsx"],
            ),
        )
    )

    records = [editing_record, repair_record]
    repaired_runs = sum(record.repair_status == "applied" for record in records)

    assert editing_record.project_edit_status == "applied"
    assert editing_record.repair_status is None
    assert repair_record.repair_status == "applied"
    assert repaired_runs == 1


def test_markdown_report_shows_project_edit_and_repair_separately(
    tmp_path: Path,
) -> None:
    evaluator = WebPilotEvaluator(project_root=tmp_path)

    editing_record = evaluator._build_record(
        RunSummary(
            task_id="sample_editing_testimonials",
            task_type="editing",
            variant="base",
            status="edited_and_verified",
            run_dir="outputs/editing/run",
            message="Editing passed.",
            browser=_browser_result(
                status="ok",
                test_status="passed",
                passed_test_count=5,
                failed_test_count=0,
            ),
            project_edit=RepairResult(
                status="applied",
                reason="Applied LLM-generated frontend edit.",
                changed_files=["src/App.jsx"],
            ),
            repair=None,
        )
    )

    repair_record = evaluator._build_record(
        RunSummary(
            task_id="sample_form_overflow_repair",
            task_type="diagnostic_repair",
            variant="llm-browser-feedback",
            status="repaired_and_verified",
            run_dir="outputs/repair/run",
            message="Repair passed.",
            initial_browser=_browser_result(
                status="loaded_with_test_failures",
                test_status="failed",
                passed_test_count=0,
                failed_test_count=4,
            ),
            browser=_browser_result(
                status="ok",
                test_status="passed",
                passed_test_count=4,
                failed_test_count=0,
            ),
            project_edit=None,
            repair=RepairResult(
                status="applied",
                reason="Applied LLM-generated repair.",
                changed_files=["src/App.jsx", "src/App.css"],
            ),
        )
    )

    summary = EvaluationSummary(
        evaluation_id="test_eval",
        output_dir=str(tmp_path),
        total_runs=2,
        passed_runs=2,
        failed_runs=0,
        repaired_runs=1,
        records=[editing_record, repair_record],
    )

    report_path = tmp_path / "evaluation_report.md"
    evaluator._write_markdown_report(report_path, summary)

    report = report_path.read_text(encoding="utf-8")

    assert "| Task | Variant | Run status | Initial test | Final test | Exec | Interaction | Visual sanity | Project edit | Repair | Project files | Repair files | Total files | Passed checks | Failed checks | Run directory |" in report
    assert "sample_editing_testimonials | base | edited_and_verified | - | passed | 1.0000 | 1.0000 | 0.5000 | applied | - | 1 | 0 | 1 | 5 | 0 |" in report
    assert "sample_form_overflow_repair | llm-browser-feedback | repaired_and_verified | failed | passed | 1.0000 | 1.0000 | 0.5000 | - | applied | 0 | 2 | 2 | 4 | 0 |" in report
    assert "| Repaired runs | 1 |" in report


def _browser_result(
    *,
    status: str,
    test_status: str,
    passed_test_count: int,
    failed_test_count: int,
) -> BrowserRunResult:
    return BrowserRunResult(
        repo_path="workspace",
        url="http://127.0.0.1:3000/",
        port=3000,
        status=status,
        artifacts={},
        console_log_count=0,
        page_error_count=0,
        test_status=test_status,
        passed_test_count=passed_test_count,
        failed_test_count=failed_test_count,
    )
