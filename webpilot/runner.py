from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from webpilot.agents import LLMPlanner, LLMReflector, LLMRepairer
from webpilot.browser import BrowserExecutor
from webpilot.repairer import DeterministicRepairer
from webpilot.schemas import (
    AgentVariant,
    BrowserRunResult,
    Plan,
    RepairIterationRecord,
    RepairResult,
    RunSummary,
    Task,
)


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
        repair_iterations: list[RepairIterationRecord] = []

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

            repair_variants = [
                "deterministic-browser-feedback",
                "llm-code-only",
                "llm-browser-feedback",
            ]

            repair_descriptions = {
                "deterministic-browser-feedback": "a deterministic repair",
                "llm-code-only": "an LLM-generated code-only repair",
                "llm-browser-feedback": "an LLM-generated browser-feedback repair",
            }

            if variant in repair_variants and final_browser_result.status != "ok":
                for iteration in range(1, task.max_iterations + 1):
                    iteration_dir = run_dir / f"repair_iteration_{iteration:02d}"
                    iteration_dir.mkdir(parents=True, exist_ok=True)

                    if variant == "deterministic-browser-feedback":
                        repair_result = DeterministicRepairer().run(
                            repo_path=workspace_repo_path,
                            run_dir=iteration_dir,
                            task=task,
                            browser_result=final_browser_result,
                        )

                    else:
                        include_browser_feedback = variant == "llm-browser-feedback"

                        llm_plan = LLMPlanner().run(
                            task=task,
                            repo_path=workspace_repo_path,
                            run_dir=iteration_dir,
                        )

                        llm_diagnosis = None
                        if include_browser_feedback:
                            llm_diagnosis = LLMReflector().run(
                                task=task,
                                browser_result=final_browser_result,
                                run_dir=iteration_dir,
                                repo_path=workspace_repo_path,
                            )

                        repair_result = LLMRepairer().run(
                            repo_path=workspace_repo_path,
                            run_dir=iteration_dir,
                            task=task,
                            browser_result=final_browser_result,
                            include_browser_feedback=include_browser_feedback,
                            llm_plan=llm_plan,
                            llm_diagnosis=llm_diagnosis,
                        )

                    if repair_result.status != "applied":
                        repair_iterations.append(
                            RepairIterationRecord(
                                iteration=iteration,
                                status="repair_skipped_or_failed",
                                repair=repair_result,
                                browser=None,
                            )
                        )
                        break

                    final_browser_result = BrowserExecutor().run(
                        repo_path=workspace_repo_path,
                        run_dir=iteration_dir / "browser_after",
                        task=task,
                    )

                    iteration_status = (
                        "verified"
                        if final_browser_result.status == "ok"
                        else "still_failing"
                    )

                    repair_iterations.append(
                        RepairIterationRecord(
                            iteration=iteration,
                            status=iteration_status,
                            repair=repair_result,
                            browser=final_browser_result,
                        )
                    )

                    if final_browser_result.status == "ok":
                        break

                if final_browser_result.status == "ok":
                    status = "repaired_and_verified"
                    message = (
                        "The initial browser run detected a failure, "
                        f"{repair_descriptions[variant]} was applied, and the repaired app passed browser verification."
                    )
                elif repair_result is not None and repair_result.status == "applied":
                    status = "repair_attempted_with_issues"
                    message = (
                        "One or more repair iterations were applied, "
                        "but the app still did not pass browser verification."
                    )
                else:
                    status = "repair_skipped_or_failed"
                    message = (
                        "The browser run detected a failure, "
                        "but no repair was successfully applied."
                    )
            else:
                status = (
                    "browser_executed"
                    if final_browser_result.status == "ok"
                    else "browser_executed_with_issues"
                )
                message = (
                    "Task was loaded, the frontend app was launched in a browser, "
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
            repair_iterations=repair_iterations,
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

        elif variant == "llm-code-only":
            steps.extend(
                [
                    "Ask an LLM planner to produce a concise repair plan from the task and source file",
                    "Ask an LLM repair agent to repair the source code using the task, source file, and repair plan",
                    "Re-run the browser execution after repair",
                    "Verify that the repaired project passes the interaction check",
                ]
            )

        elif variant == "llm-browser-feedback":
            steps.extend(
                [
                    "Ask an LLM planner to produce a concise repair plan from the task and source file",
                    "Ask an LLM reflector to diagnose the failure using browser evidence",
                    "Ask an LLM repair agent to repair the source code using the task, source file, repair plan, diagnosis, and browser feedback",
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
                    "repair_iteration_<n>/repair_plan.json",
                    "repair_iteration_<n>/patch.diff",
                    "repair_iteration_<n>/browser_after/npm_install.log",
                    "repair_iteration_<n>/browser_after/dev_server.log",
                    "repair_iteration_<n>/browser_after/screenshot.png",
                    "repair_iteration_<n>/browser_after/dom_snapshot.html",
                    "repair_iteration_<n>/browser_after/console_logs.json",
                    "repair_iteration_<n>/browser_after/page_errors.json",
                    "repair_iteration_<n>/browser_after/test_results.json",
                    "repair_iteration_<n>/browser_after/browser_result.json",
                ]
            )

        elif variant in ["llm-code-only", "llm-browser-feedback"]:
            expected_artifacts.extend(
                [
                    "repair_iteration_<n>/llm_plan/llm_plan_prompt.txt",
                    "repair_iteration_<n>/llm_plan/llm_plan_response.txt",
                    "repair_iteration_<n>/llm_repair/llm_prompt.txt",
                    "repair_iteration_<n>/llm_repair/llm_response.txt",
                    "repair_iteration_<n>/llm_repair/repair_plan.json",
                    "repair_iteration_<n>/llm_repair/patch.diff",
                    "repair_iteration_<n>/browser_after/npm_install.log",
                    "repair_iteration_<n>/browser_after/dev_server.log",
                    "repair_iteration_<n>/browser_after/screenshot.png",
                    "repair_iteration_<n>/browser_after/dom_snapshot.html",
                    "repair_iteration_<n>/browser_after/console_logs.json",
                    "repair_iteration_<n>/browser_after/page_errors.json",
                    "repair_iteration_<n>/browser_after/test_results.json",
                    "repair_iteration_<n>/browser_after/browser_result.json",
                ]
            )

            if variant == "llm-browser-feedback":
                expected_artifacts.extend(
                    [
                        "repair_iteration_<n>/llm_reflection/llm_reflection_prompt.txt",
                        "repair_iteration_<n>/llm_reflection/llm_reflection_response.txt",
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