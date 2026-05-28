from __future__ import annotations
import json
import re
from typing import Any


class MemoryManager:
    def __init__(self, max_context_tokens: int = 8000) -> None:
        self.history: list[dict[str, str]] = []
        self.max_context_tokens = max_context_tokens
        self.project_context: str = ""
        self.recent_decisions: list[str] = []
        self.session_notes: list[str] = []

    def load_ticket(self, ticket: Any) -> None:
        self.history.append({"role": "user", "content": ticket.description})

    def append_assistant(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})

    def append_tool_result(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})

    def append_system(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})

    def set_project_context(self, content: str) -> None:
        self.project_context = content.strip()

    def record_decision(self, label: str, detail: str) -> None:
        entry = f"{label}: {detail}".strip()
        if not entry:
            return
        self.recent_decisions.append(entry)
        self.recent_decisions = self.recent_decisions[-12:]

    def set_session_notes(self, notes: list[dict[str, Any]]) -> None:
        compact: list[str] = []
        for note in notes[-12:]:
            if not isinstance(note, dict):
                continue
            text = str(note.get("text", "")).strip()
            if not text:
                continue
            category = str(note.get("category", "general")).strip() or "general"
            source = str(note.get("source", "")).strip()
            suffix = f" ({source})" if source else ""
            compact.append(f"[{category}] {text}{suffix}")
        self.session_notes = compact

    def _build_system_prompt(self) -> str:
        return (
            "你是 DeepSeek Code AI 助手，一个 Claude Code 风格的编码助手。\n\n"
            "## 工作流程（Ralph 循环）\n"
            "每次回复时，请在一次推理中完成以下四个阶段：\n"
            "1. **观察**：回顾当前上下文，确认已知信息和环境状态\n"
            "2. **分析**：理解用户意图，识别依赖关系和潜在风险\n"
            "3. **决策**：选择合适的行动（读取文件、写入文件、执行命令等）\n"
            "4. **执行**：通过工具调用完成具体操作\n\n"
            "## 工具使用\n"
            "你通过 function calling 使用工具。可用工具：\n"
            "- read_file(path): 读取文件内容\n"
            "- write_file(path, content): 创建新文件并写入内容（自动创建父目录）\n"
            "- list_dir(path): 列出目录内容\n"
            "- run_shell(command, cwd?): 执行 shell 命令\n"
            "- apply_patch(path, patch_text): 应用 unified diff 补丁\n\n"
            "## 编辑规则\n"
            "- 创建新文件时可以使用 write_file\n"
            "- 修改已有文件时必须优先使用 apply_patch，生成最小 unified diff\n"
            "- 不要为了局部修改而用 write_file 覆盖整个已有文件\n\n"
            "## 项目上下文使用\n"
            "- 如果提供了 Repo Map / 项目画像，请优先利用其中的 languages、package_managers、entry_points、scripts、test_commands\n"
            "- 编辑前先根据项目画像判断技术栈和入口点；不要默认项目一定是 Python\n"
            "- 需要验证时，优先选择项目画像中的 test_commands，或与变更文件最相关的窄范围测试命令\n\n"
            "## 输出格式\n"
            "- 需要执行操作时，调用相应工具\n"
            "- 任务完成后，返回可读的结果摘要\n"
            "- 遇到错误时，分析原因并尝试修复或回退\n"
            "- 不要重复已执行的操作\n"
        )

    def _estimate_tokens(self, messages: list[dict[str, str]]) -> int:
        total = 0
        for msg in messages:
            total += len(msg["content"]) // 2
        return total

    def _summarize_history(self, messages: list[dict[str, str]]) -> dict[str, str]:
        actions_taken: list[str] = []
        files_modified: list[str] = []
        errors_encountered: list[str] = []

        for msg in messages:
            content = msg.get("content", "")
            if "工具执行结果：" in content:
                if "已写入" in content:
                    match = re.search(r"已写入 (.+)", content)
                    if match:
                        files_modified.append(match.group(1).strip())
                elif "已应用补丁" in content:
                    match = re.search(r"已应用补丁到 (.+)", content)
                    if match:
                        files_modified.append(match.group(1).strip())
                else:
                    actions_taken.append(content[:100])
            elif "命令执行失败" in content or "Error" in content or "错误" in content:
                errors_encountered.append(content[:100])

        summary: dict[str, Any] = {
            "actions_taken": actions_taken[-10:],
            "files_modified": files_modified,
            "errors_encountered": errors_encountered[-5:],
        }
        if not any(summary.values()):
            summary["note"] = "早期对话已裁剪"
        return {"role": "system", "content": json.dumps(summary, ensure_ascii=False, indent=2)}

    def _trim_history(self) -> list[dict[str, str]]:
        if len(self.history) <= self.max_history_items():
            return self.history.copy()

        system_messages = [{"role": "system", "content": self._build_system_prompt()}]
        if self.project_context:
            system_messages.append({"role": "system", "content": self.project_context})
        system_prompt_tokens = self._estimate_tokens(system_messages)
        summary_budget = 100
        budget = self.max_context_tokens - system_prompt_tokens - summary_budget
        if self.max_context_tokens < system_prompt_tokens + summary_budget:
            budget = max(0, self.max_context_tokens // 4)
        if budget < 0:
            budget = 0

        trimmed: list[dict[str, str]] = []
        token_count = 0
        for msg in reversed(self.history):
            msg_tokens = self._estimate_tokens([msg])
            if token_count + msg_tokens > budget:
                break
            trimmed.insert(0, msg)
            token_count += msg_tokens

        if len(trimmed) < len(self.history):
            dropped = self.history[: len(self.history) - len(trimmed)]
            summary_msg = self._summarize_history(dropped)
            return [summary_msg] + trimmed

        return trimmed

    def max_history_items(self) -> int:
        return max(4, self.max_context_tokens // 600)

    def build_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt()},
        ]
        if self.project_context:
            messages.append({"role": "system", "content": self.project_context})
        if self.recent_decisions:
            recent = "\n".join(f"- {item}" for item in self.recent_decisions[-8:])
            messages.append({"role": "system", "content": f"## Recent Decisions\n{recent}"})
        if self.session_notes:
            notes = "\n".join(f"- {item}" for item in self.session_notes[-8:])
            messages.append({"role": "system", "content": f"## Session Notes\n{notes}"})
        trimmed_history = self._trim_history()
        messages.extend(trimmed_history)
        return messages

    def clear_working(self) -> None:
        self.history.clear()
