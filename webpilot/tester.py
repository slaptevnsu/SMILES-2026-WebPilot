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

        if check.kind in {"click_reveals_text", "tabs_switch_content"}:
            return self._test_click_reveals_visible_target(page=page, check=check)

        if check.kind == "selector_exists":
            return self._test_selector_exists(page=page, check=check)

        if check.kind == "no_mobile_horizontal_overflow":
            return self._test_no_mobile_horizontal_overflow(page=page, check=check)

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

    def _test_click_reveals_visible_target(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        try:
            if check.action_selector is None:
                raise ValueError(f"action_selector is required for {check.kind}")

            action_locator = page.locator(check.action_selector)
            target_locator = page.locator(check.target_selector)

            before_visible = target_locator.is_visible(timeout=check.timeout_ms)
            before_text = (
                target_locator.inner_text(timeout=check.timeout_ms).strip()
                if before_visible
                else ""
            )

            action_locator.click(timeout=check.timeout_ms)
            page.wait_for_timeout(check.settle_ms)

            after_visible = target_locator.is_visible(timeout=check.timeout_ms)
            after_text = (
                target_locator.inner_text(timeout=check.timeout_ms).strip()
                if after_visible
                else ""
            )

            target_text_found = (
                True if check.target_text is None else check.target_text in after_text
            )
            passed = after_visible and target_text_found

            if passed:
                reason = "Target became visible after the click."
            elif not after_visible:
                reason = "Target did not become visible after the click."
            else:
                reason = "Target became visible, but expected text was not found."

            return TestCheckResult(
                name=check.name,
                status="passed" if passed else "failed",
                details={
                    "kind": check.kind,
                    "action_selector": check.action_selector,
                    "target_selector": check.target_selector,
                    "target_text": check.target_text,
                    "before_visible": before_visible,
                    "after_visible": after_visible,
                    "before_text": before_text,
                    "after_text": after_text,
                    "reason": reason,
                },
            )

        except Exception as exc:
            return self._build_exception_check(check=check, exc=exc)

    def _test_selector_exists(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        try:
            locator = page.locator(check.target_selector)
            count = locator.count()
            visible = count > 0 and locator.first.is_visible(timeout=check.timeout_ms)
            passed = count > 0 and visible

            return TestCheckResult(
                name=check.name,
                status="passed" if passed else "failed",
                details={
                    "kind": check.kind,
                    "target_selector": check.target_selector,
                    "count": count,
                    "visible": visible,
                    "reason": (
                        "Selector exists and is visible."
                        if passed
                        else "Selector does not exist or is not visible."
                    ),
                },
            )

        except Exception as exc:
            return self._build_exception_check(check=check, exc=exc)

    def _test_no_mobile_horizontal_overflow(
        self,
        *,
        page: Page,
        check: InteractionCheck,
    ) -> TestCheckResult:
        original_viewport = page.viewport_size

        try:
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(check.settle_ms)

            metrics = page.evaluate(
                """() => {
                    const doc = document.documentElement;
                    const body = document.body;

                    const clientWidth = doc.clientWidth;
                    const scrollWidth = Math.max(
                        doc.scrollWidth,
                        body ? body.scrollWidth : 0
                    );

                    return {
                        innerWidth: window.innerWidth,
                        clientWidth,
                        scrollWidth,
                        overflowPx: scrollWidth - clientWidth
                    };
                }"""
            )

            overflow_px = int(metrics["overflowPx"])
            passed = overflow_px <= 1

            return TestCheckResult(
                name=check.name,
                status="passed" if passed else "failed",
                details={
                    "kind": check.kind,
                    "target_selector": check.target_selector,
                    "viewport": {"width": 390, "height": 844},
                    "inner_width": metrics["innerWidth"],
                    "client_width": metrics["clientWidth"],
                    "scroll_width": metrics["scrollWidth"],
                    "overflow_px": overflow_px,
                    "reason": (
                        "Mobile viewport has no horizontal overflow."
                        if passed
                        else "Mobile viewport has horizontal overflow."
                    ),
                },
            )

        except Exception as exc:
            return self._build_exception_check(check=check, exc=exc)

        finally:
            if original_viewport is not None:
                page.set_viewport_size(original_viewport)

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