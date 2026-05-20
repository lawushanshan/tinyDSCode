from __future__ import annotations
import json
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Literal, Set
from pydantic import BaseModel, Field
from rich.console import Console
from rich.prompt import Prompt
from .worker import Worker
from .harness import Harness
from .llm_service import LLMService
from .memory import MemoryManager
from .tools import create_default_registry
from .persistence import StateManager


class SupervisorState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    DISPATCHING = "dispatching"
    WAITING_WORKER = "waiting_worker"
    REVIEWING = "reviewing"
    COMPLETE = "complete"
    FAILED = "failed"


VALID_TRANSITIONS: dict[SupervisorState, Set[SupervisorState]] = {
    SupervisorState.IDLE: {SupervisorState.PLANNING},
    SupervisorState.PLANNING: {SupervisorState.DISPATCHING, SupervisorState.FAILED},
    SupervisorState.DISPATCHING: {SupervisorState.WAITING_WORKER},
    SupervisorState.WAITING_WORKER: {SupervisorState.REVIEWING, SupervisorState.DISPATCHING, SupervisorState.FAILED},
    SupervisorState.REVIEWING: {SupervisorState.COMPLETE, SupervisorState.DISPATCHING, SupervisorState.FAILED},
    SupervisorState.COMPLETE: {SupervisorState.IDLE},
    SupervisorState.FAILED: {SupervisorState.IDLE},
}


class Ticket(BaseModel):
    ticket_id: str
    parent_ticket_id: Optional[str] = None
    status: Literal["pending", "running", "blocked", "done", "failed"] = "pending"
    description: str
    result: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    max_loop_iterations: int = 10
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    log: list[str] = Field(default_factory=list)


