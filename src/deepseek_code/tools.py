from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel


class ToolParam(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


class ToolDef(BaseModel):
    name: str
    description: str
    parameters: list[ToolParam]
    handler: Callable[..., Any]

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def to_openai_schema(self) -> list[dict[str, Any]]:
        result = []
        for tool in self._tools.values():
            props = {}
            required = []
            for p in tool.parameters:
                props[p.name] = {"type": p.type, "description": p.description}
                if p.required:
                    required.append(p.name)
            result.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            })
        return result


class Tools:
    @staticmethod
    def read_file(path: str) -> str:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        return file_path.read_text(encoding="utf-8")

    @staticmethod
    def write_file(path: str, content: str) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    @staticmethod
    def list_dir(path: str) -> list[str]:
        directory = Path(path)
        if not directory.exists():
            raise FileNotFoundError(f"路径不存在: {path}")
        return [str(child) for child in directory.iterdir()]

    @staticmethod
    def run_shell(command: str, cwd: str | None = None, timeout_seconds: int = 30) -> str:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            return (
                f"[命令执行超时 ({timeout_seconds}s)] {command}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        if result.returncode != 0:
            return f"[命令执行失败 (退出码 {result.returncode})] {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        if result.stdout:
            return result.stdout
        return f"[命令执行成功] {command}"

    @staticmethod
    def apply_patch(path: str, patch_text: str) -> None:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        patched_lines: list[str] = []
        patch_lines = patch_text.splitlines(keepends=False)
        line_index = 0
        pos = 0
        hunks_applied = 0

        def line_body(line: str) -> str:
            if line.endswith("\n"):
                line = line[:-1]
            if line.endswith("\r"):
                line = line[:-1]
            return line

        def expect_original(expected: str, kind: str) -> str:
            nonlocal line_index
            if line_index >= len(original_lines):
                raise ValueError(f"补丁{kind}超出文件末尾: {expected!r}")
            actual = line_body(original_lines[line_index])
            if actual != expected:
                raise ValueError(
                    f"补丁{kind}不匹配: 第 {line_index + 1} 行期望 {expected!r}，实际 {actual!r}"
                )
            original = original_lines[line_index]
            line_index += 1
            return original

        while pos < len(patch_lines):
            line = patch_lines[pos]
            if line.startswith("@@"):
                header = line
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$", header)
                if not match:
                    raise ValueError(f"无法解析 diff 头: {header}")
                old_start_raw = int(match.group(1))
                old_start = 0 if old_start_raw == 0 else old_start_raw - 1
                old_count = int(match.group(2) or "1")
                new_count = int(match.group(4) or "1")
                if old_start < line_index:
                    raise ValueError(f"diff hunk 顺序错误或重叠: {header}")
                if old_start > len(original_lines):
                    raise ValueError(f"diff hunk 起始行超出文件长度: {header}")
                pos += 1
                patched_lines.extend(original_lines[line_index:old_start])
                line_index = old_start
                consumed_old = 0
                produced_new = 0
                while pos < len(patch_lines) and not patch_lines[pos].startswith("@@"):
                    diff_line = patch_lines[pos]
                    if diff_line.startswith(" "):
                        patched_lines.append(expect_original(diff_line[1:], "上下文"))
                        consumed_old += 1
                        produced_new += 1
                    elif diff_line.startswith("-"):
                        expect_original(diff_line[1:], "删除行")
                        consumed_old += 1
                    elif diff_line.startswith("+"):
                        patched_lines.append(diff_line[1:] + "\n")
                        produced_new += 1
                    elif diff_line.startswith("\\ No newline at end of file"):
                        pass
                    else:
                        raise ValueError(f"无法解析 diff 行: {diff_line}")
                    pos += 1
                if consumed_old != old_count:
                    raise ValueError(f"diff hunk 删除/上下文行数不匹配: {header}")
                if produced_new != new_count:
                    raise ValueError(f"diff hunk 新增/上下文行数不匹配: {header}")
                hunks_applied += 1
            else:
                pos += 1
        if hunks_applied == 0:
            raise ValueError("补丁不包含任何 hunk")
        patched_lines.extend(original_lines[line_index:])
        file_path.write_text("".join(patched_lines), encoding="utf-8")

    _DEFAULT_EXCLUDES = {"__pycache__", ".git", "node_modules", ".venv", "venv", ".harness_state", "*.pyc"}
    _BINARY_EXTENSIONS = {".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".bin", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".tar", ".gz", ".whl", ".egg"}
    _MAX_GREP_MATCHES = 100

    @staticmethod
    def search_files(
        pattern: str,
        path: str = ".",
        exclude_patterns: list[str] | None = None,
    ) -> str:
        root = Path(path).resolve()
        if not root.exists():
            return f"路径不存在: {path}"
        if len(root.parents) == 0 or str(root) == root.root:
            return f"不允许搜索根目录: {path}，请指定具体的项目目录"
        excludes = set(exclude_patterns or []) | Tools._DEFAULT_EXCLUDES
        matched: list[str] = []
        for p in sorted(root.glob(pattern)):
            rel = p.relative_to(root)
            skip = False
            for exc in excludes:
                if fnmatch.fnmatch(str(rel), exc) or fnmatch.fnmatch(rel.name, exc) or exc in rel.parts:
                    skip = True
                    break
            if not skip and p.is_file():
                matched.append(str(rel))
            if len(matched) >= 500:
                matched.append("...（结果过多，已截断，请缩小搜索范围）")
                break
        if not matched:
            return f"未找到匹配 '{pattern}' 的文件"
        return "\n".join(matched)

    @staticmethod
    def _is_text_file(file_path: Path) -> bool:
        return file_path.suffix.lower() not in Tools._BINARY_EXTENSIONS

    @staticmethod
    def search_content(
        pattern: str,
        path: str = ".",
        include: str | None = None,
        exclude: str | None = None,
        context_lines: int = 0,
    ) -> str:
        root = Path(path).resolve()
        if not root.exists():
            return f"路径不存在: {path}"
        if len(root.parents) == 0 or str(root) == root.root:
            return f"不允许搜索根目录: {path}，请指定具体的项目目录"
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"无效的正则表达式: {e}"
        results: list[str] = []
        count = 0
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            rel = str(file_path.relative_to(root))
            parts = Path(rel).parts
            if any(d in parts for d in Tools._DEFAULT_EXCLUDES if "/" not in d):
                continue
            if not Tools._is_text_file(file_path):
                continue
            if include and not fnmatch.fnmatch(file_path.name, include):
                continue
            if exclude and fnmatch.fnmatch(file_path.name, exclude):
                continue
            try:
                lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            i = 0
            while i < len(lines):
                if regex.search(lines[i]):
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    for j in range(start, end):
                        prefix = ">" if j == i else " "
                        results.append(f"{rel}:{j + 1}:{prefix} {lines[j]}")
                    count += 1
                    if count >= Tools._MAX_GREP_MATCHES:
                        results.append(f"\n（已达到最大匹配数 {Tools._MAX_GREP_MATCHES}，结果已截断）")
                        return "\n".join(results)
                    i = end
                else:
                    i += 1
        if not results:
            return f"未找到匹配 '{pattern}' 的内容"
        return "\n".join(results)


def create_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDef(
        name="read_file",
        description="读取文件内容",
        parameters=[
            ToolParam(name="path", type="string", description="文件路径"),
        ],
        handler=Tools.read_file,
    ))
    registry.register(ToolDef(
        name="write_file",
        description="创建新文件并写入内容，自动创建父目录；修改已有文件请使用 apply_patch",
        parameters=[
            ToolParam(name="path", type="string", description="文件路径"),
            ToolParam(name="content", type="string", description="要写入的内容"),
        ],
        handler=Tools.write_file,
    ))
    registry.register(ToolDef(
        name="list_dir",
        description="列出目录内容",
        parameters=[
            ToolParam(name="path", type="string", description="目录路径"),
        ],
        handler=Tools.list_dir,
    ))
    registry.register(ToolDef(
        name="run_shell",
        description="执行 shell 命令",
        parameters=[
            ToolParam(name="command", type="string", description="要执行的命令"),
            ToolParam(name="cwd", type="string", description="工作目录", required=False),
            ToolParam(name="timeout_seconds", type="integer", description="命令超时秒数，默认 30", required=False),
        ],
        handler=lambda command, cwd=None, timeout_seconds=30: Tools.run_shell(command, cwd, timeout_seconds),
    ))
    registry.register(ToolDef(
        name="apply_patch",
        description="应用 unified diff 补丁到已有文件，适合局部修改",
        parameters=[
            ToolParam(name="path", type="string", description="文件路径"),
            ToolParam(name="patch_text", type="string", description="unified diff 补丁内容"),
        ],
        handler=Tools.apply_patch,
    ))
    registry.register(ToolDef(
        name="search_files",
        description="按文件名模式搜索文件（glob 风格）",
        parameters=[
            ToolParam(name="pattern", type="string", description="文件名模式，如 **/*.py"),
            ToolParam(name="path", type="string", description="搜索根目录，默认当前目录", required=False),
            ToolParam(name="exclude_patterns", type="string", description="排除模式（逗号分隔），如 node_modules,.git", required=False),
        ],
        handler=lambda pattern, path=".", exclude_patterns=None: Tools.search_files(pattern, path, exclude_patterns.split(",") if exclude_patterns else None),
    ))
    registry.register(ToolDef(
        name="search_content",
        description="在文件内容中搜索正则匹配（grep 风格）",
        parameters=[
            ToolParam(name="pattern", type="string", description="正则表达式"),
            ToolParam(name="path", type="string", description="搜索根目录，默认当前目录", required=False),
            ToolParam(name="include", type="string", description="只搜索匹配的文件名，如 *.py", required=False),
            ToolParam(name="exclude", type="string", description="排除匹配的文件名，如 *.log", required=False),
            ToolParam(name="context_lines", type="integer", description="上下文行数，默认 0", required=False),
        ],
        handler=lambda pattern, path=".", include=None, exclude=None, context_lines=0: Tools.search_content(pattern, path, include, exclude, context_lines),
    ))
    registry.register(ToolDef(
        name="web_search",
        description="联网搜索获取最新信息（使用 Bing 搜索）",
        parameters=[
            ToolParam(name="query", type="string", description="搜索关键词"),
            ToolParam(name="count", type="integer", description="返回结果数量，默认 5，最大 10", required=False),
        ],
        handler=lambda query, count=5: __import__("deepseek_code.web_search", fromlist=["web_search"]).web_search(query, count),
    ))
    return registry
