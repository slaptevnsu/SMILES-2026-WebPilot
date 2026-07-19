from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TaskType = Literal["text_generation", "diagnostic_repair"]
AgentVariant = Literal[
    "base",
    "deterministic-browser-feedback",
    "llm-code-only",
    "llm-browser-feedback",
]
TestStatus = Literal["passed", "failed", "skipped"]
RepairStatus = Literal["applied", "skipped", "failed"]
InteractionCheckKind = Literal[
    "click_increments_text_int",
    "fill_updates_text",
]


class InteractionCheck(BaseModel):
    name: str
    kind: InteractionCheckKind
    target_selector: str
    action_selector: str | None = None
    input_selector: str | None = None
    value: str | None = None
    timeout_ms: int = 5000
    settle_ms: int = 300

    @model_validator(mode="after")
    def validate_check(self) -> "InteractionCheck":
        if self.kind == "click_increments_text_int" and self.action_selector is None:
            raise ValueError("click_increments_text_int checks must define action_selector")

        if self.kind == "fill_updates_text":
            if self.input_selector is None:
                raise ValueError("fill_updates_text checks must define input_selector")
            if self.value is None:
                raise ValueError("fill_updates_text checks must define value")

        return self

class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task_type: TaskType = Field(alias="type")
    instruction: str
    repo_path: Path | None = None
    max_iterations:int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
    interaction_checks: list[InteractionCheck] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task(self) -> "Task":
        if self.task_type == "diagnostic_repair" and self.repo_path is None:
            raise ValueError("diagnostic_repair tasks must define repo_path")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        return self
    
class Plan(BaseModel):
    task_id: str
    task_type: TaskType
    variant: AgentVariant
    steps: list[str]
    expected_artifacts: list[str]

class TestCheckResult(BaseModel):
    name: str
    status: TestStatus
    details: dict[str, Any] = Field(default_factory=dict)

class InteractionTestResult(BaseModel):
    status: TestStatus
    checks: list[TestCheckResult]
    passed_count: int
    failed_count: int
    skipped_count: int

class RunSummary(BaseModel):
    task_id: str
    task_type: TaskType
    variant: AgentVariant
    status: str
    run_dir: str
    message: str
    browser: BrowserRunResult | None = None
    initial_browser: BrowserRunResult | None = None
    repair: RepairResult | None = None
    repair_iterations: list[RepairIterationRecord] = Field(default_factory=list)

class BrowserRunResult(BaseModel):
    repo_path: str
    url: str
    port: int
    status: str
    artifacts: dict[str, str]
    console_log_count: int
    page_error_count: int
    test_status: TestStatus | None = None
    passed_test_count: int = 0
    failed_test_count: int = 0

class RepairResult(BaseModel):
    status: RepairStatus
    reason: str
    target_file: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)

class EvaluationRunRecord(BaseModel):
    task_id: str
    task_type: TaskType
    variant: AgentVariant
    status: str
    run_dir: str
    final_browser_status: str | None = None
    final_test_status: TestStatus | None = None
    passed_test_count: int = 0
    failed_test_count: int = 0
    initial_browser_status: str | None = None
    initial_test_status: TestStatus | None = None
    repair_status: RepairStatus | None = None

class EvaluationSummary(BaseModel):
    evaluation_id: str
    output_dir: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    repaired_runs: int
    records: list[EvaluationRunRecord]

class RepairIterationRecord(BaseModel):
    iteration: int
    status: str
    repair: RepairResult | None = None
    browser: BrowserRunResult | None = None