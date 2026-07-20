from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from webpilot.project_context import validate_edit_path


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str


@dataclass(frozen=True)
class AppliedFileChange:
    path: str
    operation: str
    before: str
    after: str


def parse_llm_json_response(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()

    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1).strip()

    parsed = json.loads(text)

    if not isinstance(parsed, dict):
        raise ValueError("LLM response must be a JSON object.")

    return parsed


def extract_file_changes(parsed_response: dict[str, Any]) -> list[FileChange]:
    raw_changes = parsed_response.get("changes")

    if not isinstance(raw_changes, list):
        raise ValueError("LLM response must contain a list field named 'changes'.")

    changes = []

    for index, raw_change in enumerate(raw_changes):
        if not isinstance(raw_change, dict):
            raise ValueError(f"Change at index {index} must be an object.")

        path = raw_change.get("path")
        content = raw_change.get("content")

        if not isinstance(path, str):
            raise ValueError(f"Change at index {index} has non-string path.")

        if not isinstance(content, str):
            raise ValueError(f"Change at index {index} has non-string content.")

        changes.append(
            FileChange(
                path=Path(path).as_posix(),
                content=content.rstrip() + "\n",
            )
        )

    return changes


def apply_file_changes(
    *,
    repo_path: Path,
    before_by_path: dict[str, str],
    changes: list[FileChange],
) -> list[AppliedFileChange]:
    applied_changes = []

    for change in changes:
        target_path = validate_edit_path(
            repo_path=repo_path,
            relative_path=change.path,
        )

        before = before_by_path.get(change.path, "")
        after = change.content

        if before == after:
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(after, encoding="utf-8")

        applied_changes.append(
            AppliedFileChange(
                path=change.path,
                operation="modified" if change.path in before_by_path else "created",
                before=before,
                after=after,
            )
        )

    return applied_changes


def write_project_patch(
    *,
    path: Path,
    applied_changes: list[AppliedFileChange],
) -> None:
    chunks = []

    for change in applied_changes:
        before = change.before.splitlines(keepends=True)
        after = change.after.splitlines(keepends=True)

        chunks.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{change.path}",
                tofile=f"b/{change.path}",
            )
        )

        if chunks and chunks[-1] != "\n":
            chunks.append("\n")

    path.write_text("".join(chunks), encoding="utf-8")


def write_changed_files_artifact(
    *,
    path: Path,
    status: str,
    applied_changes: list[AppliedFileChange],
    rationale: str = "",
    error: Exception | None = None,
) -> None:
    payload: dict[str, Any] = {
        "status": status,
        "changed_files": [
            {
                "path": change.path,
                "operation": change.operation,
                "before_chars": len(change.before),
                "after_chars": len(change.after),
            }
            for change in applied_changes
        ],
        "rationale": rationale,
    }

    if error is not None:
        payload["error"] = {
            "exception_type": error.__class__.__name__,
            "exception_message": str(error),
        }

    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
