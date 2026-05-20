from deepseek_code.eval.test_runner import TestRunner


def test_run_passing_test() -> None:
    runner = TestRunner(timeout_seconds=10)
    result = runner.run(
        code="def add(a, b): return a + b",
        test_code="assert add(1, 2) == 3\nassert add(-1, 1) == 0",
    )
    assert result.exit_code == 0
    assert "All tests passed" in result.stdout
    assert not result.syntax_error


def test_run_failing_test() -> None:
    runner = TestRunner(timeout_seconds=10)
    result = runner.run(
        code="def add(a, b): return a + b",
        test_code="assert add(1, 2) == 999",
    )
    assert result.exit_code != 0
    assert not result.timeout


def test_run_syntax_error() -> None:
    runner = TestRunner(timeout_seconds=10)
    result = runner.run(
        code="def broken(:\n    pass",
        test_code="assert True",
    )
    assert result.syntax_error is True
    assert result.exit_code != 0


def test_run_timeout() -> None:
    runner = TestRunner(timeout_seconds=2)
    result = runner.run(
        code="import time\ndef slow():\n    time.sleep(100)\nslow()",
        test_code="",
    )
    assert result.timeout is True
