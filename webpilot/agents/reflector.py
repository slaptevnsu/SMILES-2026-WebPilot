from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webpilot.llm_client import LLMClient
from webpilot.schemas import BrowserRunResult, Task


MAX_TEXT_ARTIFACT_CHARS = 4000
MAX_DOM_SNAPSHOT_CHARS = 6000


class LLMReflector:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        *,
        task: Task,
        browser_result: BrowserRunResult,
        run_dir: Path,
        repo_path: Path | None = None,
    ) -> str:
        reflection_dir = run_dir / "llm_reflection"
        reflection_dir.mkdir(parents=True, exist_ok=True)

        source_code = None
        if repo_path is not None:
            target_file = repo_path / "src" / "App.jsx"
            if target_file.exists():
                source_code = target_file.read_text(encoding="utf-8")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            task=task,
            browser_result=browser_result,
            source_code=source_code,
        )

        (reflection_dir / "llm_reflection_prompt.txt").write_text(
            self._format_full_prompt(system_prompt, user_prompt),
            encoding="utf-8",
        )

        response = self.client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ).strip()

        (reflection_dir / "llm_reflection_response.txt").write_text(
            response + "\n",
            encoding="utf-8",
        )

        return response
    
    def _build_system_prompt(self) -> str:
        return (
            "You are a browser-feedback reflection agent for a web coding system. "
            "Your job is to diagnose why the current frontend behavior does not satisfy the task. "
            "Use browser status, interaction test results, console logs, page errors, and DOM evidence. "
            "Do not write code. "
            "Return a concise diagnosis with the likely root cause and the evidence supporting it."
        )
    
    def _build_user_prompt(
            self,
            *,
            task: Task,
            browser_result: BrowserRunResult,
            source_code: str | None,
        ) -> str:
        sections = [
            "# Task",
            task.instruction,
        ]

        if source_code is not None:
            sections.extend(
                [
                    "",
                    "# Current src/App.jsx",
                    "```jsx",
                    source_code,
                    "```",
                ]
            )

        sections.extend(
            [
                "",
                "# Browser evidence",
                self._format_browser_feedback(browser_result),
                "",
                "# Required output",
                "Return a concise root-cause diagnosis. Do not return code.",
            ]
        )

        return "\n".join(sections)
    
    def _format_browser_feedback(self, browser_result: BrowserRunResult) -> str:
        artifacts = browser_result.artifacts

        feedback: dict[str, Any] = {
            "browser_status": browser_result.status,
            "test_status": browser_result.test_status,
            "passed_test_count": browser_result.passed_test_count,
            "failed_test_count": browser_result.failed_test_count,
            "test_results": self._read_json_artifact(artifacts.get("test_results")),
            "console_logs": self._read_json_artifact(artifacts.get("console_logs")),
            "page_errors": self._read_json_artifact(artifacts.get("page_errors")),
            "dom_snapshot_excerpt": self._read_text_artifact(
                artifacts.get("dom_snapshot"),
                max_chars=MAX_DOM_SNAPSHOT_CHARS,
            ),
        }

        return json.dumps(feedback, indent=2, ensure_ascii=False)
    
    def _read_json_artifact(self, path_str: str | None) -> Any:
        if not path_str:
            return None

        path = Path(path_str)
        if not path.exists():
            return None

        text = path.read_text(encoding="utf-8", errors="replace")

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

    def _format_full_prompt(self, system_prompt: str, user_prompt: str) -> str:
        return "\n\n".join(
            [
                "## System prompt",
                system_prompt,
                "## User prompt",
                user_prompt,
            ]
        )