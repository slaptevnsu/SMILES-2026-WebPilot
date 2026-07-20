from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webpilot.runner import WebPilotRunner
from webpilot.schemas import AgentVariant, EvaluationRunRecord, EvaluationSummary, RunSummary


class WebPilotEvaluator:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()

    def evaluate(
        self,
        task_paths: list[Path],
        variants: list[AgentVariant] | None = None,
    ) -> EvaluationSummary:
        variants = variants or ["base", "deterministic-browser-feedback"]

        evaluation_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.project_root / "outputs" / "evaluations" / evaluation_id
        output_dir.mkdir(parents=True, exist_ok=False)

        records: list[EvaluationRunRecord] = []

        runner = WebPilotRunner(project_root=self.project_root)

        for task_path in task_paths:
            for variant in variants:
                run_summary = runner.run(task_path=task_path, variant=variant)
                record = self._build_record(run_summary)
                records.append(record)

        passed_runs = sum(record.final_test_status == "passed" for record in records)
        failed_runs = sum(record.final_test_status == "failed" for record in records)
        repaired_runs = sum(record.repair_status == "applied" for record in records)

        summary = EvaluationSummary(
            evaluation_id=evaluation_id,
            output_dir=str(output_dir),
            total_runs=len(records),
            passed_runs=passed_runs,
            failed_runs=failed_runs,
            repaired_runs=repaired_runs,
            records=records,
        )

        self._write_json(
            output_dir / "evaluation_summary.json",
            summary.model_dump(mode="json"),
        )
        self._write_jsonl(
            output_dir / "evaluation_records.jsonl",
            [record.model_dump(mode="json") for record in records],
        )
        self._write_markdown_report(
            output_dir / "evaluation_report.md",
            summary,
        )

        return summary

    def _build_record(self, run_summary: RunSummary) -> EvaluationRunRecord:
        final_browser = run_summary.browser
        initial_browser = run_summary.initial_browser
        repair = run_summary.repair

        return EvaluationRunRecord(
            task_id=run_summary.task_id,
            task_type=run_summary.task_type,
            variant=run_summary.variant,
            status=run_summary.status,
            run_dir=run_summary.run_dir,
            final_browser_status=final_browser.status if final_browser else None,
            final_test_status=final_browser.test_status if final_browser else None,
            passed_test_count=final_browser.passed_test_count if final_browser else 0,
            failed_test_count=final_browser.failed_test_count if final_browser else 0,
            initial_browser_status=initial_browser.status if initial_browser else None,
            initial_test_status=initial_browser.test_status if initial_browser else None,
            repair_status=repair.status if repair else None,
        )

    def _write_json(self, path: Path, data: Any) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False))
                file.write("\n")

    def _write_markdown_report(
        self,
        path: Path,
        summary: EvaluationSummary,
    ) -> None:
        lines = [
            "# WebPilot Evaluation Report",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Evaluation ID | `{summary.evaluation_id}` |",
            f"| Total runs | {summary.total_runs} |",
            f"| Passed runs | {summary.passed_runs} |",
            f"| Failed runs | {summary.failed_runs} |",
            f"| Repaired runs | {summary.repaired_runs} |",
            "",
            "## Results",
            "",
            "| Task | Variant | Run status | Initial test | Final test | Repair | Passed checks | Failed checks | Run directory |",
            "|---|---|---|---|---|---|---:|---:|---|",
        ]

        for record in summary.records:
            lines.append(
                "| "
                f"{record.task_id} | "
                f"{record.variant} | "
                f"{record.status} | "
                f"{self._format_optional(record.initial_test_status)} | "
                f"{self._format_optional(record.final_test_status)} | "
                f"{self._format_optional(record.repair_status)} | "
                f"{record.passed_test_count} | "
                f"{record.failed_test_count} | "
                f"`{record.run_dir}` |"
            )

        interpretation_lines = self._build_interpretation_lines(summary)

        lines.extend(
            [
                "",
                "## Interpretation",
                "",
                *interpretation_lines,
                "",
                "## Generated artifacts",
                "",
                "- `evaluation_summary.json`: full structured evaluation summary.",
                "- `evaluation_records.jsonl`: one machine-readable record per run.",
                "- `evaluation_report.md`: this human-readable report.",
                "",
            ]
        )

        path.write_text("\n".join(lines), encoding="utf-8")

    def _format_optional(self, value: Any) -> str:
        if value is None:
            return "-"
        return str(value)
    
    def _build_interpretation_lines(self, summary: EvaluationSummary) -> list[str]:
        variants = {record.variant for record in summary.records}

        lines = []

        if "base" in variants:
            lines.append(
                "- `base` runs execute the task without repair and are expected to fail on diagnostic repair tasks."
            )

        if "deterministic-browser-feedback" in variants:
            lines.append(
                "- `deterministic-browser-feedback` is a rule-based sanity baseline."
            )

        if "llm-code-only" in variants:
            lines.append(
                "- `llm-code-only` uses an LLM planner and repairer without passing browser feedback into the repair prompt."
            )

        if "llm-test-synthesis" in variants:
            lines.append(
                "- `llm-test-synthesis` uses an LLM test planner to propose interaction checks and passes them as additional repair context. Final evaluation still uses oracle checks from the task specification."
            )

        if "llm-browser-feedback" in variants:
            lines.append(
                "- `llm-browser-feedback` uses an LLM planner, browser-grounded reflector, and repairer with browser/test evidence."
            )

        return lines
