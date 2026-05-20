from pathlib import Path

from deepseek_code.eval.models import EvalReport, TaskResult, EvalTask, Difficulty, TestOutcome
from deepseek_code.eval.reporter import ReportGenerator


def _make_report() -> EvalReport:
    report = EvalReport(model="test-model")
    report.total_tasks = 3
    report.passed = 2
    report.failed = 1
    report.pass_at_1 = 66.7
    report.results = [
        TaskResult(
            task_id="a", entry_point="f", category="string",
            difficulty=Difficulty.EASY, passed=True,
            outcome=TestOutcome.PASSED,
            agent_time_seconds=1.0, execution_time_seconds=0.1,
        ),
        TaskResult(
            task_id="b", entry_point="g", category="algorithm",
            difficulty=Difficulty.MEDIUM, passed=True,
            outcome=TestOutcome.PASSED,
            agent_time_seconds=2.0, execution_time_seconds=0.2,
        ),
        TaskResult(
            task_id="c", entry_point="h", category="string",
            difficulty=Difficulty.EASY, passed=False,
            outcome=TestOutcome.FAILED,
            agent_time_seconds=1.5, execution_time_seconds=0.1,
            error_message="assert 1 == 2",
        ),
    ]
    report.total_agent_time_seconds = 4.5
    report.total_execution_time_seconds = 0.4
    report.by_difficulty = {"easy": {"passed": 1, "total": 2}, "medium": {"passed": 1, "total": 1}}
    report.by_category = {"string": {"passed": 1, "total": 2}, "algorithm": {"passed": 1, "total": 1}}
    return report


def test_save_json(tmp_path: Path) -> None:
    reporter = ReportGenerator()
    report = _make_report()
    path = tmp_path / "report.json"
    reporter.save_json(report, path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "test-model" in content
    assert "66.7" in content


def test_save_html(tmp_path: Path) -> None:
    reporter = ReportGenerator()
    report = _make_report()
    path = tmp_path / "report.html"
    reporter.save_html(report, path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "test-model" in content
    assert "pass" in content
    assert "fail" in content


def test_print_summary_does_not_crash() -> None:
    from io import StringIO
    from rich.console import Console
    buf = StringIO()
    console = Console(file=buf, force_terminal=False)
    reporter = ReportGenerator(console=console)
    reporter.print_summary(_make_report())
    output = buf.getvalue()
    assert "test-model" in output
    assert "66.7" in output
