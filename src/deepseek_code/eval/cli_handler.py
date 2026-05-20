from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console

from ..config import AppConfig, resolve_model
from ..supervisor import Supervisor
from .loader import TaskLoader
from .evaluator import Evaluator
from .reporter import ReportGenerator


def eval_run(
    model: str,
    config: AppConfig,
    tasks_dir: Optional[str] = None,
    task_ids: Optional[list[str]] = None,
    categories: Optional[list[str]] = None,
    difficulties: Optional[list[str]] = None,
    output_dir: Optional[str] = None,
    timeout: int = 30,
    continue_on_error: bool = True,
) -> None:
    console = Console()

    model_name, llm_env = resolve_model(model, config)

    console.print(f"[bold cyan]DeepSeek Code Eval[/bold cyan] Model: {model_name}")

    loader = TaskLoader(tasks_dir=tasks_dir)
    try:
        tasks = loader.load_filtered(
            categories=categories,
            difficulties=difficulties,
            task_ids=task_ids,
        )
    except Exception as e:
        console.print(f"[red]Failed to load tasks: {e}[/red]")
        return

    if not tasks:
        console.print("[yellow]No tasks matched the given filters.[/yellow]")
        return

    console.print(f"[dim]Loaded {len(tasks)} task(s)[/dim]")

    supervisor = Supervisor(
        state_root=None,
        llm_env=llm_env,
        interactive=False,
    )
    supervisor.llm_service.model = model_name

    evaluator = Evaluator(
        supervisor=supervisor,
        model=model_name,
        timeout_seconds=timeout,
        console=console,
    )
    report = evaluator.run_all(tasks, continue_on_error=continue_on_error)

    reporter = ReportGenerator(console=console)
    reporter.print_summary(report)

    if output_dir is None:
        output_dir = str(Path.cwd() / ".eval_reports")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    ts = report.run_timestamp.replace(":", "-").replace(".", "-")[:19]
    json_path = out / f"eval_{ts}.json"
    html_path = out / f"eval_{ts}.html"

    reporter.save_json(report, json_path)
    reporter.save_html(report, html_path)

    console.print(f"\n[green]Report saved:[/green]")
    console.print(f"  JSON: {json_path}")
    console.print(f"  HTML: {html_path}")
