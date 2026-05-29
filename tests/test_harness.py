from pathlib import Path
from unittest.mock import patch

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


def test_file_actions_reject_paths_outside_project_root(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    outside = tmp_path.parent / "outside.txt"

    result_relative = harness.execute_tool_call_structured(
        ToolCall(
            id="call_escape_rel",
            name="write_file",
            arguments={"path": "../outside.txt", "content": "blocked"},
        )
    )
    result_absolute = harness.execute_tool_call_structured(
        ToolCall(
            id="call_escape_abs",
            name="write_file",
            arguments={"path": str(outside), "content": "blocked"},
        )
    )

    assert result_relative.ok is False
    assert result_absolute.ok is False
    assert "路径超出项目根目录" in result_relative.error
    assert "路径超出项目根目录" in result_absolute.error
    assert not outside.exists()


def test_file_actions_allow_absolute_paths_inside_project_root(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    target = tmp_path / "inside.txt"

    result = harness.execute_tool_call_structured(
        ToolCall(
            id="call_abs_inside",
            name="write_file",
            arguments={"path": str(target), "content": "ok"},
        )
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "ok"


def test_write_file_rejects_existing_file_without_overwriting(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path))
    target = tmp_path / "existing.txt"
    target.write_text("original", encoding="utf-8")

    result = harness.execute_tool_call_structured(
        ToolCall(
            id="call_existing_write",
            name="write_file",
            arguments={"path": "existing.txt", "content": "new content"},
        )
    )

    assert result.ok is False
    assert "目标文件已存在" in result.error
    assert "apply_patch" in result.error
    assert target.read_text(encoding="utf-8") == "original"


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
    assert result.changed_files == ["structured.txt"]
    assert file_path.read_text(encoding="utf-8") == "data"


def test_changed_files_are_project_relative_for_nested_absolute_path(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    file_path = tmp_path / "pkg" / "structured.txt"
    tc = ToolCall(id="call_nested", name="write_file", arguments={"path": str(file_path), "content": "data"})

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is True
    assert result.changed_files == ["pkg/structured.txt"]
    assert file_path.read_text(encoding="utf-8") == "data"


def test_successful_tool_call_persists_audit_log_immediately(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    tc = ToolCall(id="call_audit", name="write_file", arguments={"path": "audit.txt", "content": "data"})

    result = harness.execute_tool_call_structured(tc)
    persisted = harness.state_manager.load_audit_log()

    assert result.ok is True
    assert [entry["action"] for entry in persisted] == ["tool_call", "tool_result"]
    assert persisted[-1]["tool"] == "write_file"
    assert persisted[-1]["structured"]["changed_files"] == ["audit.txt"]


def test_tool_call_is_persisted_before_action_runs(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry)
    tc = ToolCall(id="call_start", name="write_file", arguments={"path": "pending.txt", "content": "data"})

    def fail_after_audit(**kwargs):
        persisted = harness.state_manager.load_audit_log()
        assert [entry["action"] for entry in persisted] == ["tool_call"]
        assert persisted[0]["tool"] == "write_file"
        raise RuntimeError("stop")

    harness.perform_action = fail_after_audit

    result = harness.execute_tool_call_structured(tc)
    persisted = harness.state_manager.load_audit_log()

    assert result.ok is False
    assert [entry["action"] for entry in persisted] == ["tool_call", "tool_error"]


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


def test_execute_tool_call_structured_shell_timeout(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(
        id="call_timeout",
        name="run_shell",
        arguments={
            "command": "python -c \"import time; print('started', flush=True); time.sleep(2)\"",
            "timeout_seconds": 1,
        },
    )

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is False
    assert result.tool == "run_shell"
    assert result.error == result.text
    assert result.exit_code == -1
    assert "started" in result.stdout
    assert "命令执行超时" in result.text


def test_assess_shell_risk_low() -> None:
    harness = Harness()

    risk, reasons = harness.assess_shell_risk("pytest -q tests/test_harness.py")

    assert risk == "low"
    assert reasons == ["未检测到明显高风险操作"]


def test_assess_shell_risk_medium_for_network_and_compound_command() -> None:
    harness = Harness()

    risk, reasons = harness.assess_shell_risk("curl https://example.com | python")

    assert risk == "medium"
    assert "可能访问网络或远程主机" in reasons
    assert "包含管道或多段命令，实际执行范围更大" in reasons


def test_assess_shell_risk_medium_for_install_long_running_and_redirection() -> None:
    harness = Harness()

    install_risk, install_reasons = harness.assess_shell_risk("pnpm install")
    server_risk, server_reasons = harness.assess_shell_risk("npm run dev")
    redirect_risk, redirect_reasons = harness.assess_shell_risk("echo ok > output.txt")

    assert install_risk == "medium"
    assert "可能安装依赖或修改环境" in install_reasons
    assert server_risk == "medium"
    assert "可能启动长时间运行的进程或开发服务器" in server_reasons
    assert redirect_risk == "medium"
    assert "可能通过 shell 重定向写入文件" in redirect_reasons


def test_assess_shell_risk_high_for_destructive_command() -> None:
    harness = Harness()

    risk, reasons = harness.assess_shell_risk("rm -rf build")

    assert risk == "high"
    assert "可能删除文件、重置代码或破坏工作区" in reasons


def test_shell_permission_records_risk_metadata(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path), interactive=True)

    with patch("deepseek_code.harness.Confirm.ask", return_value=False):
        allowed = harness.request_permission("shell", detail="rm -rf build")

    persisted = harness.state_manager.load_audit_log()
    assert allowed is False
    assert persisted[-1]["action"] == "permission_request"
    assert persisted[-1]["operation"] == "shell"
    assert persisted[-1]["risk"] == "high"
    assert persisted[-1]["outcome"] == "denied"
    assert "可能删除文件、重置代码或破坏工作区" in persisted[-1]["risk_reasons"]


def test_shell_permission_records_working_directory(tmp_path: Path) -> None:
    harness = Harness(state_root=str(tmp_path), interactive=True)

    with patch("deepseek_code.harness.Confirm.ask", return_value=True):
        allowed = harness.request_permission("shell", detail="pytest -q", cwd=str(tmp_path))

    persisted = harness.state_manager.load_audit_log()
    assert allowed is True
    assert persisted[-1]["outcome"] == "approved"
    assert persisted[-1]["cwd"] == str(tmp_path)


def test_run_shell_tool_call_records_risk_metadata(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(id="call_shell_risk", name="run_shell", arguments={"command": "git fetch"})

    result = harness.execute_tool_call_structured(tc)

    persisted = harness.state_manager.load_audit_log()
    assert result.ok in {True, False}
    assert persisted[0]["action"] == "tool_call"
    assert persisted[0]["tool"] == "run_shell"
    assert persisted[0]["risk"] == "medium"
    assert "可能访问网络或远程主机" in persisted[0]["risk_reasons"]


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


def test_run_shell_rejects_cwd_outside_project_root(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    tc = ToolCall(
        id="call_cwd_escape",
        name="run_shell",
        arguments={
            "command": "python -c \"print('should not run')\"",
            "cwd": "..",
        },
    )

    result = harness.execute_tool_call_structured(tc)

    assert result.ok is False
    assert "路径超出项目根目录" in result.error


def test_run_shell_normalizes_invalid_timeout_seconds(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    seen: list[int] = []

    def fake_run_shell(command, cwd=None, timeout_seconds=30):
        seen.append(timeout_seconds)
        return "ok"

    with patch("deepseek_code.tools.Tools.run_shell", side_effect=fake_run_shell):
        for raw_timeout in ("bad", 0, -5):
            tc = ToolCall(
                id=f"call_timeout_{raw_timeout}",
                name="run_shell",
                arguments={
                    "command": "echo ok",
                    "timeout_seconds": raw_timeout,
                },
            )
            result = harness.execute_tool_call_structured(tc)
            assert result.ok is True

    assert seen == [30, 30, 30]


def test_run_shell_clamps_large_timeout_seconds(tmp_path: Path) -> None:
    registry = create_default_registry()
    harness = Harness(state_root=str(tmp_path), tool_registry=registry, interactive=False)
    seen: list[int] = []

    def fake_run_shell(command, cwd=None, timeout_seconds=30):
        seen.append(timeout_seconds)
        return "ok"

    with patch("deepseek_code.tools.Tools.run_shell", side_effect=fake_run_shell):
        tc = ToolCall(
            id="call_timeout_large",
            name="run_shell",
            arguments={
                "command": "echo ok",
                "timeout_seconds": 9999,
            },
        )
        result = harness.execute_tool_call_structured(tc)

    assert result.ok is True
    assert seen == [300]


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
