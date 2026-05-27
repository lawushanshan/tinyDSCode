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

    def request_permission(self, action: str, detail: str = "") -> bool:
        if self.allowed_actions.get(action, False):
            return True
        label = action
        if detail:
            label = f"{action}: {detail}"
        self.console.print(f"[yellow]需要人工确认以执行 {label}[/yellow]")
        result = Confirm.ask(f"是否允许执行？")
        self.audit_log.append({"action": "permission_request", "operation": action, "detail": detail, "approval": result})
        self.state_manager.save_audit_log(self.audit_log)
        return result

    def execute_tool_call_structured(self, tool_call: ToolCall) -> ToolResult:
        tool_name = tool_call.name
        args = tool_call.arguments
        self.audit_log.append({
            "action": "tool_call",
            "tool": tool_name,
            "arguments": args,
        })
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
        if path.is_absolute():
            return str(path)
        return str(self.state_manager.project_root / path)

    def _build_tool_result(self, tool_name: str, args: dict[str, Any], result_text: str) -> ToolResult:
        ok = not (
            result_text.startswith("[命令执行失败")
            or result_text.startswith("[ERROR]")
            or result_text.startswith("[搜索失败]")
        )
        changed_files: list[str] = []
        if ok and tool_name in {"write_file", "apply_patch"}:
            path = args.get("path")
            if isinstance(path, str):
                changed_files.append(path)

        exit_code = None
        stdout = ""
        stderr = ""
        error = None
        if tool_name == "run_shell":
            match = re.match(
                r"\[命令执行失败 \(退出码 (?P<code>-?\d+)\)\].*?\nstdout:\n(?P<stdout>.*?)\nstderr:\n(?P<stderr>.*)",
                result_text,
                re.DOTALL,
            )
            if match:
                exit_code = int(match.group("code"))
                stdout = match.group("stdout")
                stderr = match.group("stderr")
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
            if not self.request_permission("shell", detail=command):
                raise PermissionError("已拒绝 shell 执行权限")
            from .tools import Tools
            resolved_cwd = self._resolve_project_path(cwd or ".")
            return Tools.run_shell(command=command, cwd=resolved_cwd)

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
