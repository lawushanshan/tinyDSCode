import argparse
import io
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from .config import load_config, resolve_model, list_models
from .supervisor import Supervisor

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

console = Console()


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DeepSeek Code CLI - Claude Code 风格 AI 编码助手"
    )
    parser.add_argument("--config", default=None, help="配置文件路径")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="执行编码任务")
    run_parser.add_argument("prompt", help="任务描述")
    run_parser.add_argument("--model", default=None, help="模型预设名称或原始模型字符串")

    repl_parser = subparsers.add_parser("repl", help="启动交互式 REPL 会话")
    repl_parser.add_argument("--model", default=None, help="模型预设名称或原始模型字符串")

    subparsers.add_parser("models", help="列出可用的模型预设")

    eval_parser = subparsers.add_parser("eval", help="运行 L1 代码生成评估基准")
    eval_parser.add_argument("--model", default=None, help="模型预设名称或原始模型字符串")
    eval_parser.add_argument("--tasks-dir", default=None, help="自定义任务目录路径")
    eval_parser.add_argument("--task-ids", nargs="*", default=None, help="指定 task_id 列表")
    eval_parser.add_argument("--categories", nargs="*", default=None, help="按类别筛选")
    eval_parser.add_argument("--difficulties", nargs="*", default=None, help="按难度筛选")
    eval_parser.add_argument("--output-dir", default=None, help="报告输出目录")
    eval_parser.add_argument("--timeout", type=int, default=30, help="测试执行超时秒数")
    eval_parser.add_argument("--stop-on-error", action="store_true", help="首次失败即停")

    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    default_model = config.default or "deepseek-v4-flash"

    if args.command == "eval":
        from .eval.cli_handler import eval_run
        model_arg = args.model or default_model
        eval_run(
            model=model_arg,
            config=config,
            tasks_dir=args.tasks_dir,
            task_ids=args.task_ids,
            categories=args.categories,
            difficulties=args.difficulties,
            output_dir=args.output_dir,
            timeout=args.timeout,
            continue_on_error=not args.stop_on_error,
        )
        return

    if args.command == "models":
        models = list_models(config)
        if not models:
            console.print("[yellow]未配置模型预设。请在配置文件中添加 models 字段。[/yellow]")
            return
        table = Table(title="可用模型预设")
        table.add_column("预设名称", style="cyan")
        table.add_column("模型", style="green")
        table.add_column("API Base", style="dim")
        for m in models:
            marker = " (默认)" if m["name"] == default_model else ""
            table.add_row(m["name"] + marker, m["model"], m.get("api_base", "环境变量"))
        console.print(table)
        return

    model_arg = args.model or default_model
    model_name, llm_env = resolve_model(model_arg, config)
    is_repl = args.command == "repl"

    cwd = Path.cwd()
    supervisor = Supervisor(state_root=str(cwd), llm_env=llm_env, interactive=is_repl)
    supervisor.llm_service.model = model_name

    if args.command == "run":
        console.print(f"[bold cyan]DeepSeek Code CLI[/bold cyan] 使用模型: {model_name}")
        result = supervisor.handle_prompt(args.prompt, model=model_name)
        console.print(result)
    elif args.command == "repl":
        console.print(f"[bold cyan]DeepSeek Code CLI[/bold cyan] 使用模型: {model_name}")
        supervisor.start_repl(model=model_name)
