from __future__ import annotations

from pathlib import Path

from webpilot.llm_client import LLMClient
from webpilot.schemas import Task


class LLMPlanner:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        *,
        task: Task,
        repo_path: Path,
        run_dir: Path,
    ) -> str:
        plan_dir = run_dir / "llm_plan"
        plan_dir.mkdir(parents=True, exist_ok=True)

        target_file = repo_path / "src" / "App.jsx"
        source_code = (
            target_file.read_text(encoding="utf-8")
            if target_file.exists()
            else "src/App.jsx was not found."
        )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            task=task,
            source_code=source_code,
            target_file=target_file,
        )

        (plan_dir / "llm_plan_prompt.txt").write_text(
            self._format_full_prompt(system_prompt, user_prompt),
            encoding="utf-8",
        )

        response = self.client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ).strip()

        (plan_dir / "llm_plan_response.txt").write_text(
            response + "\n",
            encoding="utf-8",
        )

        return response
    
    def _build_system_prompt(self) -> str:
        return (
            "You are a frontend planning agent for a browser-grounded web coding system. "
            "Your job is to produce a concise repair plan before code editing. "
            "Do not write code. "
            "Do not include Markdown tables. "
            "Return a short numbered list of concrete repair steps."
        )
    
    def _build_user_prompt(
        self,
        *,
        task: Task,
        source_code: str,
        target_file: Path,
    ) -> str:
        return "\n".join(
            [
                "# Task",
                task.instruction,
                "",
                "# Target file",
                str(target_file),
                "",
                "# Current src/App.jsx",
                "```jsx",
                source_code,
                "```",
                "",
                "# Required output",
                "Return a concise numbered repair plan. Do not return code.",
            ]
        )
    
    def _format_full_prompt(self, system_prompt: str, user_prompt: str) -> str:
        return "\n\n".join(
            [
                "## System prompt",
                system_prompt,
                "## User prompt",
                user_prompt,
            ]
        )