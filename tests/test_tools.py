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


def test_apply_patch_multiple_hunks(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    patch = """--- a/example.txt
+++ b/example.txt
@@ -1,2 +1,2 @@
 a
-b
+B
@@ -4,2 +4,2 @@
 d
-e
+E
"""

    Tools.apply_patch(str(file_path), patch)

    assert file_path.read_text(encoding="utf-8") == "a\nB\nc\nd\nE\n"


def test_apply_patch_rejects_mismatched_context_without_writing(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    original = "line1\nline2\nline3\n"
    file_path.write_text(original, encoding="utf-8")
    patch = """--- a/example.txt
+++ b/example.txt
@@ -1,3 +1,3 @@
 line1
-not-line2
+line2 modified
 line3
"""

    try:
        Tools.apply_patch(str(file_path), patch)
        assert False, "应该拒绝上下文不匹配的补丁"
    except ValueError as exc:
        assert "不匹配" in str(exc)

    assert file_path.read_text(encoding="utf-8") == original


def test_apply_patch_rejects_patch_without_hunk(tmp_path: Path) -> None:
    file_path = tmp_path / "example.txt"
    file_path.write_text("line1\n", encoding="utf-8")

    try:
        Tools.apply_patch(str(file_path), "--- a/example.txt\n+++ b/example.txt\n")
        assert False, "应该拒绝不包含 hunk 的补丁"
    except ValueError as exc:
        assert "不包含任何 hunk" in str(exc)


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


def test_run_shell_success_no_output(tmp_path: Path) -> None:
    """命令成功但无输出时返回成功提示，而非空字符串"""
    test_dir = str(tmp_path / "test_dir")
    result = Tools.run_shell(f'mkdir "{test_dir}"')
    assert "命令执行成功" in result


def test_create_default_registry() -> None:
    registry = create_default_registry()
    assert registry.get("read_file") is not None
    assert registry.get("write_file") is not None
    assert registry.get("list_dir") is not None
    assert registry.get("run_shell") is not None
    assert registry.get("apply_patch") is not None
    assert registry.get("search_files") is not None
    assert registry.get("search_content") is not None
    assert registry.get("web_search") is not None
    schema = registry.to_openai_schema()
    assert len(schema) == 8


# --- search_files (glob) 测试 ---


def test_search_files_pattern(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    (tmp_path / "b.py").write_text("b", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "d.py").write_text("d", encoding="utf-8")

    result = Tools.search_files("**/*.py", str(tmp_path))
    assert "a.py" in result
    assert "b.py" in result
    assert "c.txt" not in result
    lines = result.strip().split("\n")
    assert len(lines) == 3


def test_search_files_exclude(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "b.py").write_text("b", encoding="utf-8")

    result = Tools.search_files("**/*.py", str(tmp_path), exclude_patterns=["node_modules"])
    assert "a.py" in result
    assert "b.py" not in result


def test_search_files_default_excludes_git(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a", encoding="utf-8")
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "b.py").write_text("b", encoding="utf-8")

    result = Tools.search_files("**/*.py", str(tmp_path))
    assert "a.py" in result
    assert "b.py" not in result


def test_search_files_not_found(tmp_path: Path) -> None:
    result = Tools.search_files("**/*.rs", str(tmp_path))
    assert "未找到" in result


def test_search_files_root_directory_rejected() -> None:
    root = Path("/").resolve()
    result = Tools.search_files("**/*.py", str(root))
    assert "不允许搜索根目录" in result


def test_search_files_result_truncation(tmp_path: Path) -> None:
    for i in range(510):
        (tmp_path / f"file_{i}.py").write_text("x", encoding="utf-8")
    result = Tools.search_files("*.py", str(tmp_path))
    assert "截断" in result


# --- search_content (grep) 测试 ---


def test_search_content_pattern(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hello():\n    return 42\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("# no match here\npass\n", encoding="utf-8")

    result = Tools.search_content("hello", str(tmp_path))
    assert "a.py" in result
    assert "hello" in result
    assert "b.py" not in result


def test_search_content_with_include(tmp_path: Path) -> None:
    (tmp_path / "code.py").write_text("target_line\n", encoding="utf-8")
    (tmp_path / "readme.txt").write_text("target_line\n", encoding="utf-8")

    result = Tools.search_content("target_line", str(tmp_path), include="*.py")
    assert "code.py" in result
    assert "readme.txt" not in result


def test_search_content_with_exclude(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "test.log").write_text("import os\n", encoding="utf-8")

    result = Tools.search_content("import", str(tmp_path), exclude="*.log")
    assert "main.py" in result
    assert "test.log" not in result


def test_search_content_context_lines(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("line1\nline2 TARGET\nline3\nline4\n", encoding="utf-8")
    result = Tools.search_content("TARGET", str(tmp_path), context_lines=1)
    assert ">line2 TARGET" in result or "TARGET" in result
    assert "line1" in result
    assert "line3" in result


def test_search_content_no_match(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello world\n", encoding="utf-8")
    result = Tools.search_content("xyz_not_found", str(tmp_path))
    assert "未找到" in result


def test_search_content_root_directory_rejected() -> None:
    root = Path("/").resolve()
    result = Tools.search_content("import", str(root))
    assert "不允许搜索根目录" in result


def test_search_content_regex(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("foo_bar = 123\nbaz_qux = 456\n", encoding="utf-8")
    result = Tools.search_content(r"foo_\w+", str(tmp_path))
    assert "foo_bar" in result
    assert "baz_qux" not in result
