from deepseek_code.eval.models import EvalTask, TaskResult, EvalReport, Difficulty, TestOutcome


def test_eval_task_creation() -> None:
    task = EvalTask(
        task_id="test_001",
        prompt="def foo(): pass",
        test_code="assert foo() is None",
        entry_point="foo",
    )
    assert task.task_id == "test_001"
    assert task.difficulty == Difficulty.EASY
    assert task.category == "general"


def test_task_result_defaults() -> None:
    result = TaskResult(
        task_id="test_001",
        entry_point="foo",
        category="general",
        difficulty=Difficulty.EASY,
    )
    assert result.passed is False
    assert result.outcome == TestOutcome.ERROR
    assert result.raw_agent_output == ""


def test_task_result_passed() -> None:
    result = TaskResult(
        task_id="test_001",
        entry_point="foo",
        category="general",
        difficulty=Difficulty.EASY,
        passed=True,
        outcome=TestOutcome.PASSED,
    )
    assert result.passed is True


def test_eval_report_defaults() -> None:
    report = EvalReport(model="test-model")
    assert report.total_tasks == 0
    assert report.pass_at_1 == 0.0
    assert report.results == []


def test_eval_report_serialization() -> None:
    report = EvalReport(model="test-model")
    report.total_tasks = 10
    report.passed = 7
    report.pass_at_1 = 70.0
    json_str = report.model_dump_json()
    assert "test-model" in json_str
    assert "70.0" in json_str

    restored = EvalReport.model_validate_json(json_str)
    assert restored.model == "test-model"
    assert restored.passed == 7
