from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from rich.console import Console

from .harness import Harness
from .llm_service import LLMService, LLMResponse
from .memory import MemoryManager

if TYPE_CHECKING:
    from .supervisor import Ticket

console = Console()

MAX_CONSECUTIVE_NO_PROGRESS = 3


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
        console.print(f"[green]Worker:[/green] 执行 Ticket {ticket.ticket_id}")

        max_iterations = getattr(ticket, "max_loop_iterations", 10)
        iteration = 0
        consecutive_no_progress = 0
        last_content: Optional[str] = None

        while iteration < max_iterations:
            iteration += 1
            console.print(f"[dim]--- 循环 {iteration}/{max_iterations} ---[/dim]")

            messages = self.memory.build_messages()
            tools_schema = (
                self.harness.tool_registry.to_openai_schema()
                if self.harness.tool_registry
                else None
            )
            response = self.llm_service.chat(messages=messages, tools=tools_schema)

            if response.content:
                self.memory.append_assistant(response.content)

            if not response.tool_calls:
                if response.content == last_content:
                    consecutive_no_progress += 1
                    if consecutive_no_progress >= MAX_CONSECUTIVE_NO_PROGRESS:
                        console.print(
                            f"[yellow]连续 {MAX_CONSECUTIVE_NO_PROGRESS} 次无进展，终止循环[/yellow]"
                        )
                        return response.content or "（无输出）"
                else:
                    consecutive_no_progress = 0
                last_content = response.content
                ticket.status = "done"
                return response.content or "（无输出）"

            consecutive_no_progress = 0
            last_content = response.content

            for tc in response.tool_calls:
                result = self.harness.execute_tool_call(tc)
                self.memory.append_tool_result(f"工具执行结果：{result}")

        console.print(f"[yellow]达到最大循环次数 {max_iterations}，Ticket 未完成[/yellow]")
        return last_content or f"[警告] 达到最大循环次数 {max_iterations}，Ticket 未完成。"
