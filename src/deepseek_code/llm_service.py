from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class LLMService:
    def __init__(self, model: str = "deepseek-v4-flash", env: dict[str, Any] | None = None) -> None:
        self.model = model
        self._api_key = (env or {}).get("api_key") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self._api_base = (env or {}).get("api_base") or os.getenv("DEEPSEEK_API_BASE") or os.getenv("OPENAI_API_BASE")
        self._api_version = (env or {}).get("api_version") or os.getenv("DEEPSEEK_API_VERSION") or os.getenv("OPENAI_API_VERSION")
        self._api_type = (env or {}).get("api_type") or os.getenv("DEEPSEEK_API_TYPE") or os.getenv("OPENAI_API_TYPE")
        self._client = None
        if self._api_key:
            self._client = self._create_client()

    def _create_client(self):
        from openai import OpenAI
        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._api_base:
            kwargs["base_url"] = self._api_base
        if self._api_version:
            kwargs["default_headers"] = {"api-version": self._api_version}
        return OpenAI(**kwargs)

    def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self._api_key:
            return LLMResponse(
                content=(
                    "[模拟响应] 未配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。"
                    "请设置环境变量后再执行真实调用。"
                ),
                tool_calls=None,
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        if not response.choices:
            return LLMResponse(content="[错误] 未从 LLM 获取响应。")

        message = response.choices[0].message
        tool_calls = None
        if message.tool_calls:
            parsed: list[ToolCall] = []
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    continue
                parsed.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
            tool_calls = parsed if parsed else None

        content = message.content
        if not tool_calls and not content:
            content = "（LLM 返回的工具调用参数格式错误，已跳过）"

        return LLMResponse(content=content, tool_calls=tool_calls)
