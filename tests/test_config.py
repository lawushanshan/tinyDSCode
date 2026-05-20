import json
from pathlib import Path

from deepseek_code.config import (
    AppConfig,
    ModelConfig,
    load_config,
    resolve_model,
    list_models,
    _find_config_file,
    DEFAULT_CONFIG,
)


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_file = tmp_path / ".deepseek-code.json"
    config_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return config_file


def test_default_config() -> None:
    config = DEFAULT_CONFIG
    assert len(config.models) >= 1
    assert config.default == "deepseek-flash"
    assert config.models[0].name == "deepseek-flash"


def test_load_config_from_file(tmp_path: Path) -> None:
    data = {
        "models": [
            {"name": "my-model", "model": "my-model-v1", "api_base": "https://example.com/v1"},
            {"name": "another", "model": "another-v2"},
        ],
        "default": "my-model",
    }
    _write_config(tmp_path, data)
    config = load_config(str(tmp_path / ".deepseek-code.json"))
    assert len(config.models) == 2
    assert config.models[0].name == "my-model"
    assert config.models[0].api_base == "https://example.com/v1"
    assert config.default == "my-model"


def test_load_config_invalid_json(tmp_path: Path) -> None:
    config_file = tmp_path / ".deepseek-code.json"
    config_file.write_text("not json", encoding="utf-8")
    config = load_config(str(config_file))
    assert config == DEFAULT_CONFIG


def test_load_config_missing_file(tmp_path: Path) -> None:
    config = load_config(str(tmp_path / "nonexistent.json"))
    assert config == DEFAULT_CONFIG


def test_resolve_model_from_preset() -> None:
    config = AppConfig(
        models=[
            ModelConfig(name="flash", model="deepseek-chat", api_base="https://api.deepseek.com"),
            ModelConfig(name="pro", model="deepseek-reasoner", api_base="https://api.deepseek.com"),
        ],
        default="flash",
    )
    model, env = resolve_model("flash", config)
    assert model == "deepseek-chat"
    assert env["api_base"] == "https://api.deepseek.com"


def test_resolve_model_fallback_raw() -> None:
    config = AppConfig(models=[], default="")
    model, env = resolve_model("gpt-4", config)
    assert model == "gpt-4"


def test_resolve_model_with_env_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MY_KEY", "sk-test-123")
    config = AppConfig(
        models=[
            ModelConfig(name="custom", model="custom-v1", api_key_env="MY_KEY", api_base="https://custom.api/v1"),
        ],
        default="custom",
    )
    model, env = resolve_model("custom", config)
    assert model == "custom-v1"
    assert env["api_key"] == "sk-test-123"
    assert env["api_base"] == "https://custom.api/v1"


def test_list_models() -> None:
    config = AppConfig(
        models=[
            ModelConfig(name="a", model="model-a", api_base="https://a.com"),
            ModelConfig(name="b", model="model-b"),
        ],
        default="a",
    )
    models = list_models(config)
    assert len(models) == 2
    assert models[0]["name"] == "a"
    assert models[0]["api_base"] == "https://a.com"
    assert "api_base" not in models[1] or models[1].get("api_base") == ""


def test_find_config_file_explicit(tmp_path: Path) -> None:
    f = tmp_path / "my-config.json"
    f.write_text("{}", encoding="utf-8")
    result = _find_config_file(str(f))
    assert result == f


def test_find_config_file_none(tmp_path: Path) -> None:
    result = _find_config_file(str(tmp_path / "nonexistent.json"))
    assert result is None
