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


def test_file_actions_resolve_relative_paths_from_project_root(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))

    result = harness.perform_action(
        action="write_file",
        path="src/example.txt",
        content="hello",
    )
    content = harness.perform_action(action="read_file", path="src/example.txt")

    assert result == "已写入 src/example.txt"
    assert content == "hello"
    assert (tmp_path / "src" / "example.txt").read_text(encoding="utf-8") == "hello"


def test_apply_patch_resolves_relative_path_from_project_root(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")

    result = harness.perform_action(
        action="apply_patch",
        path="app.py",
        patch_text="@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
    )

    assert result == "已应用补丁到 app.py"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"


def test_search_actions_resolve_relative_paths_from_project_root(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "app.py").write_text("TARGET = 1\n", encoding="utf-8")

    files = harness.perform_action(action="search_files", path="pkg", pattern="*.py")
    content = harness.perform_action(action="search_content", path="pkg", pattern="TARGET")

    assert "app.py" in files
    assert "TARGET" in content


def test_execute_tool_call(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    file_path = tmp_path / "test.txt"
    tc = ToolCall(id="call_1", name="write_file", arguments={"path": str(file_path), "content": "data"})
    result = harness.execute_tool_call(tc)
    assert "已写入" in result
    assert file_path.read_text(encoding="utf-8") == "data"


def test_execute_tool_call_structured_write_file(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    file_path = tmp_path / "structured.txt"
    tc = ToolCall(id="call_struct", name="write_file", arguments={"path": str(file_path), "content": "data"})

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is True
    assert result.tool == "write_file"
    assert result.text == f"已写入 {file_path}"
    assert result.changed_files == [str(file_path)]
    assert file_path.read_text(encoding="utf-8") == "data"


def test_execute_tool_call_structured_shell_error(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(id="call_struct_err", name="run_shell", arguments={"command": "nonexistent_command_xyz_123"})

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is False
    assert result.tool == "run_shell"
    assert result.exit_code is not None
    assert "命令执行失败" in result.text
    assert result.error == result.text


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


def test_run_shell_defaults_to_project_root(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(
        id="call_pwd",
        name="run_shell",
        arguments={"command": "python -c \"from pathlib import Path; print(Path.cwd())\""},
    )

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is True
    assert Path(result.stdout.strip()) == tmp_path


def test_run_shell_resolves_relative_cwd_from_project_root(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    (tmp_path / "pkg").mkdir()
    tc = ToolCall(
        id="call_pwd_pkg",
        name="run_shell",
        arguments={
            "command": "python -c \"from pathlib import Path; print(Path.cwd())\"",
            "cwd": "pkg",
        },
    )

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is True
    assert Path(result.stdout.strip()) == tmp_path / "pkg"


def test_execute_tool_call_file_not_found_returns_error(tmp_path: Path) -> None:
    """文件不存在时 execute_tool_call 返回错误文本，不抛异常"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    tc = ToolCall(id="call_fnf", name="read_file", arguments={"path": "/nonexistent/path/file.txt"})
    result = harness.execute_tool_call(tc)
    assert "ERROR" in result or "不存在" in result


def test_execute_tool_call_search_files(tmp_path: Path) -> None:
    """通过 harness 执行 search_files 工具"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    (tmp_path / "hello.py").write_text("x", encoding="utf-8")
    (tmp_path / "world.txt").write_text("y", encoding="utf-8")
    tc = ToolCall(id="call_glob", name="search_files", arguments={"pattern": "**/*.py", "path": str(tmp_path)})
    result = harness.execute_tool_call(tc)
    assert "hello.py" in result
    assert "world.txt" not in result


def test_execute_tool_call_search_content(tmp_path: Path) -> None:
    """通过 harness 执行 search_content 工具"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    (tmp_path / "app.py").write_text("import os\nimport sys\n", encoding="utf-8")
    tc = ToolCall(id="call_grep", name="search_content", arguments={"pattern": "import", "path": str(tmp_path)})
    result = harness.execute_tool_call(tc)
    assert "app.py" in result
    assert "import" in result


def test_execute_tool_call_web_search(tmp_path: Path) -> None:
    """通过 harness 执行 web_search 工具"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    tc = ToolCall(id="call_ws", name="web_search", arguments={"query": "Python"})
    result = harness.execute_tool_call(tc)
    # 实际调用百度，只要不崩溃就行
    assert isinstance(result, str)
    assert len(result) > 0


def test_list_dir_empty_directory(tmp_path: Path) -> None:
    """空目录返回明确提示，而非空字符串"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    tc = ToolCall(id="call_empty", name="list_dir", arguments={"path": str(empty_dir)})
    result = harness.execute_tool_call(tc)
    assert "目录为空" in result


def test_read_file_empty_file(tmp_path: Path) -> None:
    """空文件返回明确提示，而非空字符串"""
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    tc = ToolCall(id="call_ef", name="read_file", arguments={"path": str(empty_file)})
    result = harness.execute_tool_call(tc)
    assert "文件为空" in result
