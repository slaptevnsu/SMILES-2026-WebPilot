from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webpilot.llm_client import LLMClient
from webpilot.project_context import ProjectContextCollector
from webpilot.project_edit import (
    apply_file_changes,
    extract_file_changes,
    parse_llm_json_response,
    write_changed_files_artifact,
    write_project_patch,
)
from webpilot.schemas import BrowserRunResult, RepairResult, Task


MAX_TEXT_ARTIFACT_CHARS = 4000
MAX_DOM_SNAPSHOT_CHARS = 6000


class LLMRepairer:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        *,
        task: Task,
        repo_path: Path,
        run_dir: Path,
        browser_result: BrowserRunResult | None = None,
        include_browser_feedback: bool = False,
        llm_plan: str | None = None,
        llm_diagnosis: str | None = None,
        test_proposal: dict[str, Any] | None = None,
    ) -> RepairResult:
        repair_dir = run_dir / "llm_repair"
        repair_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {
            "llm_prompt": str(repair_dir / "llm_prompt.txt"),
            "llm_response": str(repair_dir / "llm_response.txt"),
            "repair_plan": str(repair_dir / "repair_plan.json"),
            "patch": str(repair_dir / "patch.diff"),
            "changed_files": str(repair_dir / "changed_files.json"),
        }

        if task.task_type not in ["diagnostic_repair", "text_generation"]:
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="skipped",
                reason="LLMRepairer currently supports only diagnostic_repair and text_generation tasks.",
                task=task,
                include_browser_feedback=include_browser_feedback,
                changed_paths=[],
            )
            return RepairResult(
                status="skipped",
                reason="LLMRepairer currently supports only diagnostic_repair and text_generation tasks.",
                target_file=None,
                artifacts=artifacts,
            )

        collector = ProjectContextCollector()
        project_files = collector.collect(repo_path=repo_path)

        if not project_files:
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="failed",
                reason="No editable frontend project files were found.",
                task=task,
                include_browser_feedback=include_browser_feedback,
                changed_paths=[],
            )
            return RepairResult(
                status="failed",
                reason="No editable frontend project files were found.",
                target_file=None,
                artifacts=artifacts,
            )

        before_by_path = {file.path: file.content for file in project_files}
        project_context = collector.format_for_prompt(project_files)

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            task=task,
            project_context=project_context,
            browser_result=browser_result,
            include_browser_feedback=include_browser_feedback,
            llm_plan=llm_plan,
            llm_diagnosis=llm_diagnosis,
            test_proposal=test_proposal,
        )

        Path(artifacts["llm_prompt"]).write_text(
            self._format_full_prompt(system_prompt, user_prompt),
            encoding="utf-8",
        )

        try:
            raw_response = self.client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="failed",
                reason=f"LLM call failed: {exc}",
                task=task,
                include_browser_feedback=include_browser_feedback,
                changed_paths=[],
            )
            return RepairResult(
                status="failed",
                reason=f"LLM call failed: {exc}",
                target_file=None,
                artifacts=artifacts,
            )

        Path(artifacts["llm_response"]).write_text(raw_response, encoding="utf-8")

        try:
            parsed_response = parse_llm_json_response(raw_response)
            changes = extract_file_changes(parsed_response)
            applied_changes = apply_file_changes(
                repo_path=repo_path,
                before_by_path=before_by_path,
                changes=changes,
            )
        except Exception as exc:
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="failed",
                reason=f"Failed to parse or apply LLM file changes: {exc}",
                task=task,
                include_browser_feedback=include_browser_feedback,
                changed_paths=[],
            )
            write_changed_files_artifact(
                path=Path(artifacts["changed_files"]),
                status="failed",
                applied_changes=[],
                error=exc,
            )
            return RepairResult(
                status="failed",
                reason=f"Failed to parse or apply LLM file changes: {exc}",
                target_file=None,
                artifacts=artifacts,
            )

        if not applied_changes:
            write_project_patch(
                path=Path(artifacts["patch"]),
                applied_changes=[],
            )
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="skipped",
                reason="LLM returned no effective file changes.",
                task=task,
                include_browser_feedback=include_browser_feedback,
                changed_paths=[],
            )
            write_changed_files_artifact(
                path=Path(artifacts["changed_files"]),
                status="skipped",
                applied_changes=[],
                rationale=parsed_response.get("rationale", ""),
            )
            return RepairResult(
                status="skipped",
                reason="LLM returned no effective file changes.",
                target_file=None,
                artifacts=artifacts,
            )

        changed_paths = [change.path for change in applied_changes]

        write_project_patch(
            path=Path(artifacts["patch"]),
            applied_changes=applied_changes,
        )

        write_changed_files_artifact(
            path=Path(artifacts["changed_files"]),
            status="applied",
            applied_changes=applied_changes,
            rationale=parsed_response.get("rationale", ""),
        )

        self._write_repair_plan(
            path=Path(artifacts["repair_plan"]),
            status="applied",
            reason="Applied LLM-generated multi-file repair candidate.",
            task=task,
            include_browser_feedback=include_browser_feedback,
            changed_paths=changed_paths,
        )

        return RepairResult(
            status="applied",
            reason="Applied LLM-generated multi-file repair candidate.",
            target_file=", ".join(changed_paths),
            artifacts=artifacts,
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are a careful frontend repair agent. "
            "You repair small React/Vite applications. "
            "You may edit multiple files when needed. "
            "Return only valid JSON. Do not include Markdown fences or explanations outside JSON."
        )

    def _build_user_prompt(
        self,
        *,
        task: Task,
        project_context: str,
        browser_result: BrowserRunResult | None,
        include_browser_feedback: bool,
        llm_plan: str | None,
        llm_diagnosis: str | None,
        test_proposal: dict[str, Any] | None,
    ) -> str:
        sections = [
            "# Task",
            task.instruction,
            "",
            "# Editable project files",
            project_context,
        ]

        if llm_plan:
            sections.extend(
                [
                    "",
                    "# Repair plan",
                    llm_plan,
                ]
            )

        if test_proposal:
            sections.extend(
                [
                    "",
                    "# Proposed interaction checks",
                    self._format_test_proposal(test_proposal),
                ]
            )

        if llm_diagnosis:
            sections.extend(
                [
                    "",
                    "# Browser-grounded diagnosis",
                    llm_diagnosis,
                ]
            )

        if include_browser_feedback:
            sections.extend(
                [
                    "",
                    "# Browser feedback",
                    self._format_browser_feedback(browser_result),
                ]
            )

        sections.extend(
            [
                "",
                "# Required JSON output",
                "Return a JSON object with this exact shape:",
                "",
                "{",
                '  "changes": [',
                "    {",
                '      "path": "relative/path/to/file",',
                '      "content": "full new file content"',
                "    }",
                "  ],",
                '  "rationale": "brief explanation of the repair"',
                "}",
                "",
                "Rules:",
                "- Return full file contents for every changed file, not patches.",
                "- Use only relative paths.",
                "- Do not edit files outside the provided project.",
                "- Prefer the smallest set of file changes that fixes the task.",
                "- Do not modify package.json unless dependencies or scripts are actually relevant.",
            ]
        )

        return "\n".join(sections)

    def _format_test_proposal(self, test_proposal: dict[str, Any]) -> str:
        payload = test_proposal.get("payload", {})
        validation = test_proposal.get("validation", {})

        formatted = {
            "status": test_proposal.get("status"),
            "rationale": payload.get("rationale"),
            "proposed_interaction_checks": payload.get(
                "proposed_interaction_checks",
                [],
            ),
            "valid_interaction_checks": validation.get(
                "valid_interaction_checks",
                [],
            ),
            "invalid_check_count": validation.get("invalid_check_count"),
        }

        return json.dumps(
            formatted,
            indent=2,
            ensure_ascii=False,
        )[:MAX_TEXT_ARTIFACT_CHARS]

    def _format_browser_feedback(
        self,
        browser_result: BrowserRunResult | None,
    ) -> str:
        if browser_result is None:
            return "No browser feedback is available."

        feedback: dict[str, Any] = {
            "browser_status": browser_result.status,
            "test_status": browser_result.test_status,
            "passed_test_count": browser_result.passed_test_count,
            "failed_test_count": browser_result.failed_test_count,
        }

        artifact_keys = [
            "test_results",
            "console_logs",
            "page_errors",
        ]

        for artifact_key in artifact_keys:
            artifact_path = browser_result.artifacts.get(artifact_key)
            if artifact_path is None:
                continue

            feedback[artifact_key] = self._read_text_artifact(
                Path(artifact_path),
                limit=MAX_TEXT_ARTIFACT_CHARS,
            )

        dom_snapshot_path = browser_result.artifacts.get("dom_snapshot")
        if dom_snapshot_path is not None:
            feedback["dom_snapshot_excerpt"] = self._read_text_artifact(
                Path(dom_snapshot_path),
                limit=MAX_DOM_SNAPSHOT_CHARS,
            )

        return json.dumps(feedback, indent=2, ensure_ascii=False)

    def _read_text_artifact(self, path: Path, limit: int) -> str:
        if not path.exists():
            return f"Artifact does not exist: {path}"

        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > limit:
            return text[:limit] + "\n\n... truncated ..."

        return text

    def _write_repair_plan(
        self,
        *,
        path: Path,
        status: str,
        reason: str,
        task: Task,
        include_browser_feedback: bool,
        changed_paths: list[str],
    ) -> None:
        payload = {
            "status": status,
            "reason": reason,
            "task_id": task.id,
            "task_type": task.task_type,
            "repair_mode": "multi_file_llm_project_edit",
            "include_browser_feedback": include_browser_feedback,
            "changed_paths": changed_paths,
        }

        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _format_full_prompt(self, system_prompt: str, user_prompt: str) -> str:
        return "\n".join(
            [
                "# System prompt",
                system_prompt,
                "",
                "# User prompt",
                user_prompt,
                "",
            ]
        )
