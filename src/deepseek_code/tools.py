from __future__ import annotations

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
    def run_shell(command: str, cwd: str | None = None) -> str:
        result = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return f"[命令执行失败 (退出码 {result.returncode})] {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        return result.stdout

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

        while pos < len(patch_lines):
            line = patch_lines[pos]
            if line.startswith("@@"):
                header = line
                match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", header)
                if not match:
                    raise ValueError(f"无法解析 diff 头: {header}")
                old_start = int(match.group(1)) - 1
                pos += 1
                patched_lines.extend(original_lines[line_index:old_start])
                line_index = old_start
                while pos < len(patch_lines) and not patch_lines[pos].startswith("@@"):
                    diff_line = patch_lines[pos]
                    if diff_line.startswith(" "):
                        patched_lines.append(original_lines[line_index])
                        line_index += 1
                    elif diff_line.startswith("-"):
                        line_index += 1
                    elif diff_line.startswith("+"):
                        patched_lines.append(diff_line[1:] + "\n")
                    else:
                        raise ValueError(f"无法解析 diff 行: {diff_line}")
                    pos += 1
            else:
                pos += 1
        patched_lines.extend(original_lines[line_index:])
        file_path.write_text("".join(patched_lines), encoding="utf-8")


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
        description="写入文件内容，自动创建父目录",
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
        ],
        handler=lambda command, cwd=None: Tools.run_shell(command, cwd),
    ))
    registry.register(ToolDef(
        name="apply_patch",
        description="应用 unified diff 补丁到文件",
        parameters=[
            ToolParam(name="path", type="string", description="文件路径"),
            ToolParam(name="patch_text", type="string", description="unified diff 补丁内容"),
        ],
        handler=Tools.apply_patch,
    ))
    return registry
