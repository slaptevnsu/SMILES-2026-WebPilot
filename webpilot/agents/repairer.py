from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path
from typing import Any

from webpilot.llm_client import LLMClient
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

        target_file = repo_path / "src" / "App.jsx"

        artifacts = {
            "llm_prompt": str(repair_dir / "llm_prompt.txt"),
            "llm_response": str(repair_dir / "llm_response.txt"),
            "repair_plan": str(repair_dir / "repair_plan.json"),
            "patch": str(repair_dir / "patch.diff"),
        }

        if task.task_type != "diagnostic_repair":
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="skipped",
                reason="LLMRepairer currently supports only diagnostic_repair tasks.",
                task=task,
                target_file=target_file,
                include_browser_feedback=include_browser_feedback,
            )
            return RepairResult(
                status="skipped",
                reason="LLMRepairer currently supports only diagnostic_repair tasks.",
                target_file=str(target_file),
                artifacts=artifacts,
            )
        
        if not target_file.exists():
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="failed",
                reason="Target file src/App.jsx does not exist.",
                task=task,
                target_file=target_file,
                include_browser_feedback=include_browser_feedback,
            )
            return RepairResult(
                status="failed",
                reason="Target file src/App.jsx does not exist.",
                target_file=str(target_file),
                artifacts=artifacts,
            )
        
        before_source = target_file.read_text(encoding="utf-8")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            task=task,
            source_code=before_source,
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
                target_file=target_file,
                include_browser_feedback=include_browser_feedback,
            )
            return RepairResult(
                status="failed",
                reason=f"LLM call failed: {exc}",
                target_file=str(target_file),
                artifacts=artifacts,
            )
        
        Path(artifacts["llm_response"]).write_text(raw_response, encoding="utf-8")

        after_source = self._extract_code(raw_response).rstrip() + "\n"

        if not after_source.strip():
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="failed",
                reason="LLM returned an empty candidate source file.",
                task=task,
                target_file=target_file,
                include_browser_feedback=include_browser_feedback,
            )
            return RepairResult(
                status="failed",
                reason="LLM returned an empty candidate source file.",
                target_file=str(target_file),
                artifacts=artifacts,
            )
        
        if after_source.strip() == before_source.strip():
            self._write_patch(
                path=Path(artifacts["patch"]),
                before=before_source,
                after=after_source,
                filename=str(target_file),
            )
            self._write_repair_plan(
                path=Path(artifacts["repair_plan"]),
                status="skipped",
                reason="LLM returned source code equivalent to the original file.",
                task=task,
                target_file=target_file,
                include_browser_feedback=include_browser_feedback,
            )
            return RepairResult(
                status="skipped",
                reason="LLM returned source code equivalent to the original file.",
                target_file=str(target_file),
                artifacts=artifacts,
            )
        
        target_file.write_text(after_source, encoding="utf-8")

        self._write_patch(
            path=Path(artifacts["patch"]),
            before=before_source,
            after=after_source,
            filename=str(target_file),
        )

        self._write_repair_plan(
            path=Path(artifacts["repair_plan"]),
            status="applied",
            reason="Applied LLM-generated repair candidate.",
            task=task,
            target_file=target_file,
            include_browser_feedback=include_browser_feedback,
        )

        return RepairResult(
            status="applied",
            reason="Applied LLM-generated repair candidate.",
            target_file=str(target_file),
            artifacts=artifacts,
        )

    def _build_system_prompt(self) -> str:
        return (
            "You are a careful frontend repair agent. "
            "You repair small React applications. "
            "Return only the full corrected contents of src/App.jsx. "
            "Do not include Markdown fences, explanations, comments about your changes, "
            "or any text outside the file contents."
        )

    def _build_user_prompt(
        self,
        *,
        task: Task,
        source_code: str,
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
            "# Current src/App.jsx",
            "```jsx",
            source_code,
            "```",
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
                "# Required output",
                "Return the full corrected src/App.jsx file only.",
            ]
        )

        return "\n".join(sections)

    def _format_test_proposal(self, test_proposal: dict[str, Any]) -> str:
        payload = test_proposal.get("payload", {})
        validation = test_proposal.get("validation", {})

        formatted = {
            "status": test_proposal.get("status"),
            "rationale": payload.get("rationale"),
            "proposed_interaction_checks": payload.get("proposed_interaction_checks", []),
            "valid_interaction_checks": validation.get("valid_interaction_checks", []),
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

        artifacts = browser_result.artifacts

        feedback["test_results"] = self._read_json_artifact(
            artifacts.get("test_results")
        )
        feedback["console_logs"] = self._read_json_artifact(
            artifacts.get("console_logs")
        )
        feedback["page_errors"] = self._read_json_artifact(
            artifacts.get("page_errors")
        )
        feedback["dom_snapshot_excerpt"] = self._read_text_artifact(
            artifacts.get("dom_snapshot"),
            max_chars=MAX_DOM_SNAPSHOT_CHARS,
        )

        return json.dumps(feedback, indent=2, ensure_ascii=False)


    def _read_json_artifact(self, path_str: str | None) -> Any:
        if not path_str:
            return None

        path = Path(path_str)
        if not path.exists():
            return None

        text = path.read_text(encoding="utf-8")

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text[:MAX_TEXT_ARTIFACT_CHARS]

    def _read_text_artifact(self, path_str: str | None, max_chars: int) -> str | None:
        if not path_str:
            return None

        path = Path(path_str)
        if not path.exists():
            return None

        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]

    def _extract_code(self, response: str) -> str:
        fenced_match = re.search(
            r"```(?:jsx|javascript|js|tsx|typescript)?\s*(.*?)```",
            response,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if fenced_match:
            return fenced_match.group(1).strip()

        return response.strip()

    def _write_patch(
        self,
        *,
        path: Path,
        before: str,
        after: str,
        filename: str,
    ) -> None:
        patch = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{filename}:before",
            tofile=f"{filename}:after",
        )
        path.write_text("".join(patch), encoding="utf-8")

    def _write_repair_plan(
        self,
        *,
        path: Path,
        status: str,
        reason: str,
        task: Task,
        target_file: Path,
        include_browser_feedback: bool,
    ) -> None:
        plan = {
            "status": status,
            "reason": reason,
            "task_id": task.id,
            "task_type": task.task_type,
            "target_file": str(target_file),
            "include_browser_feedback": include_browser_feedback,
            "model": os.environ.get("WEBPILOT_LLM_MODEL"),
        }
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def _format_full_prompt(self, system_prompt: str, user_prompt: str) -> str:
        return "\n\n".join(
            [
                "## System prompt",
                system_prompt,
                "## User prompt",
                user_prompt,
            ]
        )