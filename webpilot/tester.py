from __future__ import annotations

from playwright.sync_api import Page

from webpilot.schemas import InteractionTestResult, Task, TestCheckResult


class InteractionTester:
    def run(self, page: Page, task: Task) -> InteractionTestResult:
        if task.task_type == "diagnostic_repair" and self._looks_like_counter_task(task):
            return self._test_counter_increment(page)
        
        check = TestCheckResult(
            name="interaction_test_selection",
            status="skipped",
            details={
                "reason": "No tasl-specific interaction test is implemented for this task yet.",
                "task_id": task.id,
                "task_type": task.task_type,
            },
        )
        return self._build_result([check])


    def _looks_like_counter_task(self, task: Task) -> bool:
        text = f"{task.id} {task.instruction}".lower()
        return "counter" in text and "button" in text

    def _test_counter_increment(self, page: Page) -> InteractionTestResult:
        check_name = "counter increments after button click"

        try:
            count_locator = page.locator('[data-testid="count-value"]')
            button_locator = page.locator('[data-testid="increment-button"]')

            before_text = count_locator.inner_text(timeout=5_000).strip()
            before_value = self._parse_int(before_text)

            button_locator.click(timeout=5_000)
            page.wait_for_timeout(300)

            after_text = count_locator.inner_text(timeout=5_000).strip()
            after_value = self._parse_int(after_text)

            expected_value = before_value + 1
            passed = after_value == expected_value

            check = TestCheckResult(
                name=check_name,
                status="passed" if passed else "failed",
                details={
                    "before_text": before_text,
                    "after_text": after_text,
                    "before_value": before_value,
                    "after_value": after_value,
                    "expected_value": expected_value,
                    "reason": (
                        "Counter increased correctly."
                        if passed
                        else "Counter value did not increase after clicking the button."
                    ),
                },
            )
        except Exception as exc:
            check = TestCheckResult(
                name=check_name,
                status="failed",
                details={
                    "reason": "Interaction test raised an exception.",
                    "exception_type": exc.__class__.__name__,
                    "exception_message": str(exc),
                },
            )

        return self._build_result([check])

    def _build_result(self, checks: list[TestCheckResult]) -> InteractionTestResult:
        passed_count = sum(check.status == "passed" for check in checks)
        failed_count = sum(check.status == "failed" for check in checks)
        skipped_count = sum(check.status == "skipped" for check in checks)

        if failed_count > 0:
            status = "failed"
        elif passed_count > 0:
            status = "passed"
        else:
            status = "skipped"

        return InteractionTestResult(
            status=status,
            checks=checks,
            passed_count=passed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
        )

    def _parse_int(self, value: str) -> int:
        return int(value.strip())