from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from webpilot.llm_client import LLMClient
from webpilot.project_context import ProjectContextCollector
from webpilot.schemas import InteractionCheck, Task


class LLMTestPlanner:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def run(
        self,
        *,
        task: Task,
        repo_path: Path,
        run_dir: Path,
        llm_diagnosis: str | None = None,
    ) -> dict[str, Any]:
        proposal_dir = run_dir / "llm_test_proposal"
        proposal_dir.mkdir(parents=True, exist_ok=True)

        prompt_path = proposal_dir / "llm_test_proposal_prompt.txt"
        response_path = proposal_dir / "llm_test_proposal_response.txt"
        parsed_path = proposal_dir / "proposed_interaction_checks.json"

        collector = ProjectContextCollector()
        project_files = collector.collect(repo_path=repo_path)
        project_context = (
            collector.format_for_prompt(project_files)
            if project_files
            else "No editable frontend project files were found."
        )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            task=task,
            project_context=project_context,
            llm_diagnosis=llm_diagnosis,
        )

        prompt_path.write_text(
            self._format_full_prompt(system_prompt, user_prompt),
            encoding="utf-8",
        )

        try:
            raw_response = self.client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ).strip()

            response_path.write_text(raw_response + "\n", encoding="utf-8")

            parsed_payload = self._parse_json_response(raw_response)
            normalized_payload = self._normalize_payload(parsed_payload)
            validation_result = self._validate_payload(normalized_payload)

            result = {
                "status": "parsed",
                "artifacts": {
                    "prompt": str(prompt_path),
                    "response": str(response_path),
                    "parsed": str(parsed_path),
                },
                "payload": normalized_payload,
                "validation": validation_result,
            }

        except Exception as exc:
            result = {
                "status": "failed",
                "artifacts": {
                    "prompt": str(prompt_path),
                    "response": str(response_path),
                    "parsed": str(parsed_path),
                },
                "error": {
                    "exception_type": exc.__class__.__name__,
                    "exception_message": str(exc),
                },
            }

        parsed_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        return result

    def _build_system_prompt(self) -> str:
        return (
            "You are a test-planning agent for a browser-grounded web coding system. "
            "Your job is to propose browser interaction checks for a small React application. "
            "Return only valid JSON. Do not include Markdown fences or explanations outside JSON."
        )

    def _build_user_prompt(
        self,
        *,
        task: Task,
        project_context: str,
        llm_diagnosis: str | None,
    ) -> str:
        diagnosis_section = (
            [
                "",
                "# Browser-grounded diagnosis",
                llm_diagnosis,
            ]
            if llm_diagnosis
            else []
        )

        return "\n".join(
            [
                "# Task instruction",
                task.instruction,
                "",
                "# Editable project files",
                project_context,
                *diagnosis_section,
                "",
                "# Supported interaction check kinds",
                "",
                "1. click_increments_text_int",
                "Required fields:",
                "- name",
                "- kind",
                "- target_selector",
                "- action_selector",
                "",
                "Use this when a click should increment an integer displayed in the UI.",
                "",
                "2. fill_updates_text",
                "Required fields:",
                "- name",
                "- kind",
                "- input_selector",
                "- target_selector",
                "- value",
                "",
                "Use this when filling an input should update some visible text.",
                "",
                "3. click_reveals_text",
                "Required fields:",
                "- name",
                "- kind",
                "- action_selector",
                "- target_selector",
                "- target_text",
                "",
                "Use this when clicking an element should reveal visible text, for example opening a menu.",
                "",
                "4. tabs_switch_content",
                "Required fields:",
                "- name",
                "- kind",
                "- action_selector",
                "- target_selector",
                "",
                "Use this when clicking a tab should reveal the corresponding visible tab panel.",
                "",
                "5. selector_exists",
                "Required fields:",
                "- name",
                "- kind",
                "- target_selector",
                "",
                "Use this when a required element, field, button, or section should exist and be visible.",
                "",
                "6. no_mobile_horizontal_overflow",
                "Required fields:",
                "- name",
                "- kind",
                "- target_selector",
                "",
                "Use this when the page should fit a mobile viewport without horizontal scrolling.",
                "",
                "# Required JSON output",
                "",
                "Return a JSON object with this shape:",
                "",
                "{",
                '  "proposed_interaction_checks": [',
                "    {",
                '      "name": "short check name",',
                '      "kind": "click_increments_text_int, fill_updates_text, click_reveals_text, tabs_switch_content, selector_exists, or no_mobile_horizontal_overflow",',
                '      "target_selector": "CSS selector for the value, text, or panel to check",',
                '      "action_selector": "CSS selector for the clicked element, if needed",',
                '      "input_selector": "CSS selector for the input element, if needed",',
                '      "value": "test input value, if needed",',
                '      "target_text": "expected visible text, if needed"',
                "    }",
                "  ],",
                '  "rationale": "brief explanation of why these checks match the task"',
                "}",
                "",
                "Prefer stable selectors such as data-testid when they are present in the project files.",
                "Do not invent unsupported check kinds.",
            ]
        )

    def _parse_json_response(self, raw_response: str) -> Any:
        text = raw_response.strip()

        fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced_match:
            text = fenced_match.group(1).strip()

        return json.loads(text)

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            return {
                "proposed_interaction_checks": payload,
                "rationale": "",
            }

        if isinstance(payload, dict):
            checks = payload.get("proposed_interaction_checks", [])
            if not isinstance(checks, list):
                checks = []

            return {
                "proposed_interaction_checks": checks,
                "rationale": payload.get("rationale", ""),
            }

        return {
            "proposed_interaction_checks": [],
            "rationale": "",
        }

    def _validate_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        valid_checks = []
        validation_errors = []

        checks = payload.get("proposed_interaction_checks", [])

        for index, check_payload in enumerate(checks):
            try:
                check = InteractionCheck.model_validate(check_payload)
                valid_checks.append(check.model_dump(mode="json"))
            except ValidationError as exc:
                validation_errors.append(
                    {
                        "index": index,
                        "error": exc.errors(),
                        "payload": check_payload,
                    }
                )

        return {
            "valid_check_count": len(valid_checks),
            "invalid_check_count": len(validation_errors),
            "valid_interaction_checks": valid_checks,
            "validation_errors": validation_errors,
        }

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
