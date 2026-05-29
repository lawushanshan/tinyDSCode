from __future__ import annotations
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.prompt import Confirm

from .tools import ToolRegistry
from .llm_service import ToolCall
from .persistence import StateManager


class ToolResult(BaseModel):
    tool: str
    ok: bool
    text: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    changed_files: list[str] = Field(default_factory=list)


class Harness:
    DEFAULT_SHELL_TIMEOUT_SECONDS = 30
    MAX_SHELL_TIMEOUT_SECONDS = 300

    def __init__(
        self,
        state_root: str | None = None,
        tool_registry: ToolRegistry | None = None,
        interactive: bool = False,
    ) -> None:
        self.audit_log: list[dict[str, Any]] = []
        self.state_manager = StateManager(root=state_root)
        self.console = Console()
        self.tool_registry = tool_registry
        self.interactive = interactive
        self.allowed_actions = {
            "file": True,
            "shell": not interactive,
        }

    def assess_shell_risk(self, command: str) -> tuple[str, list[str]]:
        normalized = command.lower()
        reasons: list[str] = []

        destructive_patterns = (
            r"\brm\s+.*(-r|-f|/)",
            r"\bdel\s+",
            r"\berase\s+",
            r"\brmdir\s+",
            r"\brd\s+",
            r"\bremove-item\b",
            r"\bgit\s+reset\b",
            r"\bgit\s+clean\b",
            r"\bgit\s+restore\b",
            r"\bgit\s+checkout\s+(?:--|\.)",
            r"\bformat\b",
        )
        network_patterns = (
            r"\bcurl\b",
            r"\bwget\b",
            r"\binvoke-webrequest\b",
            r"\binvoke-restmethod\b",
            r"\bssh\b",
            r"\bscp\b",
            r"\bgit\s+(?:pull|push|fetch|clone)\b",
        )
        install_patterns = (
            r"\bnpm\s+install\b",
            r"\bnpm\s+ci\b",
            r"\byarn\s+(?:add|install)\b",
            r"\bpnpm\s+(?:add|install)\b",
            r"\bbun\s+(?:add|install)\b",
            r"\bpip\s+install\b",
            r"\bpip\s+uninstall\b",
            r"\buv\s+sync\b",
            r"\buv\s+add\b",
            r"\bpoetry\s+install\b",
            r"\bpoetry\s+add\b",
            r"\bcargo\s+install\b",
            r"\bcargo\s+update\b",
        )
        long_running_patterns = (
            r"\bnpm\s+run\s+dev\b",
            r"\bpnpm\s+dev\b",
            r"\byarn\s+dev\b",
            r"\bbun\s+dev\b",
            r"\bnext\s+dev\b",
            r"\bvite\b",
            r"\buvicorn\b",
            r"\bgunicorn\b",
            r"\bflask\s+run\b",
            r"\bpython\s+-m\s+http\.server\b",
            r"\bdocker\s+compose\s+up\b",
        )

        for pattern in destructive_patterns:
            if re.search(pattern, normalized):
                reasons.append("可能删除文件、重置代码或破坏工作区")
                break
        for pattern in network_patterns:
            if re.search(pattern, normalized):
                reasons.append("可能访问网络或远程主机")
                break
        for pattern in install_patterns:
            if re.search(pattern, normalized):
                reasons.append("可能安装依赖或修改环境")
                break
        for pattern in long_running_patterns:
            if re.search(pattern, normalized):
                reasons.append("可能启动长时间运行的进程或开发服务器")
                break
        if re.search(r"\b(setx|export)\b", normalized):
            reasons.append("可能修改环境变量")
        if re.search(r"(^|[^<])>>?($|[^>])", command):
            reasons.append("可能通过 shell 重定向写入文件")
        if any(operator in command for operator in ("|", "&&", "||", ";")):
            reasons.append("包含管道或多段命令，实际执行范围更大")

        if any("删除" in reason or "重置" in reason or "破坏" in reason for reason in reasons):
            return "high", reasons
        if reasons:
            return "medium", reasons
        return "low", ["未检测到明显高风险操作"]

    def request_permission(self, action: str, detail: str = "", cwd: str | None = None) -> bool:
        if self.allowed_actions.get(action, False):
            return True
        label = action
        if detail:
            label = f"{action}: {detail}"
        if action == "shell":
            risk, reasons = self.assess_shell_risk(detail)
            self.console.print(f"[yellow]需要人工确认以执行 shell 命令[/yellow]")
            self.console.print(f"[bold]风险等级:[/bold] {risk}")
            self.console.print(f"[bold]原因:[/bold] {'；'.join(reasons)}")
            if cwd:
                self.console.print(f"[bold]工作目录:[/bold] {cwd}")
            self.console.print(f"[bold]命令:[/bold] {detail}")
        else:
            self.console.print(f"[yellow]需要人工确认以执行 {label}[/yellow]")
        result = Confirm.ask(f"是否允许执行？")
        entry = {
            "action": "permission_request",
            "operation": action,
            "detail": detail,
            "approval": result,
            "outcome": "approved" if result else "denied",
        }
        if cwd:
            entry["cwd"] = cwd
        if action == "shell":
            risk, reasons = self.assess_shell_risk(detail)
            entry["risk"] = risk
            entry["risk_reasons"] = reasons
        self.audit_log.append(entry)
        self.state_manager.save_audit_log(self.audit_log)
        return result

    def execute_tool_call_structured(self, tool_call: ToolCall) -> ToolResult:
        tool_name = tool_call.name
        args = tool_call.arguments
        call_entry = {
            "action": "tool_call",
            "tool": tool_name,
            "arguments": args,
        }
        if tool_name == "run_shell":
            command = str(args.get("command", ""))
            risk, reasons = self.assess_shell_risk(command)
            call_entry["risk"] = risk
            call_entry["risk_reasons"] = reasons
        self.audit_log.append(call_entry)
        self.state_manager.save_audit_log(self.audit_log)
        try:
            result = self.perform_action(action=tool_name, **args)
            result_text = str(result) if result is not None else "（无返回值）"
        except Exception as exc:
            result_text = f"[ERROR] {type(exc).__name__}: {exc}"
            structured = ToolResult(
                tool=tool_name,
                ok=False,
                text=result_text,
                arguments=args,
                error=result_text,
            )
            self.audit_log.append({
                "action": "tool_error",
                "tool": tool_name,
                "error": result_text,
                "structured": structured.model_dump(),
            })
            self.state_manager.save_audit_log(self.audit_log)
            return structured

        structured = self._build_tool_result(tool_name, args, result_text)

        self.audit_log.append({
            "action": "tool_result",
            "tool": tool_name,
            "result": result_text,
            "structured": structured.model_dump(),
        })
        self.state_manager.save_audit_log(self.audit_log)
        return structured

    def execute_tool_call(self, tool_call: ToolCall) -> str:
        return self.execute_tool_call_structured(tool_call).text

    def _resolve_project_path(self, raw_path: str) -> str:
        path = Path(raw_path)
        root = self.state_manager.project_root.resolve()
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise PermissionError(f"路径超出项目根目录: {raw_path}") from exc
        return str(resolved)

    def _normalize_timeout_seconds(self, value: Any) -> int:
        try:
            timeout = int(value)
        except (TypeError, ValueError):
            return self.DEFAULT_SHELL_TIMEOUT_SECONDS
        if timeout <= 0:
            return self.DEFAULT_SHELL_TIMEOUT_SECONDS
        return min(timeout, self.MAX_SHELL_TIMEOUT_SECONDS)

    def _to_project_relative_path(self, raw_path: str) -> str:
        path = Path(raw_path)
        root = self.state_manager.project_root.resolve()
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            return raw_path

    def _build_tool_result(self, tool_name: str, args: dict[str, Any], result_text: str) -> ToolResult:
        ok = not (
            result_text.startswith("[命令执行失败")
            or result_text.startswith("[命令执行超时")
            or result_text.startswith("[ERROR]")
            or result_text.startswith("[搜索失败]")
        )
        changed_files: list[str] = []
        if ok and tool_name in {"write_file", "apply_patch"}:
            path = args.get("path")
            if isinstance(path, str):
                changed_files.append(self._to_project_relative_path(path))

        exit_code = None
        stdout = ""
        stderr = ""
        error = None
        if tool_name == "run_shell":
            failure_match = re.match(
                r"\[命令执行失败 \(退出码 (?P<code>-?\d+)\)\].*?\nstdout:\n(?P<stdout>.*?)\nstderr:\n(?P<stderr>.*)",
                result_text,
                re.DOTALL,
            )
            timeout_match = re.match(
                r"\[命令执行超时 \((?P<seconds>\d+)s\)\].*?\nstdout:\n(?P<stdout>.*?)\nstderr:\n(?P<stderr>.*)",
                result_text,
                re.DOTALL,
            )
            if failure_match:
                exit_code = int(failure_match.group("code"))
                stdout = failure_match.group("stdout")
                stderr = failure_match.group("stderr")
                error = result_text
            elif timeout_match:
                exit_code = -1
                stdout = timeout_match.group("stdout")
                stderr = timeout_match.group("stderr")
                error = result_text
            elif ok:
                stdout = result_text
                exit_code = 0

        if not ok and error is None:
            error = result_text

        return ToolResult(
            tool=tool_name,
            ok=ok,
            text=result_text,
            arguments=args,
            error=error,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            changed_files=changed_files,
        )

    def perform_action(
        self,
        action: str,
        path: str | None = None,
        content: str | None = None,
        command: str | None = None,
        cwd: str | None = None,
        patch_text: str | None = None,
        pattern: str | None = None,
        include: str | None = None,
        exclude: str | None = None,
        exclude_patterns: str | None = None,
        context_lines: int = 0,
        query: str | None = None,
        count: int = 5,
        timeout_seconds: int = 30,
    ) -> str | None:
        if action == "read_file":
            if path is None:
                raise ValueError("read_file 需要 path")
            if not self.request_permission("file", detail=f"读取 {path}"):
                raise PermissionError("已拒绝文件读取权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path)
            content = Tools.read_file(resolved_path)
            if not content:
                return f"（文件为空）{path}"
            return content

        if action == "write_file":
            if path is None or content is None:
                raise ValueError("write_file 需要 path 和 content")
            if not self.request_permission("file", detail=f"写入 {path}"):
                raise PermissionError("已拒绝文件写入权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path)
            if Path(resolved_path).exists():
                raise FileExistsError(f"目标文件已存在: {path}。修改已有文件请使用 apply_patch")
            Tools.write_file(resolved_path, content)
            return f"已写入 {path}"

        if action == "list_dir":
            if path is None:
                raise ValueError("list_dir 需要 path")
            if not self.request_permission("file", detail=f"列出 {path}"):
                raise PermissionError("已拒绝目录读取权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path)
            entries = Tools.list_dir(resolved_path)
            if not entries:
                return f"目录为空: {path}"
            return "\n".join(entries)

        if action == "run_shell":
            if command is None:
                raise ValueError("run_shell 需要 command")
            resolved_cwd = self._resolve_project_path(cwd or ".")
            if not self.request_permission("shell", detail=command, cwd=resolved_cwd):
                raise PermissionError("已拒绝 shell 执行权限")
            from .tools import Tools
            timeout = self._normalize_timeout_seconds(timeout_seconds)
            return Tools.run_shell(command=command, cwd=resolved_cwd, timeout_seconds=timeout)

        if action == "apply_patch":
            if path is None or patch_text is None:
                raise ValueError("apply_patch 需要 path 和 patch_text")
            if not self.request_permission("file", detail=f"补丁 {path}"):
                raise PermissionError("已拒绝文件写入权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path)
            Tools.apply_patch(resolved_path, patch_text)
            return f"已应用补丁到 {path}"

        if action == "search_files":
            if pattern is None:
                raise ValueError("search_files 需要 pattern")
            if not self.request_permission("file", detail=f"搜索文件 {pattern}"):
                raise PermissionError("已拒绝文件搜索权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path or ".")
            return Tools.search_files(pattern, resolved_path, exclude_patterns.split(",") if exclude_patterns else None)

        if action == "search_content":
            if pattern is None:
                raise ValueError("search_content 需要 pattern")
            if not self.request_permission("file", detail=f"搜索内容 '{pattern}'"):
                raise PermissionError("已拒绝内容搜索权限")
            from .tools import Tools
            resolved_path = self._resolve_project_path(path or ".")
            return Tools.search_content(pattern, resolved_path, include, exclude, context_lines)

        if action == "web_search":
            if query is None:
                raise ValueError("web_search 需要 query")
            if not self.request_permission("file", detail=f"搜索 '{query}'"):
                raise PermissionError("已拒绝联网搜索权限")
            from .web_search import web_search
            return web_search(query, count)

        raise ValueError(f"未知操作: {action}")

    def log(self, message: str) -> None:
        self.audit_log.append({"action": "log", "message": message})
        self.state_manager.save_audit_log(self.audit_log)
