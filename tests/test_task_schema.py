from pathlib import Path

import pytest
from pydantic import ValidationError

from webpilot.schemas import InteractionCheck, Task


def test_editing_task_requires_repo_path() -> None:
    with pytest.raises(ValidationError, match="editing tasks must define repo_path"):
        Task(
            id="editing_missing_repo",
            task_type="editing",
            instruction="Add a testimonials section.",
            repo_path=None,
        )


def test_diagnostic_repair_task_requires_repo_path() -> None:
    with pytest.raises(ValidationError, match="diagnostic_repair tasks must define repo_path"):
        Task(
            id="repair_missing_repo",
            task_type="diagnostic_repair",
            instruction="Fix the app.",
            repo_path=None,
        )


def test_text_generation_task_accepts_blank_repo_path() -> None:
    task = Task(
        id="generation_task",
        task_type="text_generation",
        instruction="Generate a page.",
        repo_path=Path("examples/blank_react_app"),
        max_iterations=2,
    )

    assert task.task_type == "text_generation"
    assert task.repo_path == Path("examples/blank_react_app")
    assert task.max_iterations == 2


def test_max_iterations_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="max_iterations must be >= 1"):
        Task(
            id="bad_iterations",
            task_type="text_generation",
            instruction="Generate a page.",
            repo_path=Path("examples/blank_react_app"),
            max_iterations=0,
        )


def test_click_increment_check_requires_action_selector() -> None:
    with pytest.raises(
        ValidationError,
        match="click_increments_text_int checks must define action_selector",
    ):
        InteractionCheck(
            name="bad increment check",
            kind="click_increments_text_int",
            target_selector="[data-testid='count']",
        )


def test_fill_updates_text_requires_input_selector_and_value() -> None:
    with pytest.raises(
        ValidationError,
        match="fill_updates_text checks must define input_selector",
    ):
        InteractionCheck(
            name="bad fill check",
            kind="fill_updates_text",
            target_selector="[data-testid='output']",
            value="hello",
        )

    with pytest.raises(
        ValidationError,
        match="fill_updates_text checks must define value",
    ):
        InteractionCheck(
            name="bad fill check",
            kind="fill_updates_text",
            target_selector="[data-testid='output']",
            input_selector="[data-testid='input']",
        )


def test_click_reveals_text_requires_action_selector_and_target_text() -> None:
    with pytest.raises(
        ValidationError,
        match="click_reveals_text checks must define action_selector",
    ):
        InteractionCheck(
            name="bad reveal check",
            kind="click_reveals_text",
            target_selector="main",
            target_text="Done",
        )

    with pytest.raises(
        ValidationError,
        match="click_reveals_text checks must define target_text",
    ):
        InteractionCheck(
            name="bad reveal check",
            kind="click_reveals_text",
            target_selector="main",
            action_selector="button",
        )


def test_tabs_switch_content_requires_action_selector() -> None:
    with pytest.raises(
        ValidationError,
        match="tabs_switch_content checks must define action_selector",
    ):
        InteractionCheck(
            name="bad tabs check",
            kind="tabs_switch_content",
            target_selector="section[role='tabpanel']",
        )
