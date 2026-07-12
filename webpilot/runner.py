from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webpilot.browser import BrowserExecutor
from webpilot.schemas import AgentVariant, BrowserRunResult, Plan, RunSummary, Task


class WebPilotRunner:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()

    def run(
        self,
        task_path: Path,
        variant: AgentVariant,
        max_iterations: int | None = None
    ) -> RunSummary:
        task = self._load_task(task_path)

        if max_iterations is not None:
            task.max_iterations = max_iterations
        
        plan = self._build_initial_plan(task=task, variant=variant)
        run_dir = self._create_run_dir(task_id=task.id)

        self._write_json(run_dir / "task.json", task.model_dump(mode="json", by_alias=True))
        self._write_json(run_dir / "plan.json", plan.model_dump(mode="json"))

        browser_result: BrowserRunResult | None = None

        if task.task_type == "diagnostic_repair":
            if task.repo_path is None:
                raise ValueError("diagnostic_repair task must define repo_path")

            repo_path = self._resolve_path(task.repo_path)
            browser_result = BrowserExecutor().run(repo_path=repo_path, run_dir=run_dir)

            status = "browser_executed" if browser_result.status == "ok" else "browser_executed_with_issues"
            message = (
                "Stage 3 completed: task was loaded, an initial plan was created, "
                "the frontend app was launched in a browser, and browser artifacts were saved."
            )
        else:
            status = "planned_only"
            message = (
                "Stage 1 completed: task was loaded, an initial plan was created, "
                "and artifacts were saved. Browser execution for text_generation is not implemented yet."
            )

        summary = RunSummary(
            task_id=task.id,
            task_type=task.task_type,
            variant=variant,
            status=status,
            run_dir=str(run_dir),
            message=message,
            browser=browser_result,
        )

        self._write_json(run_dir / "summary.json", summary.model_dump(mode="json"))
        return summary

    def _load_task(self, task_path: Path) -> Task:
        full_path = self._resolve_path(task_path)
        with full_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return Task.model_validate(data)

    def _build_initial_plan(self, task: Task, variant: AgentVariant) -> Plan:
        steps = [
            "Read task specification",
            "Prepare working directory",
        ]

        if task.task_type == "text_generation":
            steps.extend(
                [
                    "Generate a minimal frontend project from the text instruction",
                    "Run the generated project in a browser",
                    "Collect screenshot, DOM snapshot, console logs, and page errors",
                    "Run basic interaction checks",
                ]
            )
        elif task.task_type == "diagnostic_repair":
            steps.extend(
                [
                    "Copy the provided buggy frontend repository into a run workspace",
                    "Run the project in a browser",
                    "Collect screenshot, DOM snapshot, console logs, and page errors",
                    "Run a diagnostic interaction check",
                ]
            )
        
        if variant == "browser-feedback":
            steps.extend(
                [
                    "Diagnose failures using collected browser evidence",
                    "Apply a repair patch if possible",
                    "Re-run the browser execution after repair",
                ]
            )

        expected_artifacts = [
            "task.json",
            "plan.json",
            "summary.json",
            "npm_install.log",
            "dev_server.log",
            "screenshot.png",
            "dom_snapshot.html",
            "console_logs.json",
            "page_errors.json",
            "browser_result.json",
            "test_results.json",
        ]

        if task.task_type == "diagnostic_repair":
            expected_artifacts.extend(["repair_plan.json", "patch.diff"])

        return Plan(
            task_id=task.id,
            task_type=task.task_type,
            variant=variant,
            steps=steps,
            expected_artifacts=expected_artifacts,
        )
    
    def _create_run_dir(self, task_id: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.project_root / "outputs" / task_id / timestamp
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir
    
    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.project_root / path
    
    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")