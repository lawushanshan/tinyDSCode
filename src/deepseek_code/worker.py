from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

from rich.console import Console

from .harness import Harness
from .llm_service import LLMService, ToolCall
from .memory import MemoryManager

if TYPE_CHECKING:
    from .supervisor import Ticket

console = Console()

MAX_CONSECUTIVE_NO_PROGRESS = 3
MAX_CONSECUTIVE_IDENTICAL_TOOL_CALLS = 3
PROGRESS_CHECK_INTERVAL = 5


def _truncate(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


@dataclass
class StepDirective:
    """Supervisor 通过回调返回给 Worker 的指令"""
    approved: bool = True
    inject_message: str | None = None
    abort: bool = False


@dataclass
class AgentStep:
    iteration: int
    ticket_id: str
    assistant_content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    injected_messages: list[str] = field(default_factory=list)
    done_reason: str | None = None


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
        self.last_steps: list[AgentStep] = []

    def execute_ticket(
        self,
        ticket: "Ticket",
        model: str = "deepseek-v4-flash",
        on_step: Callable[[str, ...], StepDirective] | None = None,
    ) -> str:
        self.memory.load_ticket(ticket)
        self.last_steps = []
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
            step = AgentStep(iteration=iteration, ticket_id=ticket.ticket_id)
            self.last_steps.append(step)
            console.print()
            console.print(f"[bold cyan]▸ 循环 {iteration}/{max_iterations}[/bold cyan]")

            # 进度检查：每 N 次循环注入提醒
            if on_step and iteration > 1 and iteration % PROGRESS_CHECK_INTERVAL == 0:
                directive = on_step("progress_check", ticket=ticket, iteration=iteration)
                if directive.abort:
                    console.print("[yellow]⚠ Supervisor 中止任务[/yellow]")
                    ticket.status = "failed"
                    step.done_reason = "aborted_by_supervisor"
                    return "（任务被 Supervisor 中止）"
                if directive.inject_message:
                    self.memory.append_system(directive.inject_message)
                    step.injected_messages.append(directive.inject_message)
                    console.print("[bold blue]📋 进度检查[/bold blue]")

            messages = self.memory.build_messages()
            tools_schema = (
                self.harness.tool_registry.to_openai_schema()
                if self.harness.tool_registry
                else None
            )
            response = self.llm_service.chat(messages=messages, tools=tools_schema)
            step.assistant_content = response.content
            step.tool_calls = list(response.tool_calls or [])

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
                        step.done_reason = "no_progress"
                        return response.content or "（无输出）"
                else:
                    consecutive_no_progress = 0
                last_content = response.content
                ticket.status = "done"
                step.done_reason = "assistant_final"
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
                    step.done_reason = "repeated_tool_calls"
                    return last_content or "（检测到重复工具调用，循环已终止）"
            else:
                consecutive_identical_calls = 0
            last_tool_signature = current_signature

            for tc in response.tool_calls:
                args_summary = ", ".join(f"{k}={_truncate(str(v), 80)}" for k, v in tc.arguments.items())
                console.print(f"[yellow]⚡ 工具调用:[/yellow] {tc.name}({args_summary})")

                # 请求 Supervisor 审批
                if on_step:
                    directive = on_step("before_tool_call", ticket=ticket, tool_call=tc, iteration=iteration)
                    if directive.abort:
                        console.print("[yellow]⚠ Supervisor 中止任务[/yellow]")
                        ticket.status = "failed"
                        step.done_reason = "aborted_by_supervisor"
                        return "（任务被 Supervisor 中止）"
                    if not directive.approved:
                        console.print(f"[red]⊘ 工具被拒绝:[/red] {tc.name}")
                        self.memory.append_tool_result(f"（操作已被 Supervisor 拒绝）{tc.name}({args_summary})")
                        if directive.inject_message:
                            self.memory.append_system(directive.inject_message)
                            step.injected_messages.append(directive.inject_message)
                        break

                result = self.harness.execute_tool_call_structured(tc)
                step.tool_results.append(result)
                if not result.ok:
                    console.print(f"[red]✗ 工具失败:[/red] {_truncate(result.text, 150)}")
                else:
                    console.print(f"[green]✓ 工具结果:[/green] {_truncate(result.text, 150)}")
                self.memory.append_tool_result(f"工具执行结果：{result.text}")

                # 执行后汇报
                if on_step:
                    on_step("after_tool_call", ticket=ticket, tool_call=tc, result=result.text, tool_result=result)

        console.print(f"[yellow]⚠ 达到最大循环次数 {max_iterations}，Ticket 未完成[/yellow]")
        if self.last_steps:
            self.last_steps[-1].done_reason = "max_iterations"
        return last_content or f"[警告] 达到最大循环次数 {max_iterations}，Ticket 未完成。"
