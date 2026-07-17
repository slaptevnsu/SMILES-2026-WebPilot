from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from webpilot.browser import BrowserExecutor
from webpilot.repairer import DeterministicRepairer
from webpilot.schemas import AgentVariant, BrowserRunResult, Plan, RunSummary, Task, RepairResult


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

        initial_browser_result: BrowserRunResult | None = None
        final_browser_result: BrowserRunResult | None = None
        repair_result: RepairResult | None = None

        if task.task_type == "diagnostic_repair":
            if task.repo_path is None:
                raise ValueError("diagnostic_repair task must define repo_path")

            source_repo_path = self._resolve_path(task.repo_path)
            workspace_repo_path = self._prepare_workspace_repo(
                source_repo_path=source_repo_path,
                run_dir=run_dir,
            )

            initial_browser_result = BrowserExecutor().run(
                repo_path=workspace_repo_path,
                run_dir=run_dir / "initial_browser",
                task=task,
            )
            final_browser_result = initial_browser_result

            if variant == "deterministic-browser-feedback" and initial_browser_result.failed_test_count > 0:
                repair_result = DeterministicRepairer().run(
                    repo_path=workspace_repo_path,
                    run_dir=run_dir,
                    task=task,
                    browser_result=initial_browser_result,
                )

                if repair_result.status == "applied":
                    final_browser_result = BrowserExecutor().run(
                        repo_path=workspace_repo_path,
                        run_dir=run_dir / "repaired_browser",
                        task=task,
                    )

                    if final_browser_result.status == "ok":
                        status = "repaired_and_verified"
                        message = (
                            "Stage 5 completed: the initial browser run detected an interaction failure, "
                            "a deterministic repair was applied, and the repaired app passed browser verification."
                        )
                    else:
                        status = "repair_attempted_with_issues"
                        message = (
                            "Stage 5 completed with issues: a repair was applied, "
                            "but the repaired app still did not pass browser verification."
                        )
                else:
                    status = "repair_skipped_or_failed"
                    message = (
                        "Stage 5 completed with issues: the initial browser run detected a failure, "
                        "but no repair was successfully applied."
                    )

            else:
                status = (
                    "browser_executed"
                    if final_browser_result.status == "ok"
                    else "browser_executed_with_issues"
                )
                message = (
                    "Stage 4 completed: task was loaded, the frontend app was launched in a browser, "
                    "browser artifacts were saved, and interaction tests were executed."
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
            browser=final_browser_result,
            initial_browser=initial_browser_result,
            repair=repair_result,
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
        
        if variant == "deterministic-browser-feedback":
            steps.extend(
                [
                    "Diagnose failures using collected browser evidence",
                    "Apply a deterministic repair patch if possible",
                    "Re-run the browser execution after repair",
                    "Verify that the repaired project passes the interaction check",
                ]
            )

        expected_artifacts = [
            "task.json",
            "plan.json",
            "summary.json",
            "workspace/",
            "initial_browser/npm_install.log",
            "initial_browser/dev_server.log",
            "initial_browser/screenshot.png",
            "initial_browser/dom_snapshot.html",
            "initial_browser/console_logs.json",
            "initial_browser/page_errors.json",
            "initial_browser/test_results.json",
            "initial_browser/browser_result.json",
        ]

        if variant == "deterministic-browser-feedback":
            expected_artifacts.extend(
                [
                    "repair_plan.json",
                    "patch.diff",
                    "repaired_browser/npm_install.log",
                    "repaired_browser/dev_server.log",
                    "repaired_browser/screenshot.png",
                    "repaired_browser/dom_snapshot.html",
                    "repaired_browser/console_logs.json",
                    "repaired_browser/page_errors.json",
                    "repaired_browser/test_results.json",
                    "repaired_browser/browser_result.json",
                ]
            )

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
    
    def _prepare_workspace_repo(self, source_repo_path: Path, run_dir: Path) -> Path:
        source_repo_path = source_repo_path.resolve()

        workspace_root = run_dir / "workspace"
        workspace_repo_path = workspace_root / source_repo_path.name

        shutil.copytree(
            source_repo_path,
            workspace_repo_path,
            ignore=shutil.ignore_patterns(
                "node_modules",
                "dist",
                ".vite",
                ".git",
                "playwright-report",
                "test-results",
            ),
        )

        return workspace_repo_path
    
    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.project_root / path
    
    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")