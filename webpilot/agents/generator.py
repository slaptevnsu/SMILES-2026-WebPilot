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
from webpilot.schemas import RepairResult, Task


SUPPORTED_PROJECT_EDIT_TASK_TYPES = {"text_generation", "editing"}


class LLMGenerator:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        *,
        task: Task,
        repo_path: Path,
        run_dir: Path,
    ) -> RepairResult:
        artifact_dir_name = (
            "llm_edit" if task.task_type == "editing" else "llm_generation"
        )
        plan_artifact_key = (
            "edit_plan" if task.task_type == "editing" else "generation_plan"
        )
        plan_artifact_name = f"{plan_artifact_key}.json"

        project_edit_dir = run_dir / artifact_dir_name
        project_edit_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {
            "llm_prompt": str(project_edit_dir / "llm_prompt.txt"),
            "llm_response": str(project_edit_dir / "llm_response.txt"),
            plan_artifact_key: str(project_edit_dir / plan_artifact_name),
            "patch": str(project_edit_dir / "patch.diff"),
            "changed_files": str(project_edit_dir / "changed_files.json"),
        }

        if task.task_type not in SUPPORTED_PROJECT_EDIT_TASK_TYPES:
            self._write_generation_plan(
                path=Path(artifacts[plan_artifact_key]),
                status="skipped",
                reason="LLMGenerator supports only text_generation and editing tasks.",
                task=task,
                changed_paths=[],
            )
            return RepairResult(
                status="skipped",
                reason="LLMGenerator supports only text_generation and editing tasks.",
                artifacts=artifacts,
            )

        collector = ProjectContextCollector()
        project_files = collector.collect(repo_path=repo_path)

        if not project_files:
            self._write_generation_plan(
                path=Path(artifacts[plan_artifact_key]),
                status="failed",
                reason="No editable frontend project files were found.",
                task=task,
                changed_paths=[],
            )
            return RepairResult(
                status="failed",
                reason="No editable frontend project files were found.",
                artifacts=artifacts,
            )

        before_by_path = {file.path: file.content for file in project_files}
        project_context = collector.format_for_prompt(project_files)

        system_prompt = self._build_system_prompt(task=task)
        user_prompt = self._build_user_prompt(
            task=task,
            project_context=project_context,
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
            self._write_generation_plan(
                path=Path(artifacts[plan_artifact_key]),
                status="failed",
                reason=f"LLM call failed: {exc}",
                task=task,
                changed_paths=[],
            )
            return RepairResult(
                status="failed",
                reason=f"LLM call failed: {exc}",
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
            self._write_generation_plan(
                path=Path(artifacts[plan_artifact_key]),
                status="failed",
                reason=f"Failed to parse or apply LLM file changes: {exc}",
                task=task,
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
                artifacts=artifacts,
            )

        if not applied_changes:
            write_project_patch(
                path=Path(artifacts["patch"]),
                applied_changes=[],
            )
            self._write_generation_plan(
                path=Path(artifacts[plan_artifact_key]),
                status="skipped",
                reason="LLM returned no effective file changes.",
                task=task,
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

        applied_reason = self._applied_reason(task)

        self._write_generation_plan(
            path=Path(artifacts[plan_artifact_key]),
            status="applied",
            reason=applied_reason,
            task=task,
            changed_paths=changed_paths,
        )

        return RepairResult(
            status="applied",
            reason=applied_reason,
            changed_files=changed_paths,
            artifacts=artifacts,
        )

    def _build_system_prompt(self, *, task: Task) -> str:
        if task.task_type == "editing":
            return (
                "You are a careful frontend editing agent. "
                "You modify existing React/Vite applications according to precise edit instructions. "
                "Preserve unrelated content and behavior. "
                "You may edit multiple files when needed. "
                "Return only valid JSON. Do not include Markdown fences or explanations outside JSON."
            )

        return (
            "You are a careful frontend generation agent. "
            "You implement small React/Vite applications from text instructions. "
            "You may edit multiple files when needed. "
            "Return only valid JSON. Do not include Markdown fences or explanations outside JSON."
        )

    def _build_user_prompt(
        self,
        *,
        task: Task,
        project_context: str,
    ) -> str:
        if task.task_type == "editing":
            task_heading = "# Editing task"
            project_heading = "# Existing editable project files"
            task_specific_rules = [
                "- Modify the existing application according to the requested edit.",
                "- Preserve existing visible content, layout, and behavior unless the task explicitly asks to change them.",
                "- Do not replace the application with an unrelated implementation.",
                "- Prefer local, minimal edits over rewriting the whole project.",
            ]
        else:
            task_heading = "# Task"
            project_heading = "# Editable starter project files"
            task_specific_rules = [
                "- Implement the requested application from the starter project.",
                "- Preserve the Vite/React entrypoint unless changing it is necessary.",
            ]

        sections = [
            task_heading,
            task.instruction,
            "",
            "# Oracle interaction checks",
            self._format_interaction_checks(task),
            "",
            project_heading,
            project_context,
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
            '  "rationale": "brief explanation of the implementation"',
            "}",
            "",
            "Rules:",
            "- Return full file contents for every changed file, not patches.",
            "- Use only relative paths.",
            "- Do not edit files outside the provided project.",
            "- Prefer the smallest set of file changes that satisfies the task.",
            *task_specific_rules,
            "- Include the requested data-testid attributes exactly when the task specifies them.",
            "- Satisfy the oracle interaction checks exactly.",
            "- For click_increments_text_int checks, the target element's textContent must be only an integer, for example 0, 1, or 2. Do not include labels such as 'Count: 0' inside that target element.",
            "- Do not modify package.json unless dependencies or scripts are actually relevant.",
        ]

        return "\n".join(sections)

    def _applied_reason(self, task: Task) -> str:
        if task.task_type == "editing":
            return "Applied LLM-generated frontend edit."

        return "Applied LLM-generated frontend implementation."

    def _format_interaction_checks(self, task: Task) -> str:
        if not task.interaction_checks:
            return "No oracle interaction checks are defined for this task."

        payload = [
            check.model_dump(mode="json")
            for check in task.interaction_checks
        ]

        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _write_generation_plan(
        self,
        *,
        path: Path,
        status: str,
        reason: str,
        task: Task,
        changed_paths: list[str],
    ) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "reason": reason,
            "task_id": task.id,
            "task_type": task.task_type,
            "project_edit_mode": "multi_file_llm_project_edit",
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
