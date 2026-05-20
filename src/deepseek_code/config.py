from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ModelConfig(BaseModel):
    name: str
    model: str
    api_base: str | None = None
    api_key_env: str | None = None
    api_version: str | None = None
    api_type: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096


class AppConfig(BaseModel):
    models: list[ModelConfig] = []
    default: str = ""


CONFIG_FILENAME = ".deepseek-code.json"

DEFAULT_CONFIG = AppConfig(
    models=[
        ModelConfig(
            name="deepseek-flash",
            model="deepseek-chat",
            api_base="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        ),
    ],
    default="deepseek-flash",
)


def _find_config_file(config_path: str | None = None) -> Path | None:
    if config_path:
        p = Path(config_path)
        return p if p.exists() else None

    # 项目目录
    local = Path.cwd() / CONFIG_FILENAME
    if local.exists():
        return local

    # 用户目录
    home = Path.home() / ".deepseek-code" / "config.json"
    if home.exists():
        return home

    return None


def load_config(config_path: str | None = None) -> AppConfig:
    path = _find_config_file(config_path)
    if path is None:
        return DEFAULT_CONFIG
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig(**data)
    except (json.JSONDecodeError, Exception):
        return DEFAULT_CONFIG


def resolve_model(model_arg: str, config: AppConfig) -> tuple[str, dict[str, Any]]:
    """根据 --model 参数解析模型配置。

    返回 (model_name, env_overrides)。
    如果 model_arg 匹配配置中的预设名称，使用预设配置；
    否则当作原始模型字符串，仅使用环境变量。
    """
    for mc in config.models:
        if mc.name == model_arg:
            env: dict[str, Any] = {}
            if mc.api_base:
                env["api_base"] = mc.api_base
            if mc.api_key_env:
                key = os.getenv(mc.api_key_env, "")
                if not key:
                    key = mc.api_key_env
                env["api_key"] = key
            if mc.api_version:
                env["api_version"] = mc.api_version
            if mc.api_type:
                env["api_type"] = mc.api_type
            return mc.model, env

    # 未匹配预设，当作原始模型字符串
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("DEEPSEEK_API_BASE") or os.getenv("OPENAI_API_BASE")
    env: dict[str, Any] = {}
    if api_key:
        env["api_key"] = api_key
    if api_base:
        env["api_base"] = api_base
    return model_arg, env


def list_models(config: AppConfig) -> list[dict[str, str]]:
    result = []
    for mc in config.models:
        item: dict[str, str] = {"name": mc.name, "model": mc.model}
        if mc.api_base:
            item["api_base"] = mc.api_base
        result.append(item)
    return result
