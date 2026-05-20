from __future__ import annotations

import time
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from ..supervisor import Supervisor
from .models import EvalTask, TaskResult, EvalReport, TestOutcome
from .extractor import CodeExtractor
from .test_runner import TestRunner


class Evaluator:
    def __init__(
        self,
        supervisor: Supervisor,
        model: str,
        timeout_seconds: int = 30,
        console: Optional[Console] = None,
    ) -> None:
        self.supervisor = supervisor
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.console = console or Console()
        self.code_extractor = CodeExtractor()
        self.test_runner = TestRunner(timeout_seconds=timeout_seconds)

    def run_single(self, task: EvalTask) -> TaskResult:
        result = TaskResult(
            task_id=task.task_id,
            entry_point=task.entry_point,
            category=task.category,
            difficulty=task.difficulty,
        )

        # Step 1: Agent generation
        agent_start = time.monotonic()
        try:
            raw_output = self.supervisor.handle_prompt(task.prompt, model=self.model)
            result.raw_agent_output = raw_output
        except Exception as e:
            result.error_message = f"Agent error: {e}"
            result.outcome = TestOutcome.ERROR
            result.agent_time_seconds = time.monotonic() - agent_start
            return result
        result.agent_time_seconds = time.monotonic() - agent_start

        # Step 2: Code extraction
        extracted = self.code_extractor.extract(raw_output, task.entry_point)
        if not extracted:
            result.error_message = "Could not extract function from agent output"
            result.outcome = TestOutcome.ERROR
            return result
        result.extracted_code = extracted

        # Step 3: Test execution
        exec_start = time.monotonic()
        test_result = self.test_runner.run(
            code=extracted,
            test_code=task.test_code,
            entry_point=task.entry_point,
        )
        result.execution_time_seconds = time.monotonic() - exec_start
        result.test_stdout = test_result.stdout
        result.test_stderr = test_result.stderr

        if test_result.timeout:
            result.outcome = TestOutcome.TIMEOUT
        elif test_result.exit_code == 0:
            result.passed = True
            result.outcome = TestOutcome.PASSED
        elif test_result.syntax_error:
            result.outcome = TestOutcome.ERROR
            result.error_message = f"Syntax error: {test_result.stderr[:200]}"
        else:
            result.outcome = TestOutcome.FAILED
            result.error_message = f"Test failed: {test_result.stderr[:200]}"

        return result

    def run_all(
        self,
        tasks: list[EvalTask],
        continue_on_error: bool = True,
    ) -> EvalReport:
        report = EvalReport(model=self.model, total_tasks=len(tasks))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            overall = progress.add_task("Evaluating...", total=len(tasks))
            for task in tasks:
                progress.update(
                    overall,
                    description=f"[cyan]{task.task_id} ({task.difficulty.value})",
                )
                result = self.run_single(task)
                report.results.append(result)

                if result.passed:
                    report.passed += 1
                elif result.outcome == TestOutcome.TIMEOUT:
                    report.timeouts += 1
                elif result.outcome == TestOutcome.ERROR:
                    report.errors += 1
                else:
                    report.failed += 1

                report.total_agent_time_seconds += result.agent_time_seconds
                report.total_execution_time_seconds += result.execution_time_seconds

                if not continue_on_error and not result.passed:
                    self.console.print(f"[red]Stopping on failure: {task.task_id}[/red]")
                    break

                progress.advance(overall)

        report.pass_at_1 = round(
            report.passed / max(report.total_tasks, 1) * 100, 1
        )
        self._compute_breakdowns(report)
        return report

    @staticmethod
    def _compute_breakdowns(report: EvalReport) -> None:
        by_diff: dict[str, dict[str, int]] = {}
        by_cat: dict[str, dict[str, int]] = {}
        for r in report.results:
            d = r.difficulty.value
            c = r.category
            if d not in by_diff:
                by_diff[d] = {"passed": 0, "total": 0}
            by_diff[d]["total"] += 1
            if r.passed:
                by_diff[d]["passed"] += 1
            if c not in by_cat:
                by_cat[c] = {"passed": 0, "total": 0}
            by_cat[c]["total"] += 1
            if r.passed:
                by_cat[c]["passed"] += 1
        report.by_difficulty = by_diff
        report.by_category = by_cat
