from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TestOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class EvalTask(BaseModel):
    task_id: str
    prompt: str
    test_code: str
    entry_point: str
    difficulty: Difficulty = Difficulty.EASY
    category: str = "general"
    description: str = ""


class TaskResult(BaseModel):
    task_id: str
    entry_point: str
    category: str
    difficulty: Difficulty
    passed: bool = False
    outcome: TestOutcome = TestOutcome.ERROR
    raw_agent_output: str = ""
    extracted_code: str = ""
    test_stdout: str = ""
    test_stderr: str = ""
    execution_time_seconds: float = 0.0
    agent_time_seconds: float = 0.0
    error_message: str = ""


class EvalReport(BaseModel):
    model: str
    run_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    timeouts: int = 0
    pass_at_1: float = 0.0
    total_agent_time_seconds: float = 0.0
    total_execution_time_seconds: float = 0.0
    results: list[TaskResult] = Field(default_factory=list)
    by_difficulty: dict[str, dict[str, int]] = Field(default_factory=dict)
    by_category: dict[str, dict[str, int]] = Field(default_factory=dict)
