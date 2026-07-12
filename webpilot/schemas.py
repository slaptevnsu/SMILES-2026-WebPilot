from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TaskType = Literal["text_generation", "diagnostic_repair"]
AgentVariant = Literal["base", "browser-feedback"]


class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    task_type: TaskType = Field(alias="type")
    instruction: str
    repo_path: Path | None = None
    max_iterations:int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

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

class RunSummary(BaseModel):
    task_id: str
    task_type: TaskType
    variant: AgentVariant
    status: str
    run_dir: str
    message: str