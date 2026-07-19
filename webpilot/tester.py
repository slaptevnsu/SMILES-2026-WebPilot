from __future__ import annotations

from playwright.sync_api import Page

from webpilot.schemas import InteractionCheck, InteractionTestResult, Task, TestCheckResult


class InteractionTester:
    def run(self, page: Page, task: Task) -> InteractionTestResult:
        if not task.interaction_checks:
            check = TestCheckResult(
                name="interaction_test_selection",
                status="skipped",
                details={
                    "reason": "No interaction checks are defined for this task.",
                    "task_id": task.id,
                    "task_type": task.task_type,
                },
            )
            return self._build_result([check])

        checks = [
            self._run_interaction_check(page=page, check=check)
            for check in task.interaction_checks
        ]

        return self._build_result(checks)

    def _run_interaction_check(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        if check.kind == "click_increments_text_int":
            return self._test_click_increments_text_int(page=page, check=check)

        if check.kind == "fill_updates_text":
            return self._test_fill_updates_text(page=page, check=check)

        return TestCheckResult(
            name=check.name,
            status="skipped",
            details={
                "reason": f"Unsupported interaction check kind: {check.kind}",
                "kind": check.kind,
            },
        )

    def _test_click_increments_text_int(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        try:
            if check.action_selector is None:
                raise ValueError("action_selector is required for click_increments_text_int")

            target_locator = page.locator(check.target_selector)
            action_locator = page.locator(check.action_selector)

            before_text = target_locator.inner_text(timeout=check.timeout_ms).strip()
            before_value = self._parse_int(before_text)

            action_locator.click(timeout=check.timeout_ms)
            page.wait_for_timeout(check.settle_ms)

            after_text = target_locator.inner_text(timeout=check.timeout_ms).strip()
            after_value = self._parse_int(after_text)

            expected_value = before_value + 1
            passed = after_value == expected_value

            return TestCheckResult(
                name=check.name,
                status="passed" if passed else "failed",
                details={
                    "kind": check.kind,
                    "target_selector": check.target_selector,
                    "action_selector": check.action_selector,
                    "before_text": before_text,
                    "after_text": after_text,
                    "before_value": before_value,
                    "after_value": after_value,
                    "expected_value": expected_value,
                    "reason": (
                        "Text value incremented correctly after the click."
                        if passed
                        else "Text value did not increment after the click."
                    ),
                },
            )

        except Exception as exc:
            return self._build_exception_check(check=check, exc=exc)

    def _test_fill_updates_text(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        try:
            if check.input_selector is None:
                raise ValueError("input_selector is required for fill_updates_text")
            if check.value is None:
                raise ValueError("value is required for fill_updates_text")

            input_locator = page.locator(check.input_selector)
            target_locator = page.locator(check.target_selector)

            before_text = target_locator.inner_text(timeout=check.timeout_ms).strip()

            input_locator.fill(check.value, timeout=check.timeout_ms)
            page.wait_for_timeout(check.settle_ms)

            after_text = target_locator.inner_text(timeout=check.timeout_ms).strip()
            passed = check.value in after_text

            return TestCheckResult(
                name=check.name,
                status="passed" if passed else "failed",
                details={
                    "kind": check.kind,
                    "input_selector": check.input_selector,
                    "target_selector": check.target_selector,
                    "input_value": check.value,
                    "before_text": before_text,
                    "after_text": after_text,
                    "expected_text": check.value,
                    "reason": (
                        "Target text updated correctly after filling the input."
                        if passed
                        else "Target text did not update after filling the input."
                    ),
                },
            )

        except Exception as exc:
            return self._build_exception_check(check=check, exc=exc)

    def _build_exception_check(
        self,
        *,
        check: InteractionCheck,
        exc: Exception,
    ) -> TestCheckResult:
        return TestCheckResult(
            name=check.name,
            status="failed",
            details={
                "kind": check.kind,
                "reason": "Interaction check raised an exception.",
                "exception_type": exc.__class__.__name__,
                "exception_message": str(exc),
            },
        )

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