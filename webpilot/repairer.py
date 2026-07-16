from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from webpilot.schemas import BrowserRunResult, RepairResult, Task


class DeterministicRepairer:
    def run(self, repo_path: Path, run_dir: Path, task: Task, browser_result: BrowserRunResult) -> RepairResult:
        repo_path = repo_path.resolve()
        run_dir = run_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        artifacts = {
            "repair_plan": str(run_dir / "repair_plan.json"),
            "patch": str(run_dir / "patch.diff"),
        }

        target_file = repo_path / "src" / "App.jsx"
        failure_reasons = self._load_failure_reasons(browser_result)

        if task.task_type != "diagnostic_repair":
            result = RepairResult(
                status="skipped",
                reason="Repair is only implemented for diagnostic_repair tasks.",
                target_file=None,
                artifacts=artifacts,
            )
            self._write_result(run_dir, result)
            return result

        if not self._looks_like_counter_failure(task=task, failure_reasons=failure_reasons):
            result = RepairResult(
                status="skipped",
                reason="No deterministic repair rule matched the observed failure.",
                target_file=None,
                artifacts=artifacts,
            )
            self._write_result(run_dir, result)
            return result

        if not target_file.exists():
            result = RepairResult(
                status="failed",
                reason=f"Target file was not found: {target_file}",
                target_file=str(target_file),
                artifacts=artifacts,
            )
            self._write_result(run_dir, result)
            return result

        before = target_file.read_text(encoding="utf-8")
        after = self._repair_counter_increment_handler(before)

        if after == before:
            result = RepairResult(
                status="failed",
                reason="Counter repair rule matched the failure, but no source-code change was produced.",
                target_file=str(target_file),
                artifacts=artifacts,
            )
            self._write_result(run_dir, result)
            return result

        target_file.write_text(after, encoding="utf-8")

        patch = self._build_patch(
            before=before,
            after=after,
            relative_path="src/App.jsx",
        )
        (run_dir / "patch.diff").write_text(patch, encoding="utf-8")

        result = RepairResult(
            status="applied",
            reason="Applied deterministic repair for a counter button that did not update React state.",
            target_file=str(target_file),
            artifacts=artifacts,
        )
        self._write_result(run_dir, result)
        return result

    def _load_failure_reasons(self, browser_result: BrowserRunResult) -> list[str]:
        test_results_path = browser_result.artifacts.get("test_results")
        if test_results_path is None:
            return []

        path = Path(test_results_path)
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

        reasons: list[str] = []
        for check in data.get("checks", []):
            details = check.get("details", {})
            reason = details.get("reason")
            if isinstance(reason, str):
                reasons.append(reason)

        return reasons

    def _looks_like_counter_failure(self, task: Task, failure_reasons: list[str]) -> bool:
        text = " ".join([task.id, task.instruction, *failure_reasons]).lower()

        return (
            "counter" in text
            and (
                "did not increase" in text
                or "increment" in text
                or "button" in text
            )
        )

    def _repair_counter_increment_handler(self, source: str) -> str:
        replacement = (
            "function handleIncrement() {\n"
            "    setCount((currentCount) => currentCount + 1);\n"
            "  }"
        )

        pattern = (
            r"function\s+handleIncrement\s*\(\)\s*\{\s*"
            r"(?://[^\n]*\n\s*)?"
            r"count\s*\+\s*1\s*;\s*"
            r"\}"
        )

        repaired, replacements = re.subn(pattern, replacement, source, count=1)

        if replacements > 0:
            return repaired

        return source.replace(
            "count + 1;",
            "setCount((currentCount) => currentCount + 1);",
            1,
        )

    def _build_patch(self, before: str, after: str, relative_path: str) -> str:
        return "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )

    def _write_result(self, run_dir: Path, result: RepairResult) -> None:
        data: dict[str, Any] = result.model_dump(mode="json")

        with (run_dir / "repair_plan.json").open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")