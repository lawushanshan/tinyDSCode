from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .models import EvalReport, TestOutcome


class ReportGenerator:
    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    def print_summary(self, report: EvalReport) -> None:
        self.console.print()
        self.console.rule(f"[bold]Evaluation Report: {report.model}[/bold]")
        self.console.print(
            f"  Tasks: {report.total_tasks}  "
            f"[green]Passed: {report.passed}[/green]  "
            f"[red]Failed: {report.failed}[/red]  "
            f"[yellow]Errors: {report.errors}[/yellow]  "
            f"[yellow]Timeouts: {report.timeouts}[/yellow]"
        )
        self.console.print(
            f"  pass@1: [bold cyan]{report.pass_at_1}%[/bold cyan]  "
            f"Agent time: {report.total_agent_time_seconds:.1f}s  "
            f"Exec time: {report.total_execution_time_seconds:.1f}s"
        )

        table = Table(title="Task Results")
        table.add_column("ID", style="cyan", width=14)
        table.add_column("Category", width=16)
        table.add_column("Diff", width=8)
        table.add_column("Result", width=8)
        table.add_column("Agent(s)", justify="right", width=8)
        table.add_column("Exec(s)", justify="right", width=8)
        table.add_column("Error", style="dim")

        outcome_styles = {
            TestOutcome.PASSED: "[green]PASS[/green]",
            TestOutcome.FAILED: "[red]FAIL[/red]",
            TestOutcome.ERROR: "[yellow]ERR[/yellow]",
            TestOutcome.TIMEOUT: "[magenta]TOUT[/magenta]",
        }

        for r in report.results:
            table.add_row(
                r.task_id,
                r.category,
                r.difficulty.value,
                outcome_styles.get(r.outcome, "[dim]?[/dim]"),
                f"{r.agent_time_seconds:.1f}",
                f"{r.execution_time_seconds:.1f}",
                r.error_message[:50] if r.error_message else "",
            )
        self.console.print(table)

        if report.by_difficulty:
            self.console.print("\n[bold]By Difficulty:[/bold]")
            dt = Table()
            dt.add_column("Difficulty")
            dt.add_column("Passed", justify="right")
            dt.add_column("Total", justify="right")
            dt.add_column("Rate", justify="right")
            for diff, counts in sorted(report.by_difficulty.items()):
                rate = counts["passed"] / max(counts["total"], 1) * 100
                dt.add_row(diff, str(counts["passed"]), str(counts["total"]), f"{rate:.0f}%")
            self.console.print(dt)

        if report.by_category:
            self.console.print("\n[bold]By Category:[/bold]")
            ct = Table()
            ct.add_column("Category")
            ct.add_column("Passed", justify="right")
            ct.add_column("Total", justify="right")
            ct.add_column("Rate", justify="right")
            for cat, counts in sorted(report.by_category.items()):
                rate = counts["passed"] / max(counts["total"], 1) * 100
                ct.add_row(cat, str(counts["passed"]), str(counts["total"]), f"{rate:.0f}%")
            self.console.print(ct)

    def save_json(self, report: EvalReport, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def save_html(self, report: EvalReport, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render_html(report), encoding="utf-8")

    def _render_html(self, report: EvalReport) -> str:
        outcome_class = {
            TestOutcome.PASSED: "pass",
            TestOutcome.FAILED: "fail",
            TestOutcome.ERROR: "error",
            TestOutcome.TIMEOUT: "timeout",
        }
        task_rows = ""
        for r in report.results:
            cls = outcome_class.get(r.outcome, "")
            task_rows += f"""
            <tr class="{cls}">
                <td>{escape(r.task_id)}</td>
                <td>{escape(r.category)}</td>
                <td>{escape(r.difficulty.value)}</td>
                <td>{r.outcome.value}</td>
                <td>{r.agent_time_seconds:.1f}</td>
                <td>{r.execution_time_seconds:.1f}</td>
                <td>{escape(r.error_message[:100])}</td>
            </tr>
            <tr class="detail">
                <td colspan="7">
                    <details><summary>Generated Code</summary>
                    <pre><code>{escape(r.extracted_code or '(not extracted)')}</code></pre></details>
                    <details><summary>Agent Output</summary>
                    <pre><code>{escape(r.raw_agent_output[:2000])}</code></pre></details>
                    <details><summary>Test Output</summary>
                    <pre><code>{escape(r.test_stderr or r.test_stdout)}</code></pre></details>
                </td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Eval Report - {escape(report.model)}</title>
<style>
    body {{ font-family: -apple-system, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
    h1 {{ color: #333; }}
    .summary {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
    .stat {{ background: white; padding: 15px 25px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .stat .value {{ font-size: 2em; font-weight: bold; color: #2196F3; }}
    .stat .label {{ color: #666; font-size: 0.9em; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    th {{ background: #333; color: white; padding: 10px; text-align: left; }}
    td {{ padding: 8px 10px; border-bottom: 1px solid #eee; }}
    tr.pass td {{ background: #e8f5e9; }}
    tr.fail td {{ background: #ffebee; }}
    tr.error td {{ background: #fff3e0; }}
    tr.timeout td {{ background: #f3e5f5; }}
    tr.detail td {{ padding: 0 10px 10px; background: #fafafa; }}
    details {{ margin: 5px 0; }}
    pre {{ background: #263238; color: #eeffff; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; max-height: 300px; overflow-y: auto; }}
    .meta {{ color: #999; font-size: 0.85em; }}
</style>
</head>
<body>
<h1>Agent Evaluation Report</h1>
<p class="meta">Model: {escape(report.model)} | Time: {escape(report.run_timestamp)}</p>
<div class="summary">
    <div class="stat"><div class="value">{report.pass_at_1}%</div><div class="label">pass@1</div></div>
    <div class="stat"><div class="value">{report.passed}/{report.total_tasks}</div><div class="label">Passed</div></div>
    <div class="stat"><div class="value">{report.failed}</div><div class="label">Failed</div></div>
    <div class="stat"><div class="value">{report.errors}</div><div class="label">Errors</div></div>
    <div class="stat"><div class="value">{report.timeouts}</div><div class="label">Timeouts</div></div>
</div>
<table>
<tr><th>ID</th><th>Category</th><th>Difficulty</th><th>Result</th><th>Agent(s)</th><th>Exec(s)</th><th>Error</th></tr>
{task_rows}
</table>
</body>
</html>"""
