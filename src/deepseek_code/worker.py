from __future__ import annotations
import json
from typing import TYPE_CHECKING, Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .harness import Harness
from .llm_service import LLMService, LLMResponse
from .memory import MemoryManager

if TYPE_CHECKING:
    from .supervisor import Ticket

console = Console()

MAX_CONSECUTIVE_NO_PROGRESS = 3
MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 3


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _tool_calls_signature(tool_calls) -> str:
    """将 tool_calls 列表序列化为可比较的签名字符串"""
    parts = []
    for tc in tool_calls:
        args_json = json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)
        parts.append(f"{tc.name}:{args_json}")
    return "|".join(parts)


class Worker:
    def __init__(
        self,
        harness: Harness,
        llm_service: LLMService,
        memory: MemoryManager,
    ) -> None:
        self.harness = harness
        self.llm_service = llm_service
        self.memory = memory

    def execute_ticket(self, ticket: "Ticket", model: str = "deepseek-v4-flash") -> str:
        self.memory.load_ticket(ticket)
        console.print()
        console.rule(f"[bold green]Worker: 执行 {ticket.ticket_id}[/bold green]")
        console.print(f"[dim]描述: {ticket.description}[/dim]")

        max_iterations = getattr(ticket, "max_loop_iterations", 10)
        iteration = 0
        consecutive_no_progress = 0
        consecutive_identical_calls = 0
        last_content: Optional[str] = None
        last_tool_signature: Optional[str] = None

        while iteration < max_iterations:
            iteration += 1
            console.print()
            console.print(f"[bold cyan]▸ 循环 {iteration}/{max_iterations}[/bold cyan]")

            messages = self.memory.build_messages()
            tools_schema = (
                self.harness.tool_registry.to_openai_schema()
                if self.harness.tool_registry
                else None
            )
            response = self.llm_service.chat(messages=messages, tools=tools_schema)

            if response.content:
                self.memory.append_assistant(response.content)
                console.print(f"[magenta]💭 思考:[/magenta] {_truncate(response.content)}")

            if not response.tool_calls:
                if response.content == last_content:
                    consecutive_no_progress += 1
                    if consecutive_no_progress >= MAX_CONSECUTIVE_NO_PROGRESS:
                        console.print(
                            f"[yellow]⚠ 连续 {MAX_CONSECUTIVE_NO_PROGRESS} 次无进展，终止循环[/yellow]"
                        )
                        return response.content or "（无输出）"
                else:
                    consecutive_no_progress = 0
                last_content = response.content
                ticket.status = "done"
                console.print(f"[bold green]✓ Ticket 完成[/bold green]")
                return response.content or "（无输出）"

            consecutive_no_progress = 0
            last_content = response.content

            current_signature = _tool_calls_signature(response.tool_calls)
            if current_signature == last_tool_signature:
                consecutive_identical_calls += 1
                if consecutive_identical_calls >= MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS:
                    console.print(
                        f"[yellow]⚠ 连续 {MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS} 次相同工具调用，终止循环[/yellow]"
                    )
                    return last_content or "（检测到重复工具调用，循环已终止）"
            else:
                consecutive_identical_calls = 0
            last_tool_signature = current_signature

            for tc in response.tool_calls:
                args_summary = ", ".join(f"{k}={_truncate(str(v), 80)}" for k, v in tc.arguments.items())
                console.print(f"[yellow]⚡ 工具调用:[/yellow] {tc.name}({args_summary})")
                result = self.harness.execute_tool_call(tc)
                is_error = result.startswith("[命令执行失败") or result.startswith("[ERROR]")
                if is_error:
                    console.print(f"[red]✗ 工具失败:[/red] {_truncate(result, 150)}")
                else:
                    console.print(f"[green]✓ 工具结果:[/green] {_truncate(result, 150)}")
                self.memory.append_tool_result(f"工具执行结果：{result}")

        console.print(f"[yellow]⚠ 达到最大循环次数 {max_iterations}，Ticket 未完成[/yellow]")
        return last_content or f"[警告] 达到最大循环次数 {max_iterations}，Ticket 未完成。"
