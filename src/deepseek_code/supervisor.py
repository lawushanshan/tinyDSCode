from __future__ import annotations
import difflib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Literal, Set
from pydantic import BaseModel, Field
from rich.console import Console
from rich.prompt import Prompt
from .worker import Worker, StepDirective, _truncate
from .harness import Harness
from .llm_service import LLMService, ToolCall
from .memory import MemoryManager
from .repo_map import RepoMapBuilder
from .tools import create_default_registry
from .persistence import StateManager

MAX_SUPERVISOR_ITERATIONS = 50


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
    status: Literal["pending", "running", "blocked", "done", "failed", "cancelled"] = "pending"
    description: str
    result: Optional[str] = None
    acceptance_criteria: Optional[str] = None
    max_loop_iterations: int = 10
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    log: list[str] = Field(default_factory=list)


@dataclass
class EvaluationAction:
    action: str
    reason: str = ""
    new_tasks: list[dict] | None = None


@dataclass
class TaskConstraints:
    disallowed_tools: set[str]
    reason: str = ""


class Supervisor:
    def __init__(self, state_root: str | None = None, load_state: Optional[bool] = None,
                 llm_env: dict | None = None, interactive: bool = False) -> None:
        if load_state is None:
            load_state = state_root is not None
        self.state_manager = StateManager(root=state_root)
        self.tool_registry = create_default_registry()
        self.harness = Harness(state_root=self.state_manager.project_root, tool_registry=self.tool_registry,
                               interactive=interactive)
        self.memory = MemoryManager()
        self.refresh_project_context()
        self.llm_service = LLMService(env=llm_env)
        self.worker = Worker(harness=self.harness, llm_service=self.llm_service, memory=self.memory)
        self.tickets: List[Ticket] = []
        self.console = Console()
        self.ticket_counter = 0
        self.current_ticket: Optional[Ticket] = None
        self.state: SupervisorState = SupervisorState.IDLE
        self.current_constraints = TaskConstraints(disallowed_tools=set())
        self.changed_files: list[str] = []
        self.context_files_seen: set[str] = set()
        self.context_search_performed = False
        if load_state:
            self._load_state()

    def _worker_on_step(self, step_type: str, **kwargs) -> StepDirective:
        if step_type == "before_tool_call":
            tc = kwargs.get("tool_call")
            ticket = kwargs.get("ticket")
            if tc and tc.name in self.current_constraints.disallowed_tools:
                reason = self.current_constraints.reason or f"用户约束禁止调用工具 {tc.name}"
                if ticket:
                    ticket.log.append(f"工具被拒绝: {tc.name} - {reason}")
                    ticket.updated_at = datetime.now(timezone.utc)
                    self._persist_tickets()
                return StepDirective(
                    approved=False,
                    inject_message=(
                        f"用户明确要求不要调用 {tc.name}。"
                        f"{reason} 请基于已提供的项目上下文直接回答，不要再调用该工具。"
                    ),
                )
            if tc and tc.name == "write_file" and self._path_exists(tc.arguments.get("path")):
                path = tc.arguments.get("path")
                reason = f"目标文件已存在: {path}。修改已有文件时请使用 apply_patch，避免整文件覆盖。"
                if ticket:
                    ticket.log.append(f"工具被拒绝: write_file - {reason}")
                    ticket.updated_at = datetime.now(timezone.utc)
                    self._persist_tickets()
                return StepDirective(
                    approved=False,
                    inject_message=(
                        f"{reason} 请先基于现有内容生成最小 unified diff，"
                        "然后调用 apply_patch(path, patch_text)。"
                    ),
                )
            if tc and tc.name == "apply_patch" and not self._has_edit_context(tc.arguments.get("path")):
                path = tc.arguments.get("path")
                reason = f"修改已有文件前需要先读取目标文件或执行定向搜索: {path}"
                if ticket:
                    ticket.log.append(f"工具被拒绝: apply_patch - {reason}")
                    ticket.updated_at = datetime.now(timezone.utc)
                    self._persist_tickets()
                return StepDirective(
                    approved=False,
                    inject_message=(
                        f"{reason}。请先调用 read_file(path) 查看目标文件当前内容，"
                        "或使用 search_files/search_content 定位相关代码后，再生成最小 unified diff。"
                    ),
                )
            if tc and ticket:
                args = tc.arguments
                ticket.log.append(f"工具调用: {tc.name}({json.dumps(args, ensure_ascii=False)})")
                ticket.updated_at = datetime.now(timezone.utc)
                self._persist_tickets()
            return StepDirective(approved=True)

        if step_type == "after_tool_call":
            tc = kwargs.get("tool_call")
            ticket = kwargs.get("ticket")
            result = kwargs.get("result", "")
            tool_result = kwargs.get("tool_result")
            if tool_result:
                for path in getattr(tool_result, "changed_files", []):
                    if path not in self.changed_files:
                        self.changed_files.append(path)
                if getattr(tool_result, "ok", False) and tc:
                    self._record_context_evidence(tc)
            is_error = "[ERROR]" in result or "命令执行失败" in result
            status = "失败" if is_error else "成功"
            if tc and ticket:
                ticket.log.append(f"工具结果 [{status}]: {result[:120]}")
                ticket.updated_at = datetime.now(timezone.utc)
                self._persist_tickets()
            return StepDirective()

        if step_type == "progress_check":
            ticket = kwargs.get("ticket")
            iteration = kwargs.get("iteration", 0)
            desc = ticket.description if ticket else "未知"
            return StepDirective(
                inject_message=(
                    f"【进度检查】请评估你当前的工作进展。\n"
                    f"原始任务: {desc}\n"
                    f"当前是第 {iteration} 次循环。\n"
                    f"如果你的操作偏离了原始任务，请立即回到正题。\n"
                    f"如果任务已完成，请直接输出最终结果，不要再调用工具。"
                )
            )

        return StepDirective()

    def _context_key(self, raw_path: object) -> str | None:
        if not isinstance(raw_path, str) or not raw_path.strip():
            return None
        return Path(self._to_git_paths([raw_path])[0]).as_posix()

    def _record_context_evidence(self, tool_call: ToolCall) -> None:
        if tool_call.name == "read_file":
            key = self._context_key(tool_call.arguments.get("path"))
            if key:
                self.context_files_seen.add(key)
        elif tool_call.name in {"search_files", "search_content"}:
            self.context_search_performed = True

    def _has_edit_context(self, raw_path: object) -> bool:
        key = self._context_key(raw_path)
        if key is None:
            return False
        return self.context_search_performed or key in self.context_files_seen

    def _transition(self, new_state: SupervisorState) -> None:
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"非法状态转换: {self.state.value} -> {new_state.value}")
        self.state = new_state
        self._persist_state()

    def _reset_stale_running_state(self) -> None:
        if self.state != SupervisorState.IDLE:
            self.console.print(
                f"[yellow]检测到上次遗留状态 {self.state.value}，启动新任务前已重置为 idle。[/yellow]"
            )
            self.state = SupervisorState.IDLE
            self._persist_state()

    def _persist_state(self) -> None:
        self.state_manager.save_supervisor_state({
            "state": self.state.value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def _parse_constraints(self, prompt: str) -> TaskConstraints:
        normalized = prompt.lower()
        disallowed: set[str] = set()
        reasons: list[str] = []

        if any(marker in prompt for marker in ("不要读取文件", "不要读文件", "无需读取文件", "不读取文件")):
            disallowed.update({"read_file", "list_dir", "search_files", "search_content"})
            reasons.append("用户要求不要读取文件。")

        if any(marker in prompt for marker in ("不要调用工具", "不调用工具", "不要使用工具", "不使用工具")):
            disallowed.update(
                {
                    "read_file",
                    "write_file",
                    "apply_patch",
                    "list_dir",
                    "run_shell",
                    "search_files",
                    "search_content",
                    "web_search",
                }
            )
            reasons.append("用户要求不要调用工具。")

        if "based on project context" in normalized and "do not read" in normalized:
            disallowed.update({"read_file", "list_dir", "search_files", "search_content"})
            reasons.append("User asked to answer from project context without reading files.")

        return TaskConstraints(disallowed_tools=disallowed, reason=" ".join(reasons))

    def _next_ticket_id(self) -> str:
        self.ticket_counter += 1
        return f"T-{self.ticket_counter:03d}"

    def _path_exists(self, raw_path: object) -> bool:
        if not isinstance(raw_path, str) or not raw_path.strip():
            return False
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.state_manager.project_root / path
        return path.exists()

    def normalize_repl_command(self, user_input: str) -> str:
        stripped = user_input.strip()
        lower = stripped.lower()
        command_aliases = {
            "help": ":help",
            "tickets": ":tickets",
            "status": ":status",
            "trace": ":trace",
            "context": ":context",
            "refresh": ":refresh",
            "verify": ":verify",
            "diff": ":diff",
            "checkpoint": ":checkpoint",
            "ticket": ":ticket",
            "revise": ":revise",
            "continue": ":continue",
            "new": ":new",
        }
        if lower in command_aliases:
            return command_aliases[lower]
        if lower.startswith("/"):
            command_text = stripped[1:].strip()
            command, _, rest = command_text.partition(" ")
            canonical = command_aliases.get(command.lower())
            if not canonical:
                return stripped
            if canonical in {":new", ":ticket", ":revise", ":continue"}:
                return f"{canonical} {rest.strip()}" if rest.strip() else canonical
            return canonical if not rest.strip() else stripped
        return stripped

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
        self.context_files_seen.clear()
        self.context_search_performed = False

    def complete_ticket(self, ticket: Ticket, result: str) -> None:
        ticket.status = "done"
        ticket.result = result
        ticket.updated_at = datetime.now(timezone.utc)
        ticket.log.append("Ticket 完成")
        self._persist_tickets()

    def suggest_verification_command(self) -> str | None:
        for raw_path in self.changed_files:
            path = Path(raw_path)
            if path.suffix != ".py":
                continue

            git_path = self._to_git_paths([raw_path])[0]
            normalized = Path(git_path).as_posix()
            if normalized.startswith("tests/") and Path(normalized).name.startswith("test_"):
                return f"pytest -q {normalized}"

            candidate = self.state_manager.project_root / "tests" / f"test_{path.stem}.py"
            if candidate.exists():
                candidate_path = candidate.relative_to(self.state_manager.project_root).as_posix()
                return f"pytest -q {candidate_path}"

            parts = normalized.split("/")
            if len(parts) > 2 and parts[0] == "src":
                package_candidate = (
                    self.state_manager.project_root
                    / "tests"
                    / Path(*parts[1:-1])
                    / f"test_{path.stem}.py"
                )
                if package_candidate.exists():
                    candidate_path = package_candidate.relative_to(self.state_manager.project_root).as_posix()
                    return f"pytest -q {candidate_path}"

        if any(path.endswith(".py") for path in self.changed_files):
            return "pytest -q"
        project_command = self._suggest_project_verification_command()
        if project_command:
            return project_command
        return None

    def _suggest_project_verification_command(self) -> str | None:
        if self._has_changed_suffix({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}):
            node_command = self._suggest_node_test_command()
            if node_command:
                return node_command

        if self._has_changed_suffix({".go"}) and self._project_file_exists("go.mod"):
            return "go test ./..."

        if self._has_changed_suffix({".rs"}) and self._project_file_exists("Cargo.toml"):
            return "cargo test"

        if self._has_changed_suffix({".java"}) and self._project_file_exists("pom.xml"):
            return "mvn test"

        if self._has_changed_suffix({".java", ".kt", ".kts"}) and (
            self._project_file_exists("build.gradle")
            or self._project_file_exists("build.gradle.kts")
            or self._project_file_exists("gradlew")
            or self._project_file_exists("gradlew.bat")
        ):
            return self._gradle_test_command()

        if self._has_changed_suffix({".cs", ".fs", ".vb"}) and (
            self._project_has_glob("*.sln")
            or self._project_has_glob("*.csproj")
            or self._project_has_glob("**/*.csproj")
        ):
            return "dotnet test"

        return None

    def _suggest_node_test_command(self) -> str | None:
        package_json = self.state_manager.project_root / "package.json"
        if not package_json.exists():
            return None
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        scripts = data.get("scripts")
        if not isinstance(scripts, dict) or not scripts.get("test"):
            return None
        if self._project_file_exists("pnpm-lock.yaml"):
            return "pnpm test"
        if self._project_file_exists("yarn.lock"):
            return "yarn test"
        if self._project_file_exists("bun.lockb"):
            return "bun test"
        if self._project_file_exists("package-lock.json"):
            return "npm test"
        return "npm test"

    def _gradle_test_command(self) -> str:
        if self._project_file_exists("gradlew"):
            return "./gradlew test"
        if self._project_file_exists("gradlew.bat"):
            return "gradlew.bat test"
        return "gradle test"

    def _has_changed_suffix(self, suffixes: set[str]) -> bool:
        return any(Path(path).suffix.lower() in suffixes for path in self.changed_files)

    def _project_file_exists(self, name: str) -> bool:
        return (self.state_manager.project_root / name).exists()

    def _project_has_glob(self, pattern: str) -> bool:
        return any(self.state_manager.project_root.glob(pattern))

    def format_task_summary(self) -> str:
        lines = ["\n\nChanges"]
        if self.changed_files:
            lines.extend(f"- {path}" for path in self.changed_files)
        else:
            lines.append("- none")

        lines.append("")
        lines.append("Tests")

        command = self.suggest_verification_command()
        if command:
            lines.append(f"- Suggested: {command}")
        elif self.changed_files:
            lines.append("- Suggested: manually inspect the changed files")
        else:
            lines.append("- Suggested: not required")

        notes = self.format_trace_summary()
        if len(self.changed_files) > 1:
            notes.append("多文件变更，建议运行 /checkpoint 查看当前 git 状态")
        if notes:
            lines.append("")
            lines.append("Notes")
            lines.extend(f"- {line}" for line in notes)
        return "\n".join(lines)

    def format_structured_output(self, results: list[str], executed_tickets: list[Ticket]) -> str:
        lines = ["Result"]
        if results:
            lines.extend(results)
        else:
            lines.append("（无结果）")

        plan = self.format_plan_summary(executed_tickets)
        if plan:
            lines.append(plan.lstrip())

        lines.append(self.format_task_summary().lstrip())
        return "\n".join(lines)

    def format_plan_summary(self, tasks: list[Ticket]) -> str:
        if len(tasks) <= 1:
            return ""
        lines = ["\n\nPlan"]
        for index, ticket in enumerate(tasks, 1):
            lines.append(f"{index}. {ticket.description}")
        return "\n".join(lines)

    def format_trace_summary(self, max_steps: int = 5) -> list[str]:
        steps = self.worker.last_steps[-max_steps:]
        summary: list[str] = []
        for step in steps:
            parts = [f"loop {step.iteration}"]
            if step.tool_calls:
                tool_names = ", ".join(tc.name for tc in step.tool_calls)
                parts.append(f"tools={tool_names}")
            if step.done_reason:
                parts.append(f"done={step.done_reason}")
            elif step.assistant_content:
                parts.append(f"assistant={_truncate(step.assistant_content, 80)}")
            summary.append("; ".join(parts))
        return summary

    def run_verification(self) -> str:
        command = self.suggest_verification_command()
        if not self.changed_files:
            return "当前没有可验证的变更文件"
        if not command:
            return "当前变更没有自动验证命令，请手动检查相关文件"

        tc = ToolCall(
            id="verify",
            name="run_shell",
            arguments={
                "command": command,
                "cwd": str(self.state_manager.project_root),
            },
        )
        result = self.harness.execute_tool_call_structured(tc)
        status = "通过" if result.ok else "失败"
        output = result.stdout or result.text
        return f"验证命令: {command}\n验证结果: {status}\n{output}"

    def format_diff(self) -> str:
        paths = self.changed_files or None
        diff_text = self._git_diff(paths)
        if paths:
            untracked_diffs = self._format_untracked_changed_files(paths)
            if untracked_diffs:
                diff_text = "\n".join(part for part in [diff_text, "\n".join(untracked_diffs)] if part)
        if diff_text.strip():
            return diff_text
        scope = "本轮变更文件" if paths else "当前工作区"
        return f"{scope}没有可显示的 git diff"

    def format_checkpoint(self) -> str:
        inside_result = self._run_git(["git", "rev-parse", "--is-inside-work-tree"])
        branch_result = self._run_git(["git", "branch", "--show-current"])
        head_result = self._run_git(["git", "rev-parse", "--short", "HEAD"])
        status_result = self._run_git(["git", "status", "--short"])
        if (
            inside_result.returncode != 0
            or (inside_result.stdout or "").strip().lower() != "true"
            or branch_result.returncode != 0
            or status_result.returncode != 0
        ):
            return "当前目录不是可读取的 git 仓库，无法生成 checkpoint 状态"

        branch = (branch_result.stdout or "").strip() or "detached"
        head = (head_result.stdout or "").strip() if head_result.returncode == 0 else "unknown"
        status_lines = [line for line in (status_result.stdout or "").splitlines() if line.strip()]
        lines = [
            "Checkpoint",
            f"- 分支: {branch}",
            f"- HEAD: {head}",
            f"- 工作区: {'干净' if not status_lines else f'有 {len(status_lines)} 项变更'}",
        ]
        if status_lines:
            lines.append("变更:")
            lines.extend(f"- {line}" for line in status_lines[:20])
            if len(status_lines) > 20:
                lines.append(f"- ... 还有 {len(status_lines) - 20} 项")
        return "\n".join(lines)

    def _git_diff(self, paths: list[str] | None = None) -> str:
        command = ["git", "diff"]
        if paths:
            command.append("--")
            command.extend(self._to_git_paths(paths))
        result = self._run_git(command)
        if result.returncode != 0:
            return ""
        return result.stdout or ""

    def _run_git(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.state_manager.project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def _to_git_paths(self, paths: list[str]) -> list[str]:
        root = self.state_manager.project_root.resolve()
        result: list[str] = []
        for raw_path in paths:
            path = Path(raw_path)
            if not path.is_absolute():
                result.append(raw_path)
                continue
            try:
                result.append(str(path.resolve().relative_to(root)))
            except ValueError:
                result.append(str(path))
        return result

    def _format_untracked_changed_files(self, paths: list[str]) -> list[str]:
        root = self.state_manager.project_root.resolve()
        diffs: list[str] = []
        for git_path in self._to_git_paths(paths):
            path = root / git_path
            if not path.exists() or not path.is_file() or self._is_git_tracked(git_path):
                continue
            try:
                content = path.read_text(encoding="utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                diffs.append(f"diff --git a/{git_path} b/{git_path}\n新增二进制或非 UTF-8 文件，无法显示文本 diff。\n")
                continue
            diffs.append(
                "".join(
                    difflib.unified_diff(
                        [],
                        content,
                        fromfile="/dev/null",
                        tofile=f"b/{git_path}",
                    )
                )
            )
        return diffs

    def _is_git_tracked(self, git_path: str) -> bool:
        result = self._run_git(["git", "ls-files", "--error-unmatch", "--", git_path])
        return result.returncode == 0

    def list_tickets(self) -> str:
        if not self.tickets:
            return "当前没有 Ticket"
        status_order = ["pending", "running", "blocked", "done", "failed", "cancelled"]
        counts = {status: 0 for status in status_order}
        for ticket in self.tickets:
            counts[ticket.status] = counts.get(ticket.status, 0) + 1
        summary = "汇总: " + ", ".join(f"{status}={counts[status]}" for status in status_order)
        lines = [summary]
        for ticket in self.tickets:
            lines.append(f"{ticket.ticket_id} ({ticket.status}) - {ticket.description}")
        return "\n".join(lines)

    def find_ticket(self, ticket_id: str) -> Ticket | None:
        normalized = ticket_id.strip().upper()
        for ticket in self.tickets:
            if ticket.ticket_id.upper() == normalized:
                return ticket
        return None

    def format_ticket_detail(self, ticket_id: str) -> str:
        ticket = self.find_ticket(ticket_id)
        if ticket is None:
            return f"未找到 Ticket: {ticket_id}"

        lines = [
            f"Ticket: {ticket.ticket_id}",
            f"状态: {ticket.status}",
            f"描述: {ticket.description}",
        ]
        if ticket.parent_ticket_id:
            lines.append(f"父 Ticket: {ticket.parent_ticket_id}")
        if ticket.acceptance_criteria:
            lines.append(f"验收标准: {ticket.acceptance_criteria}")
        if ticket.result:
            lines.append(f"结果: {_truncate(ticket.result, 500)}")
        logs = ticket.log[-10:]
        if logs:
            lines.append("日志:")
            lines.extend(f"- {item}" for item in logs)
        return "\n".join(lines)

    def revise_ticket(self, ticket_id: str, description: str) -> str:
        ticket = self.find_ticket(ticket_id)
        if ticket is None:
            return f"未找到 Ticket: {ticket_id}"
        if ticket.status not in {"pending", "blocked", "failed"}:
            return f"Ticket {ticket.ticket_id} 当前状态为 {ticket.status}，不能修改描述"
        new_description = description.strip()
        if not new_description:
            return "请提供新的 Ticket 描述"
        old_description = ticket.description
        ticket.description = new_description
        if ticket.status in {"blocked", "failed"}:
            ticket.status = "pending"
        ticket.updated_at = datetime.now(timezone.utc)
        ticket.log.append(f"Ticket 描述已修改: {old_description} -> {new_description}")
        self._persist_tickets()
        return f"已修改 {ticket.ticket_id}: {new_description}"

    def next_resumable_ticket(self) -> Ticket | None:
        for ticket in self.tickets:
            if ticket.status in {"pending", "blocked", "failed"}:
                return ticket
        return None

    def _prepare_resumable_ticket(self, ticket: Ticket) -> str | None:
        if ticket.status == "done":
            return f"Ticket {ticket.ticket_id} 已完成，不能继续执行"
        if ticket.status == "cancelled":
            return f"Ticket {ticket.ticket_id} 已取消，不能继续执行"
        if ticket.status == "running":
            return f"Ticket {ticket.ticket_id} 正在执行，不能重复启动"
        if ticket.status in {"blocked", "failed"}:
            ticket.status = "pending"
            ticket.updated_at = datetime.now(timezone.utc)
            ticket.log.append("Ticket 已切回 pending，准备继续执行")
            self._persist_tickets()
        return None

    def run_existing_ticket(self, ticket: Ticket, model: str = "deepseek-v4-flash") -> str:
        self._reset_stale_running_state()
        self.current_constraints = self._parse_constraints(ticket.description)
        self.changed_files = []
        try:
            self._transition(SupervisorState.PLANNING)
            self._transition(SupervisorState.DISPATCHING)
            self.start_ticket(ticket)
            self._transition(SupervisorState.WAITING_WORKER)
            response = self.worker.execute_ticket(ticket, model=model, on_step=self._worker_on_step)
            result = f"[{ticket.ticket_id}] {response}"
            self._transition(SupervisorState.REVIEWING)
            final_result = self.format_structured_output([result], [ticket])
            self.memory.record_decision("final_result", _truncate(final_result, 240))
            self.complete_ticket(ticket, final_result)
            self.state_manager.save_audit_log(self.worker.harness.audit_log)
            self._transition(SupervisorState.COMPLETE)
            return final_result
        except Exception:
            ticket.status = "failed"
            ticket.updated_at = datetime.now(timezone.utc)
            ticket.log.append("Ticket 继续执行失败")
            self._persist_tickets()
            try:
                self._transition(SupervisorState.FAILED)
            except ValueError:
                pass
            raise
        finally:
            self.current_constraints = TaskConstraints(disallowed_tools=set())
            if self.state != SupervisorState.IDLE:
                try:
                    self._transition(SupervisorState.IDLE)
                except ValueError:
                    self.state = SupervisorState.IDLE

    def continue_ticket(self, ticket_id: str | None = None, model: str = "deepseek-v4-flash") -> str:
        ticket = self.find_ticket(ticket_id) if ticket_id else self.next_resumable_ticket()
        if ticket_id and ticket is None:
            return f"未找到 Ticket: {ticket_id}"
        if ticket is None:
            return "当前没有可继续执行的 Ticket"
        error = self._prepare_resumable_ticket(ticket)
        if error:
            return error
        return self.run_existing_ticket(ticket, model=model)

    def continue_next_ticket(self, model: str = "deepseek-v4-flash") -> str:
        return self.continue_ticket(model=model)

    def cancel_pending_tickets(self, tickets: list[Ticket], reason: str = "") -> None:
        note = reason.strip() or "调度器判断无需继续执行"
        now = datetime.now(timezone.utc)
        for ticket in tickets:
            if ticket.status != "pending":
                continue
            ticket.status = "cancelled"
            ticket.updated_at = now
            ticket.log.append(f"Ticket 已取消: {note}")
        if tickets:
            self._persist_tickets()

    def refresh_project_context(self) -> str:
        context = RepoMapBuilder(self.state_manager.project_root).build().to_prompt()
        self.memory.set_project_context(context)
        return context

    def format_context(self) -> str:
        if not self.memory.project_context:
            return "当前没有项目上下文"
        return self.memory.project_context

    def format_status(self) -> str:
        if not self.current_ticket:
            return "当前没有正在运行的 Ticket"
        t = self.current_ticket
        logs = "\n".join(t.log) if t.log else "（无日志）"
        return f"当前 Ticket: {t.ticket_id} ({t.status})\n描述: {t.description}\n日志:\n{logs}"

    def format_trace(self) -> str:
        steps = self.worker.last_steps
        if not steps:
            return "当前没有可显示的执行轨迹"

        lines = [f"执行轨迹：{len(steps)} 轮"]
        for step in steps:
            suffix = f"，结束原因: {step.done_reason}" if step.done_reason else ""
            lines.append(f"\n# 循环 {step.iteration} / Ticket {step.ticket_id}{suffix}")
            if step.injected_messages:
                for msg in step.injected_messages:
                    lines.append(f"注入消息: {_truncate(msg, 160)}")
            if step.assistant_content:
                lines.append(f"LLM 输出: {_truncate(step.assistant_content, 240)}")
            if step.tool_calls:
                for index, tc in enumerate(step.tool_calls, 1):
                    args = json.dumps(tc.arguments, ensure_ascii=False)
                    lines.append(f"工具调用 {index}: {tc.name}({args})")
            if step.tool_results:
                for index, result in enumerate(step.tool_results, 1):
                    status = "成功" if result.ok else "失败"
                    lines.append(f"工具结果 {index} [{status}]: {_truncate(result.text, 240)}")
            if not step.assistant_content and not step.tool_calls and not step.injected_messages:
                lines.append("（本轮无可显示内容）")
        return "\n".join(lines)

    def start_repl(self, model: str = "deepseek-v4-flash") -> None:
        self.console.print("[green]输入 exit 或 quit 退出会话。[/green]")
        self.console.print("[green]输入 /tickets 查看当前 Ticket 列表。[/green]")
        self.console.print("[green]可用命令: /help, /tickets, /ticket <id>, /status, /trace, /context, /refresh, /diff, /verify, /checkpoint, /revise <id> <描述>, /continue, /new <描述>, exit[/green]")
        while True:
            user_input = self.normalize_repl_command(Prompt.ask("[bold cyan]DeepSeek>[/bold cyan]"))
            if user_input.lower() in {"exit", "quit"}:
                break
            if user_input == ":help":
                self.console.print(
                    "/help - 显示帮助\n/tickets - 列出 Ticket\n/ticket <id> - 查看指定 Ticket 详情\n/status - 当前 Ticket 状态\n/trace - 最近一次执行轨迹\n/context - 当前项目上下文\n/refresh - 刷新项目上下文\n/diff - 查看当前变更 diff\n/verify - 运行最近一次建议验证命令\n/checkpoint - 查看当前 git 分支、HEAD 和工作区变更概况\n/revise <id> <描述> - 修改 pending/blocked/failed Ticket\n/continue - 继续执行下一个未完成 Ticket\n/new <描述> - 创建并执行新 Ticket\nexit - 退出"
                )
                continue
            if user_input == ":tickets":
                self.console.print(self.list_tickets())
                continue
            if user_input.startswith(":ticket "):
                ticket_id = user_input[8:].strip()
                if not ticket_id:
                    self.console.print("请提供 Ticket ID，例如: /ticket T-001")
                    continue
                self.console.print(self.format_ticket_detail(ticket_id))
                continue
            if user_input.startswith(":revise "):
                payload = user_input[8:].strip()
                ticket_id, _, description = payload.partition(" ")
                if not ticket_id or not description.strip():
                    self.console.print("请提供 Ticket ID 和新描述，例如: /revise T-001 修复 auth.ts")
                    continue
                self.console.print(self.revise_ticket(ticket_id, description))
                continue
            if user_input == ":continue" or user_input.startswith(":continue "):
                ticket_id = user_input[10:].strip() if user_input.startswith(":continue ") else None
                try:
                    self.console.print(self.continue_ticket(ticket_id, model=model))
                except Exception as e:
                    self.console.print(f"[red]继续执行出错: {e}[/red]")
                continue
            if user_input == ":status":
                self.console.print(self.format_status())
                continue
            if user_input == ":trace":
                self.console.print(self.format_trace())
                continue
            if user_input == ":context":
                self.console.print(self.format_context())
                continue
            if user_input == ":refresh":
                self.refresh_project_context()
                self.console.print("[green]项目上下文已刷新[/green]")
                continue
            if user_input == ":verify":
                self.console.print(self.run_verification())
                continue
            if user_input == ":diff":
                self.console.print(self.format_diff())
                continue
            if user_input == ":checkpoint":
                self.console.print(self.format_checkpoint())
                continue
            if user_input.startswith(":new "):
                desc = user_input[5:].strip()
                if not desc:
                    self.console.print("请提供任务描述，例如: /new 修复 auth.ts")
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

    def _should_skip_planning(self, prompt: str) -> bool:
        normalized = prompt.lower()
        edit_markers = ("修改", "改成", "替换", "rename", "change", "update", "replace")
        file_markers = (".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".json", ".toml", ".yaml", ".yml", ".txt")
        complex_markers = ("多个", "所有", "整个项目", "架构", "重构", "规划", "分析并", "生成测试", "运行测试")
        return (
            any(marker in normalized for marker in edit_markers)
            and any(marker in normalized for marker in file_markers)
            and not any(marker in normalized for marker in complex_markers)
        )

    def _create_child_ticket(self, parent: Ticket, task_dict: dict[str, str]) -> Ticket:
        child = self.create_ticket(task_dict["description"])
        child.parent_ticket_id = parent.ticket_id
        if "acceptance_criteria" in task_dict:
            child.acceptance_criteria = task_dict["acceptance_criteria"]
        return child

    def _parse_evaluation(self, text: str) -> EvaluationAction:
        cleaned = text.strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            return EvaluationAction(action="continue")
        try:
            data = json.loads(cleaned[start:end + 1])
            action = data.get("action", "continue")
            return EvaluationAction(
                action=action,
                reason=data.get("reason", ""),
                new_tasks=data.get("new_tasks"),
            )
        except (json.JSONDecodeError, TypeError):
            return EvaluationAction(action="continue")

    def _evaluate_ticket(
        self,
        ticket: Ticket,
        result: str,
        pending_tickets: List[Ticket],
        original_prompt: str,
    ) -> EvaluationAction:
        review_messages = [
            {
                "role": "system",
                "content": (
                    "你是一个任务调度助手。根据已完成的子任务结果，决定下一步行动。\n"
                    "可选动作:\n"
                    "- continue: 继续执行下一个子任务\n"
                    "- re_plan: 重新规划剩余工作（说明原因）\n"
                    "- skip_remaining: 当前结果已满足原始目标，跳过剩余任务\n"
                    "- add_tasks: 需要追加新的子任务（附 JSON 数组）\n"
                    '仅回复 JSON: {"action": "continue"} 或 {"action": "re_plan", "reason": "..."} '
                    '或 {"action": "skip_remaining", "reason": "..."} '
                    '或 {"action": "add_tasks", "new_tasks": [{"description": "..."}]}\n'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"原始目标: {original_prompt}\n"
                    f"已完成任务 [{ticket.ticket_id}]: {ticket.description}\n"
                    f"结果: {result[:500]}\n"
                    f"待执行任务: {[t.description for t in pending_tickets]}\n"
                ),
            },
        ]
        response = self.llm_service.chat(messages=review_messages)
        return self._parse_evaluation(response.content or "")

    def handle_prompt(self, prompt: str, model: str = "deepseek-v4-flash") -> str:
        try:
            self._reset_stale_running_state()
            self.current_constraints = self._parse_constraints(prompt)
            self.changed_files = []
            self._transition(SupervisorState.PLANNING)
            parent_ticket = self.create_ticket(prompt)

            sub_tasks = [] if self._should_skip_planning(prompt) else self.plan_task(prompt, model)
            if len(sub_tasks) > 1:
                child_tickets = [self._create_child_ticket(parent_ticket, t) for t in sub_tasks]
            else:
                child_tickets = [parent_ticket]
            if len(child_tickets) > 1:
                self.memory.record_decision(
                    "plan",
                    " -> ".join(ticket.description for ticket in child_tickets),
                )

            pending = list(child_tickets)
            executed_tickets: list[Ticket] = []
            results = []
            supervisor_iteration = 0

            while pending and supervisor_iteration < MAX_SUPERVISOR_ITERATIONS:
                supervisor_iteration += 1
                ticket = pending.pop(0)
                executed_tickets.append(ticket)

                self._transition(SupervisorState.DISPATCHING)
                self.start_ticket(ticket)

                self._transition(SupervisorState.WAITING_WORKER)
                if results:
                    self.memory.clear_working()
                    self.memory.append_system(
                        f"之前任务的结果（供参考）：\n" + "\n".join(results[-3:])
                    )
                response = self.worker.execute_ticket(ticket, model=model, on_step=self._worker_on_step)
                results.append(f"[{ticket.ticket_id}] {response}")

                if pending:
                    eval_action = self._evaluate_ticket(ticket, response, pending, prompt)

                    if eval_action.action == "skip_remaining":
                        parent_ticket.log.append(f"跳过剩余任务: {eval_action.reason}")
                        self.memory.record_decision("skip_remaining", eval_action.reason)
                        self.cancel_pending_tickets(pending, eval_action.reason)
                        pending.clear()

                    elif eval_action.action == "add_tasks" and eval_action.new_tasks:
                        for t in eval_action.new_tasks:
                            new_ticket = self._create_child_ticket(parent_ticket, t)
                            pending.append(new_ticket)
                        parent_ticket.log.append(f"追加 {len(eval_action.new_tasks)} 个新任务")
                        self.memory.record_decision(
                            "add_tasks",
                            ", ".join(str(t.get("description", "")) for t in eval_action.new_tasks),
                        )

                    elif eval_action.action == "re_plan":
                        parent_ticket.log.append(f"重新规划: {eval_action.reason}")
                        self.memory.record_decision("re_plan", eval_action.reason)
                        pending.clear()
                        new_plan = self.plan_task(eval_action.reason, model)
                        if new_plan:
                            for t in new_plan:
                                new_ticket = self._create_child_ticket(parent_ticket, t)
                                pending.append(new_ticket)

            if supervisor_iteration >= MAX_SUPERVISOR_ITERATIONS:
                parent_ticket.log.append(f"达到 Supervisor 最大循环次数 {MAX_SUPERVISOR_ITERATIONS}")

            self._transition(SupervisorState.REVIEWING)
            final_result = self.format_structured_output(results, executed_tickets)
            self.memory.record_decision("final_result", _truncate(final_result, 240))
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
            self.current_constraints = TaskConstraints(disallowed_tools=set())
            if self.state != SupervisorState.IDLE:
                try:
                    self._transition(SupervisorState.IDLE)
                except ValueError:
                    self.state = SupervisorState.IDLE

    def _load_state(self) -> None:
        raw_tickets = self.state_manager.load_tickets()
        recovered_running_tickets = False
        for raw in raw_tickets:
            ticket = Ticket(**raw)
            if ticket.status == "running":
                ticket.status = "blocked"
                ticket.updated_at = datetime.now(timezone.utc)
                ticket.log.append("检测到上次中断的 running Ticket，已标记为 blocked，可用 /continue 继续执行")
                recovered_running_tickets = True
            self.tickets.append(ticket)
        self.ticket_counter = len(self.tickets)
        if recovered_running_tickets:
            self._persist_tickets()
        state_data = self.state_manager.load_supervisor_state()
        if state_data:
            self.state = SupervisorState(state_data.get("state", "idle"))

    def _persist_tickets(self) -> None:
        self.state_manager.save_tickets([ticket.model_dump() for ticket in self.tickets])
