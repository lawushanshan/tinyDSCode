from pathlib import Path

from deepseek_code.tools import Tools, ToolRegistry, ToolDef, ToolParam, create_default_registry


def test_read_write_file(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    Tools.write_file(str(file_path), "hello\nworld\n")
    assert file_path.read_text(encoding="utf-8") == "hello\nworld\n"
    content = Tools.read_file(str(file_path))
    assert content == "hello\nworld\n"


def test_list_dir(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    entries = Tools.list_dir(str(tmp_path))
    assert len(entries) == 2
    assert any(entry.endswith("a.txt") for entry in entries)
    assert any(entry.endswith("sub") for entry in entries)


def test_apply_patch(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    patch = """--- a/example.txt
+++ b/example.txt
@@ -1,3 +1,3 @@
 line1
-line2
+line2 modified
 line3
"""
    Tools.apply_patch(str(file_path), patch)
    assert file_path.read_text(encoding="utf-8") == "line1\nline2 modified\nline3\n"


# --- ToolRegistry 测试 ---


def test_registry_register_and_get() -> None:
    registry = ToolRegistry()
    tool = ToolDef(
        name="test_tool",
        description="测试工具",
        parameters=[ToolParam(name="x", type="string", description="参数x")],
        handler=lambda x: x,
    )
    registry.register(tool)
    assert registry.get("test_tool") is tool
    assert registry.get("nonexistent") is None


def test_registry_list_tools() -> None:
    registry = ToolRegistry()
    registry.register(ToolDef(
        name="a", description="工具A",
        parameters=[], handler=lambda: None,
    ))
    registry.register(ToolDef(
        name="b", description="工具B",
        parameters=[], handler=lambda: None,
    ))
    assert len(registry.list_tools()) == 2


def test_registry_to_openai_schema() -> None:
    registry = ToolRegistry()
    registry.register(ToolDef(
        name="read_file",
        description="读取文件",
        parameters=[
            ToolParam(name="path", type="string", description="文件路径"),
            ToolParam(name="encoding", type="string", description="编码", required=False),
        ],
        handler=lambda path, encoding="utf-8": None,
    ))
    schema = registry.to_openai_schema()
    assert len(schema) == 1
    func = schema[0]["function"]
    assert func["name"] == "read_file"
    assert "path" in func["parameters"]["properties"]
    assert func["parameters"]["required"] == ["path"]


def test_run_shell_failure_returns_error_text() -> None:
    """命令失败时返回错误信息，而非抛出异常"""
    result = Tools.run_shell("nonexistent_command_xyz_123")
    assert "命令执行失败" in result
    assert "nonexistent_command_xyz_123" in result


def test_run_shell_success() -> None:
    """命令成功时返回 stdout"""
    result = Tools.run_shell("echo hello")
    assert "hello" in result


def test_create_default_registry() -> None:
    registry = create_default_registry()
    assert registry.get("read_file") is not None
    assert registry.get("write_file") is not None
    assert registry.get("list_dir") is not None
    assert registry.get("run_shell") is not None
    assert registry.get("apply_patch") is not None
    schema = registry.to_openai_schema()
    assert len(schema) == 5