class Supervisor:
    def __init__(self, state_root: str | None = None, load_state: Optional[bool] = None,
                 llm_env: dict | None = None, interactive: bool = False) -> None:
        if load_state is None:
            load_state = state_root is not None
        self.state_manager = StateManager(root=state_root)
        self.tool_registry = create_default_registry()
        self.harness = Harness(state_root=self.state_manager.root, tool_registry=self.tool_registry,
                               interactive=interactive)
        self.memory = MemoryManager()
        self.llm_service = LLMService(env=llm_env)
        self.worker = Worker(harness=self.harness, llm_service=self.llm_service, memory=self.memory)
        self.tickets: List[Ticket] = []
        self.console = Console()
        self.ticket_counter = 0
        self.current_ticket: Optional[Ticket] = None
        self.state: SupervisorState = SupervisorState.IDLE
        if load_state:
            self._load_state()

    def _transition(self, new_state: SupervisorState) -> None:
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"非法状态转换: {self.state.value} -> {new_state.value}")
        self.state = new_state
        self._persist_state()

    def _persist_state(self) -> None:
        self.state_manager.save_supervisor_state({
            "state": self.state.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def _next_ticket_id(self) -> str:
        self.ticket_counter += 1
        return f"T-{self.ticket_counter:03d}"

    def create_ticket(self, prompt: str) -> Ticket:
        ticket = Ticket(ticket_id=self._next_ticket_id(), description=prompt)
        ticket.status = "pending"
        ticket.created_at = datetime.now(timezone.utc)
        ticket.updated_at = ticket.created_at
        ticket.log.append(f"创建 Ticket: {ticket.ticket_id}")
        self.tickets.append(ticket)
        self._persist_tickets()
        return ticket

    def start_ticket(self, ticket: Ticket) -> None:
        ticket.status = "running"
        ticket.updated_at = datetime.now(timezone.utc)
        ticket.log.append("Ticket 开始执行")
        self.current_ticket = ticket
        self.memory.clear_working()

    def complete_ticket(self, ticket: Ticket, result: str) -> None:
        ticket.status = "done"
        ticket.result = result
        ticket.updated_at = datetime.now(timezone.utc)
        ticket.log.append("Ticket 完成")
        self._persist_tickets()

    def list_tickets(self) -> str:
        if not self.tickets:
            return "当前没有 Ticket"
        lines = []
        for ticket in self.tickets:
            lines.append(f"{ticket.ticket_id} [{ticket.status}] - {ticket.description}")
        return "\n".join(lines)

    def start_repl(self, model: str = "deepseek-v4-flash") -> None:
        self.console.print("[green]输入 exit 或 quit 退出会话。[/green]")
        self.console.print("[green]输入 :tickets 查看当前 Ticket 列表。[/green]")
        self.console.print("[green]可用命令: :help, :tickets, :status, :new <描述>, exit[/green]")
        while True:
            user_input = Prompt.ask("[bold cyan]DeepSeek>[/bold cyan]")
            if user_input.strip().lower() in {"exit", "quit"}:
                break
            if user_input.strip() == ":help":
                self.console.print(
                    ":help - 显示帮助\n:tickets - 列出 Ticket\n:status - 当前 Ticket 状态\n:new <描述> - 创建并执行新 Ticket\nexit - 退出"
                )
                continue
            if user_input.strip() == ":tickets":
                self.console.print(self.list_tickets())
                continue
            if user_input.strip() == ":status":
                if self.current_ticket:
                    t = self.current_ticket
                    self.console.print(f"当前 Ticket: {t.ticket_id} [{t.status}]\n描述: {t.description}\n日志:\n" + "\n".join(t.log))
                else:
                    self.console.print("当前没有正在运行的 Ticket")
                continue
            if user_input.strip().startswith(":new "):
                desc = user_input.strip()[5:].strip()
                if not desc:
                    self.console.print("请提供任务描述，例如: :new 修复 auth.ts")
                    continue
                try:
                    response = self.handle_prompt(desc, model=model)
                    self.console.print(response)
                except Exception as e:
                    self.console.print(f"[red]任务执行出错: {e}[/red]")
                continue
            try:
                response = self.handle_prompt(user_input, model=model)
                self.console.print(response)
            except Exception as e:
                self.console.print(f"[red]任务执行出错: {e}[/red]")

    def plan_task(self, prompt: str, model: str) -> list[dict[str, str]]:
        planning_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个任务规划助手。请将用户请求拆分为具体的子任务步骤。\n"
                    "每步应独立可执行。\n"
                    '请以 JSON 数组格式返回，每个元素包含 "description" 字段（子任务描述）。\n'
                    '如果任务无法拆分或过于简单，返回包含单个元素的数组。\n'
                    '只输出 JSON 数组，不要输出其他内容。'
                ),
            },
            {"role": "user", "content": prompt},
        ]
        response = self.llm_service.chat(messages=planning_messages)
        return self._parse_plan(response.content or "[]")

    def _parse_plan(self, text: str) -> list[dict[str, str]]:
        cleaned = text.strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            plan = json.loads(cleaned[start:end + 1])
            if not isinstance(plan, list):
                return []
            return [item for item in plan if isinstance(item, dict) and "description" in item]
        except (json.JSONDecodeError, TypeError):
            return []

    def handle_prompt(self, prompt: str, model: str = "deepseek-v4-flash") -> str:
        try:
            self._transition(SupervisorState.PLANNING)
            parent_ticket = self.create_ticket(prompt)

            sub_tasks = self.plan_task(prompt, model)
            if len(sub_tasks) > 1:
                child_tickets = []
                for task in sub_tasks:
                    child = self.create_ticket(task["description"])
                    child.parent_ticket_id = parent_ticket.ticket_id
                    if "acceptance_criteria" in task:
                        child.acceptance_criteria = task["acceptance_criteria"]
                    child_tickets.append(child)
            else:
                child_tickets = [parent_ticket]

            results = []
            for ticket in child_tickets:
                self._transition(SupervisorState.DISPATCHING)
                self.start_ticket(ticket)

                self._transition(SupervisorState.WAITING_WORKER)
                response = self.worker.execute_ticket(ticket, model=model)
                results.append(f"[{ticket.ticket_id}] {response}")

            self._transition(SupervisorState.REVIEWING)
            final_result = "\n\n".join(results) if results else "（无结果）"
            self.complete_ticket(parent_ticket, final_result)
            self.state_manager.save_audit_log(self.worker.harness.audit_log)

            self._transition(SupervisorState.COMPLETE)
            return final_result
        except Exception:
            try:
                self._transition(SupervisorState.FAILED)
            except ValueError:
                pass
            raise
        finally:
            if self.state != SupervisorState.IDLE:
                try:
                    self._transition(SupervisorState.IDLE)
                except ValueError:
                    self.state = SupervisorState.IDLE

    def _load_state(self) -> None:
        raw_tickets = self.state_manager.load_tickets()
        for raw in raw_tickets:
            ticket = Ticket(**raw)
            self.tickets.append(ticket)
        self.ticket_counter = len(self.tickets)
        state_data = self.state_manager.load_supervisor_state()
        if state_data:
            self.state = SupervisorState(state_data.get("state", "idle"))

    def _persist_tickets(self) -> None:
        self.state_manager.save_tickets([ticket.model_dump() for ticket in self.tickets])
