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

        self._write_json(output_dir / "evaluation_summary.json", summary.model_dump(mode="json"))
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