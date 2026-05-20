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

    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    default_model = config.default or "deepseek-v4-flash"

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
