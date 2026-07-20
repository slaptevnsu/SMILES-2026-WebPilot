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
        generation_dir = run_dir / "llm_generation"
        generation_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {
            "llm_prompt": str(generation_dir / "llm_prompt.txt"),
            "llm_response": str(generation_dir / "llm_response.txt"),
            "generation_plan": str(generation_dir / "generation_plan.json"),
            "patch": str(generation_dir / "patch.diff"),
            "changed_files": str(generation_dir / "changed_files.json"),
        }

        if task.task_type != "text_generation":
            self._write_generation_plan(
                path=Path(artifacts["generation_plan"]),
                status="skipped",
                reason="LLMGenerator currently supports only text_generation tasks.",
                task=task,
                changed_paths=[],
            )
            return RepairResult(
                status="skipped",
                reason="LLMGenerator currently supports only text_generation tasks.",
                target_file=None,
                artifacts=artifacts,
            )

        collector = ProjectContextCollector()
        project_files = collector.collect(repo_path=repo_path)

        if not project_files:
            self._write_generation_plan(
                path=Path(artifacts["generation_plan"]),
                status="failed",
                reason="No editable frontend project files were found.",
                task=task,
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
                path=Path(artifacts["generation_plan"]),
                status="failed",
                reason=f"LLM call failed: {exc}",
                task=task,
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
            self._write_generation_plan(
                path=Path(artifacts["generation_plan"]),
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
                target_file=None,
                artifacts=artifacts,
            )

        if not applied_changes:
            write_project_patch(
                path=Path(artifacts["patch"]),
                applied_changes=[],
            )
            self._write_generation_plan(
                path=Path(artifacts["generation_plan"]),
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

        self._write_generation_plan(
            path=Path(artifacts["generation_plan"]),
            status="applied",
            reason="Applied LLM-generated frontend implementation.",
            task=task,
            changed_paths=changed_paths,
        )

        return RepairResult(
            status="applied",
            reason="Applied LLM-generated frontend implementation.",
            target_file=", ".join(changed_paths),
            artifacts=artifacts,
        )

    def _build_system_prompt(self) -> str:
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
        sections = [
            "# Task",
            task.instruction,
            "",
            "# Oracle interaction checks",
            self._format_interaction_checks(task),
            "",
            "# Editable starter project files",
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
            "- Prefer the smallest set of file changes that implements the task.",
            "- Preserve the Vite/React entrypoint unless changing it is necessary.",
            "- Include the requested data-testid attributes exactly when the task specifies them.",
            "- Satisfy the oracle interaction checks exactly.",
            "- For click_increments_text_int checks, the target element's textContent must be only an integer, for example 0, 1, or 2. Do not include labels such as 'Count: 0' inside that target element.",
            "- Do not modify package.json unless dependencies or scripts are actually relevant.",
        ]

        return "\n".join(sections)

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
            "generation_mode": "multi_file_llm_project_edit",
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
