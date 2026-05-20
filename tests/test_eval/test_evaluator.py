from unittest.mock import MagicMock, patch
from pathlib import Path

from deepseek_code.eval.models import EvalTask, Difficulty, TestOutcome
from deepseek_code.eval.evaluator import Evaluator
from deepseek_code.supervisor import Supervisor


def _make_evaluator() -> Evaluator:
    supervisor = MagicMock(spec=Supervisor)
    supervisor.handle_prompt = MagicMock()
    evaluator = Evaluator(
        supervisor=supervisor,
        model="mock",
        timeout_seconds=10,
    )
    return evaluator


def test_run_single_passed(tmp_path) -> None:
    evaluator = _make_evaluator()
    task = EvalTask(
        task_id="t1",
        prompt="def add(a, b): return a + b",
        test_code="assert add(1, 2) == 3",
        entry_point="add",
    )
    evaluator.supervisor.handle_prompt.return_value = (
        "```python\ndef add(a, b):\n    return a + b\n```"
    )
    result = evaluator.run_single(task)
    assert result.passed is True
    assert result.outcome == TestOutcome.PASSED


def test_run_single_failed(tmp_path) -> None:
    evaluator = _make_evaluator()
    task = EvalTask(
        task_id="t2",
        prompt="def add(a, b): return a + b",
        test_code="assert add(1, 2) == 999",
        entry_point="add",
    )
    evaluator.supervisor.handle_prompt.return_value = (
        "```python\ndef add(a, b):\n    return a + b\n```"
    )
    result = evaluator.run_single(task)
    assert result.passed is False
    assert result.outcome == TestOutcome.FAILED


def test_run_single_extract_failed(tmp_path) -> None:
    evaluator = _make_evaluator()
    task = EvalTask(
        task_id="t3",
        prompt="def foo(): pass",
        test_code="assert True",
        entry_point="foo",
    )
    evaluator.supervisor.handle_prompt.return_value = "I cannot solve this."
    result = evaluator.run_single(task)
    assert result.outcome == TestOutcome.ERROR
    assert "Could not extract" in result.error_message


def test_run_single_agent_error(tmp_path) -> None:
    evaluator = _make_evaluator()
    task = EvalTask(
        task_id="t4",
        prompt="def foo(): pass",
        test_code="assert True",
        entry_point="foo",
    )
    evaluator.supervisor.handle_prompt.side_effect = RuntimeError("API error")
    result = evaluator.run_single(task)
    assert result.outcome == TestOutcome.ERROR
    assert "Agent error" in result.error_message


def test_run_all(tmp_path) -> None:
    evaluator = _make_evaluator()
    tasks = [
        EvalTask(
            task_id="p1", prompt="def f(): return 1",
            test_code="assert f() == 1", entry_point="f",
        ),
        EvalTask(
            task_id="p2", prompt="def g(): return 2",
            test_code="assert g() == 2", entry_point="g",
        ),
    ]
    evaluator.supervisor.handle_prompt.side_effect = [
        "```python\ndef f(): return 1\n```",
        "```python\ndef g(): return 2\n```",
    ]
    report = evaluator.run_all(tasks)
    assert report.total_tasks == 2
    assert report.passed == 2
    assert report.pass_at_1 == 100.0


def test_run_all_with_failure(tmp_path) -> None:
    evaluator = _make_evaluator()
    tasks = [
        EvalTask(
            task_id="ok", prompt="def f(): return 1",
            test_code="assert f() == 1", entry_point="f",
        ),
        EvalTask(
            task_id="fail", prompt="def g(): return 0",
            test_code="assert g() == 1", entry_point="g",
        ),
    ]
    evaluator.supervisor.handle_prompt.side_effect = [
        "```python\ndef f(): return 1\n```",
        "```python\ndef g(): return 0\n```",
    ]
    report = evaluator.run_all(tasks)
    assert report.passed == 1
    assert report.failed == 1
    assert report.pass_at_1 == 50.0
