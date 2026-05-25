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
        extracted = ""
        
        written_file_paths = self._extract_written_file_paths(raw_output)
        if written_file_paths:
            target_file = self._find_target_file(written_file_paths, task.entry_point)
            if target_file:
                try:
                    from ..tools import Tools
                    extracted = Tools.read_file(target_file)
                except Exception:
                    pass
        
        if not extracted:
            extracted = self.code_extractor.extract(raw_output, task.entry_point)
        
        if not extracted:
            extracted = self._extract_code_from_output(raw_output, task.entry_point)
        
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

    def _extract_written_file_paths(self, raw_output: str) -> list[str]:
        import re
        patterns = [
            r"已写入 (.+)",
            r"已创建文件 (.+)",
            r"文件 (.+) 已创建",
            r"写入文件 (.+)",
            r"文件位置\n(.+) —",
            r"代码已写入 (.+)",
        ]
        all_paths = []
        for pattern in patterns:
            matches = re.findall(pattern, raw_output)
            all_paths.extend(matches)
        
        cleaned_paths = []
        for path in all_paths:
            path = path.strip()
            path = path.replace("`", "")
            path = path.replace("'", "")
            path = path.replace('"', "")
            if path and (path.endswith(".py") or "/" in path or "\\" in path):
                cleaned_paths.append(path)
        
        if not cleaned_paths:
            cleaned_paths = self._extract_with_llm(raw_output)
        
        return cleaned_paths

    def _extract_with_llm(self, raw_output: str) -> list[str]:
        prompt = f"""
从以下文本中提取所有写入的Python文件路径。
只返回文件路径列表，格式为JSON数组。
如果没有找到文件路径，返回空数组 []。

文本：
{raw_output[:1000]}

返回格式示例：
["/path/to/file.py", "D:\\path\\to\\file.py"]
        """
        
        try:
            llm_service = getattr(self.supervisor, "llm_service", None)
            if llm_service is None:
                return []
            response = llm_service.chat(messages=[{"role": "user", "content": prompt}])
            import json
            cleaned = response.content.strip() if response.content else "[]"
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start == -1 or end == -1:
                return []
            paths = json.loads(cleaned[start:end + 1])
            return paths if isinstance(paths, list) else []
        except Exception:
            return []

    def _extract_code_from_output(self, raw_output: str, entry_point: str) -> str:
        import re
        
        blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", raw_output, re.DOTALL)
        
        for block in blocks:
            if f"def {entry_point}" in block or f"class {entry_point}" in block:
                if "..." in block:
                    continue
                return block.strip()
        
        for block in blocks:
            if entry_point.replace("_", "") in block.replace("_", "").lower():
                if "..." in block:
                    continue
                return block.strip()
        
        for block in blocks:
            if f"def {entry_point}" in block or f"class {entry_point}" in block:
                lines = block.split('\n')
                complete_lines = []
                for line in lines:
                    if line.strip() == "...":
                        continue
                    complete_lines.append(line)
                return '\n'.join(complete_lines).strip()
        
        return ""

    def _find_target_file(self, file_paths: list[str], entry_point: str) -> str | None:
        for path in file_paths:
            if entry_point in path or entry_point.replace("_", "") in path.replace("_", "").lower():
                return path
        return None

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
