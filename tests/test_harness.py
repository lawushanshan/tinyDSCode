from pathlib import Path

from deepseek_code.harness import Harness
from deepseek_code.tools import create_default_registry
from deepseek_code.llm_service import ToolCall


def test_perform_action_write_and_read(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    file_path = tmp_path / "example.txt"
    result = harness.perform_action(
        action="write_file",
        path=str(file_path),
        content="hello",
    )
    assert result == f"已写入 {file_path}"
    content = harness.perform_action(action="read_file", path=str(file_path))
    assert content == "hello"


def test_execute_tool_call(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    file_path = tmp_path / "test.txt"
    tc = ToolCall(id="call_1", name="write_file", arguments={"path": str(file_path), "content": "data"})
    result = harness.execute_tool_call(tc)
    assert "已写入" in result
    assert file_path.read_text(encoding="utf-8") == "data"


def test_execute_tool_call_read_file(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    file_path = tmp_path / "info.txt"
    file_path.write_text("内容", encoding="utf-8")
    tc = ToolCall(id="call_2", name="read_file", arguments={"path": str(file_path)})
    result = harness.execute_tool_call(tc)
    assert result == "内容"


def test_perform_action_unknown_raises() -> None:
    harness = Harness()
    try:
        harness.perform_action(action="nonexistent_tool")
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "未知操作" in str(e)


def test_execute_tool_call_shell_error_returns_text(tmp_path: Path) -> None:
    """shell 命令失败时 execute_tool_call 返回错误文本，不抛异常"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(id="call_err", name="run_shell", arguments={"command": "nonexistent_command_xyz_123"})
    result = harness.execute_tool_call(tc)
    assert "命令执行失败" in result
    assert isinstance(result, str)


def test_execute_tool_call_file_not_found_returns_error(tmp_path: Path) -> None:
    """文件不存在时 execute_tool_call 返回错误文本，不抛异常"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    tc = ToolCall(id="call_fnf", name="read_file", arguments={"path": "/nonexistent/path/file.txt"})
    result = harness.execute_tool_call(tc)
    assert "ERROR" in result or "不存在" in result
