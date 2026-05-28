import subprocess
import json
from pathlib import Path
from unittest.mock import MagicMock

from deepseek_code.supervisor import Supervisor, SupervisorState
from deepseek_code.llm_service import LLMResponse, ToolCall
from deepseek_code.worker import StepDirective
from deepseek_code.persistence import StateManager
from deepseek_code.harness import ToolResult


def test_create_and_list_tickets() -> None:
    supervisor = Supervisor()
    assert supervisor.list_tickets() == "当前没有 Ticket"
    supervisor.create_ticket("测试任务")
    assert "汇总: pending=1, running=0, blocked=0, done=0, failed=0, cancelled=0" in supervisor.list_tickets()
    assert "T-001 (pending) - 测试任务" in supervisor.list_tickets()


def test_list_tickets_summarizes_status_counts() -> None:
    supervisor = Supervisor()
    pending = supervisor.create_ticket("待执行")
    blocked = supervisor.create_ticket("被阻塞")
    blocked.status = "blocked"
    done = supervisor.create_ticket("已完成")
    done.status = "done"
    cancelled = supervisor.create_ticket("已取消")
    cancelled.status = "cancelled"

    listing = supervisor.list_tickets()

    assert listing.splitlines()[0] == "汇总: pending=1, running=0, blocked=1, done=1, failed=0, cancelled=1"
    assert "T-001 (pending) - 待执行" in listing
    assert "T-002 (blocked) - 被阻塞" in listing
    assert "T-003 (done) - 已完成" in listing
    assert "T-004 (cancelled) - 已取消" in listing


def test_format_status_without_current_ticket() -> None:
    supervisor = Supervisor()
    assert supervisor.format_status() == "当前没有正在运行的 Ticket"


def test_format_status_with_current_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("测试状态")
    supervisor.start_ticket(ticket)

    status = supervisor.format_status()

    assert "当前 Ticket: T-001 (running)" in status
    assert "描述: 测试状态" in status
    assert "Ticket 开始执行" in status


def test_format_trace_without_steps() -> None:
    supervisor = Supervisor()
    assert supervisor.format_trace() == "当前没有可显示的执行轨迹"


def test_format_trace_with_tool_result(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    test_file = tmp_path / "trace.txt"
    test_file.write_text("trace-data", encoding="utf-8")
    tc = ToolCall(id="call_trace", name="read_file", arguments={"path": str(test_file)})

    supervisor.worker.llm_service = MagicMock()
    supervisor.worker.llm_service.chat.side_effect = [
        LLMResponse(content="读取 trace 文件", tool_calls=[tc]),
        LLMResponse(content="完成", tool_calls=None),
    ]

    ticket = supervisor.create_ticket("查看 trace")
    supervisor.start_ticket(ticket)
    supervisor.worker.execute_ticket(ticket, model="mock", on_step=supervisor._worker_on_step)

    trace = supervisor.format_trace()

    assert "执行轨迹：2 轮" in trace
    assert "循环 1" in trace
    assert "LLM 输出: 读取 trace 文件" in trace
    assert "工具调用 1: read_file" in trace
    assert "工具结果 1 [成功]: trace-data" in trace
    assert "结束原因: assistant_final" in trace


def test_after_tool_call_collects_changed_files(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    ticket = supervisor.create_ticket("修改文件")
    tc = ToolCall(id="call_write", name="write_file", arguments={"path": "src/app.py", "content": "x"})
    tool_result = ToolResult(
        tool="write_file",
        ok=True,
        text="已写入 src/app.py",
        changed_files=["src/app.py"],
    )

    supervisor._worker_on_step("after_tool_call", ticket=ticket, tool_call=tc, result=tool_result.text, tool_result=tool_result)
    supervisor._worker_on_step("after_tool_call", ticket=ticket, tool_call=tc, result=tool_result.text, tool_result=tool_result)

    assert supervisor.changed_files == ["src/app.py"]


def test_format_task_summary_with_changes_and_trace(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "summary.py"
    tc = ToolCall(id="call_write", name="write_file", arguments={"path": str(target), "content": "x = 1\n"})
    supervisor.worker.llm_service = MagicMock()
    supervisor.worker.llm_service.chat.side_effect = [
        LLMResponse(content="write file", tool_calls=[tc]),
        LLMResponse(content="done", tool_calls=None),
    ]

    ticket = supervisor.create_ticket("create summary file")
    supervisor.start_ticket(ticket)
    supervisor.worker.execute_ticket(ticket, model="mock", on_step=supervisor._worker_on_step)

    summary = supervisor.format_task_summary()

    assert "Changes" in summary
    assert "summary.py" in summary
    assert "Tests" in summary
    assert "Suggested: pytest -q" in summary
    assert "Notes" in summary
    assert "loop 1; tools=write_file" in summary
    assert "loop 2; done=assistant_final" in summary


def test_format_task_summary_without_changes() -> None:
    supervisor = Supervisor()

    summary = supervisor.format_task_summary()

    assert "Changes" in summary
    assert "- none" in summary
    assert "Tests" in summary
    assert "Suggested: not required" in summary
    assert "Notes" not in summary


def test_format_structured_output_sections(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    ticket = supervisor.create_ticket("结构化输出")
    supervisor.changed_files = ["src/app.py"]
    supervisor.worker.last_steps = []

    output = supervisor.format_structured_output([f"[{ticket.ticket_id}] 完成"], [ticket])

    assert output.startswith("Result")
    assert "[T-001] 完成" in output
    assert "Changes" in output
    assert "- src/app.py" in output
    assert "Tests" in output
    assert "Suggested: pytest -q" in output
    assert "建议验证" not in output


def test_format_plan_summary_for_multiple_tickets() -> None:
    supervisor = Supervisor()
    first = supervisor.create_ticket("read target file")
    second = supervisor.create_ticket("patch target file")

    summary = supervisor.format_plan_summary([first, second])

    assert "Plan" in summary
    assert "1. read target file" in summary
    assert "2. patch target file" in summary


def test_format_plan_summary_skips_single_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("single task")

    assert supervisor.format_plan_summary([ticket]) == ""


def test_suggest_verification_command_for_python_changes() -> None:
    supervisor = Supervisor()
    supervisor.changed_files = ["src/app.py"]

    assert supervisor.suggest_verification_command() == "pytest -q"


def test_suggest_verification_command_for_changed_test_file(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_app.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_app(): pass\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = [str(test_file)]

    assert supervisor.suggest_verification_command() == "pytest -q tests/test_app.py"


def test_suggest_verification_command_for_matching_test_file(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "app.py"
    test_file = tmp_path / "tests" / "test_app.py"
    src_file.parent.mkdir()
    test_file.parent.mkdir()
    src_file.write_text("def app(): pass\n", encoding="utf-8")
    test_file.write_text("def test_app(): pass\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = [str(src_file)]

    assert supervisor.suggest_verification_command() == "pytest -q tests/test_app.py"


def test_suggest_verification_command_for_src_package_test_file(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "pkg" / "app.py"
    test_file = tmp_path / "tests" / "pkg" / "test_app.py"
    src_file.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    src_file.write_text("def app(): pass\n", encoding="utf-8")
    test_file.write_text("def test_app(): pass\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/pkg/app.py"]

    assert supervisor.suggest_verification_command() == "pytest -q tests/pkg/test_app.py"


def test_suggest_verification_command_prefers_top_level_matching_test(tmp_path: Path) -> None:
    src_file = tmp_path / "src" / "pkg" / "app.py"
    top_level_test = tmp_path / "tests" / "test_app.py"
    package_test = tmp_path / "tests" / "pkg" / "test_app.py"
    src_file.parent.mkdir(parents=True)
    top_level_test.parent.mkdir(parents=True)
    package_test.parent.mkdir(parents=True)
    src_file.write_text("def app(): pass\n", encoding="utf-8")
    top_level_test.write_text("def test_app(): pass\n", encoding="utf-8")
    package_test.write_text("def test_app_pkg(): pass\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/pkg/app.py"]

    assert supervisor.suggest_verification_command() == "pytest -q tests/test_app.py"


def test_suggest_verification_command_for_node_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.ts"]

    assert supervisor.suggest_verification_command() == "npm test"


def test_suggest_verification_command_prefers_pnpm_for_node_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.tsx"]

    assert supervisor.suggest_verification_command() == "pnpm test"


def test_suggest_verification_command_prefers_bun_for_node_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "bun test"}}),
        encoding="utf-8",
    )
    (tmp_path / "bun.lockb").write_text("", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.ts"]

    assert supervisor.suggest_verification_command() == "bun test"


def test_suggest_verification_command_uses_npm_for_package_lock(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.js"]

    assert supervisor.suggest_verification_command() == "npm test"


def test_suggest_verification_command_skips_node_without_test_script(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "vite build"}}), encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.ts"]

    assert supervisor.suggest_verification_command() is None


def test_suggest_verification_command_for_go_project(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/app\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["cmd/app/main.go"]

    assert supervisor.suggest_verification_command() == "go test ./..."


def test_suggest_verification_command_for_rust_project(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"app\"\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/lib.rs"]

    assert supervisor.suggest_verification_command() == "cargo test"


def test_suggest_verification_command_for_maven_project(tmp_path: Path) -> None:
    (tmp_path / "pom.xml").write_text("<project></project>\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/main/java/App.java"]

    assert supervisor.suggest_verification_command() == "mvn test"


def test_suggest_verification_command_for_gradle_project(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/main/kotlin/App.kt"]

    assert supervisor.suggest_verification_command() == "gradle test"


def test_suggest_verification_command_prefers_gradle_wrapper(tmp_path: Path) -> None:
    (tmp_path / "build.gradle").write_text("plugins {}\n", encoding="utf-8")
    (tmp_path / "gradlew").write_text("", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/main/java/App.java"]

    assert supervisor.suggest_verification_command() == "./gradlew test"


def test_suggest_verification_command_for_dotnet_project(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").write_text("<Project></Project>\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["Program.cs"]

    assert supervisor.suggest_verification_command() == "dotnet test"


def test_run_verification_without_changed_files() -> None:
    supervisor = Supervisor()

    assert supervisor.run_verification() == "当前没有可验证的变更文件"


def test_run_verification_without_auto_command() -> None:
    supervisor = Supervisor()
    supervisor.changed_files = ["README.md"]

    assert supervisor.run_verification() == "当前变更没有自动验证命令，请手动检查相关文件"


def test_run_verification_executes_suggested_command(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["src/app.py"]
    seen: list[ToolCall] = []

    def fake_execute(tc: ToolCall) -> ToolResult:
        seen.append(tc)
        return ToolResult(tool="run_shell", ok=True, text="ok", stdout="tests passed")

    supervisor.harness.execute_tool_call_structured = fake_execute

    result = supervisor.run_verification()

    assert "验证命令: pytest -q" in result
    assert "验证结果: 通过" in result
    assert "tests passed" in result
    assert seen[0].name == "run_shell"
    assert seen[0].arguments["command"] == "pytest -q"
    assert seen[0].arguments["cwd"] == str(tmp_path)


def test_format_diff_for_untracked_changed_file(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "new_file.py"
    target.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    supervisor.changed_files = [str(target)]

    diff = supervisor.format_diff()

    assert "--- /dev/null" in diff
    assert f"+++ b/{target.name}" in diff
    assert "+def hello():" in diff


def test_format_diff_ignores_git_error_when_untracked_diff_exists(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "new_file.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    supervisor.changed_files = ["new_file.py"]

    def fake_run_git(command):
        if command[:2] == ["git", "diff"]:
            return subprocess.CompletedProcess(command, 128, "", "fatal: not a git repository")
        if command[:2] == ["git", "ls-files"]:
            return subprocess.CompletedProcess(command, 1, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    supervisor._run_git = fake_run_git

    diff = supervisor.format_diff()

    assert "fatal:" not in diff
    assert "--- /dev/null" in diff
    assert "+++ b/new_file.py" in diff
    assert "+VALUE = 1" in diff


def test_format_diff_for_tracked_file(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    target = tmp_path / "tracked.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True, capture_output=True, text=True)
    target.write_text("VALUE = 2\n", encoding="utf-8")

    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.changed_files = ["tracked.py"]

    diff = supervisor.format_diff()

    assert "diff --git" in diff
    assert "-VALUE = 1" in diff
    assert "+VALUE = 2" in diff


def test_format_diff_handles_empty_subprocess_stdout(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor._run_git = MagicMock(return_value=subprocess.CompletedProcess(["git", "diff"], 0, None, None))

    diff = supervisor.format_diff()

    assert diff == "当前工作区没有可显示的 git diff"


def test_format_checkpoint_for_clean_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)
    target = tmp_path / "tracked.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    checkpoint = Supervisor(state_root=str(tmp_path)).format_checkpoint()

    assert "Checkpoint" in checkpoint
    assert "- 分支:" in checkpoint
    assert "- HEAD:" in checkpoint
    assert "- 工作区: 干净" in checkpoint


def test_format_checkpoint_for_dirty_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    tracked = tmp_path / "tracked.py"
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True, capture_output=True, text=True)
    tracked.write_text("VALUE = 2\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("VALUE = 3\n", encoding="utf-8")

    checkpoint = Supervisor(state_root=str(tmp_path)).format_checkpoint()

    assert "- 工作区: 有 2 项变更" in checkpoint
    assert "tracked.py" in checkpoint
    assert "?? new.py" in checkpoint


def test_format_checkpoint_outside_git_repo(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor._run_git = MagicMock(return_value=subprocess.CompletedProcess(["git"], 128, "", "fatal"))

    checkpoint = supervisor.format_checkpoint()

    assert checkpoint == "当前目录不是可读取的 git 仓库，无法生成 checkpoint 状态"


def test_normalize_repl_command_accepts_missing_colon() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("verify") == ":verify"
    assert supervisor.normalize_repl_command(" VERIFY ") == ":verify"
    assert supervisor.normalize_repl_command("status") == ":status"
    assert supervisor.normalize_repl_command("trace") == ":trace"
    assert supervisor.normalize_repl_command("checkpoint") == ":checkpoint"


def test_normalize_repl_command_accepts_slash_commands() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("/verify") == ":verify"
    assert supervisor.normalize_repl_command(" /STATUS ") == ":status"
    assert supervisor.normalize_repl_command("/diff") == ":diff"
    assert supervisor.normalize_repl_command("/checkpoint") == ":checkpoint"
    assert supervisor.normalize_repl_command("/ticket T-001") == ":ticket T-001"
    assert supervisor.normalize_repl_command("/revise T-001 修复描述") == ":revise T-001 修复描述"
    assert supervisor.normalize_repl_command("/continue") == ":continue"
    assert supervisor.normalize_repl_command("/continue T-003") == ":continue T-003"
    assert supervisor.normalize_repl_command("/new 测试任务") == ":new 测试任务"
    assert supervisor.normalize_repl_command("/new") == ":new"


def test_normalize_repl_command_keeps_regular_tasks() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("创建一个文件") == "创建一个文件"
    assert supervisor.normalize_repl_command(":new 测试") == ":new 测试"


def test_format_ticket_detail_for_existing_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("检查登录逻辑")
    ticket.acceptance_criteria = "通过测试"
    ticket.log.append("定位 auth.ts")

    detail = supervisor.format_ticket_detail("t-001")

    assert "Ticket: T-001" in detail
    assert "状态: pending" in detail
    assert "描述: 检查登录逻辑" in detail
    assert "验收标准: 通过测试" in detail
    assert "- 定位 auth.ts" in detail


def test_format_ticket_detail_for_missing_ticket() -> None:
    supervisor = Supervisor()

    assert supervisor.format_ticket_detail("T-404") == "未找到 Ticket: T-404"


def test_revise_ticket_updates_pending_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("旧描述")

    result = supervisor.revise_ticket(ticket.ticket_id, "新描述")

    assert result == "已修改 T-001: 新描述"
    assert ticket.description == "新描述"
    assert "Ticket 描述已修改" in ticket.log[-1]


def test_revise_ticket_resets_failed_ticket_to_pending() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("旧描述")
    ticket.status = "failed"

    result = supervisor.revise_ticket(ticket.ticket_id, "重试描述")

    assert result == "已修改 T-001: 重试描述"
    assert ticket.status == "pending"


def test_revise_ticket_rejects_running_or_done_ticket() -> None:
    supervisor = Supervisor()
    running = supervisor.create_ticket("运行中")
    running.status = "running"
    done = supervisor.create_ticket("已完成")
    done.status = "done"

    assert "不能修改描述" in supervisor.revise_ticket(running.ticket_id, "新描述")
    assert "不能修改描述" in supervisor.revise_ticket(done.ticket_id, "新描述")
    assert running.description == "运行中"
    assert done.description == "已完成"


def test_continue_next_ticket_runs_first_resumable_ticket() -> None:
    supervisor = Supervisor()
    done = supervisor.create_ticket("已完成")
    done.status = "done"
    pending = supervisor.create_ticket("继续这个")
    supervisor.run_existing_ticket = MagicMock(return_value="继续结果")

    result = supervisor.continue_next_ticket(model="mock")

    assert result == "继续结果"
    supervisor.run_existing_ticket.assert_called_once_with(pending, model="mock")


def test_continue_next_ticket_resets_failed_ticket_before_running() -> None:
    supervisor = Supervisor()
    failed = supervisor.create_ticket("失败任务")
    failed.status = "failed"
    supervisor.run_existing_ticket = MagicMock(return_value="重试结果")

    result = supervisor.continue_next_ticket(model="mock")

    assert result == "重试结果"
    assert failed.status == "pending"
    assert "准备继续执行" in failed.log[-1]
    supervisor.run_existing_ticket.assert_called_once_with(failed, model="mock")


def test_continue_ticket_runs_requested_ticket_id() -> None:
    supervisor = Supervisor()
    first = supervisor.create_ticket("第一个")
    second = supervisor.create_ticket("第二个")
    supervisor.run_existing_ticket = MagicMock(return_value="执行第二个")

    result = supervisor.continue_ticket("t-002", model="mock")

    assert result == "执行第二个"
    supervisor.run_existing_ticket.assert_called_once_with(second, model="mock")
    assert first.status == "pending"


def test_continue_ticket_rejects_done_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("已完成")
    ticket.status = "done"

    result = supervisor.continue_ticket(ticket.ticket_id, model="mock")

    assert result == "Ticket T-001 已完成，不能继续执行"


def test_continue_ticket_rejects_cancelled_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("已取消")
    ticket.status = "cancelled"

    result = supervisor.continue_ticket(ticket.ticket_id, model="mock")

    assert result == "Ticket T-001 已取消，不能继续执行"


def test_run_existing_ticket_keeps_original_ticket_id() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("原始任务")
    supervisor.worker.execute_ticket = MagicMock(return_value="完成原始任务")

    result = supervisor.run_existing_ticket(ticket, model="mock")

    assert "[T-001] 完成原始任务" in result
    assert len(supervisor.tickets) == 1
    assert supervisor.tickets[0].ticket_id == "T-001"
    assert supervisor.tickets[0].status == "done"
    supervisor.worker.execute_ticket.assert_called_once()
    assert supervisor.worker.execute_ticket.call_args[0][0] is ticket


def test_continue_next_ticket_without_resumable_ticket() -> None:
    supervisor = Supervisor()
    done = supervisor.create_ticket("已完成")
    done.status = "done"
    cancelled = supervisor.create_ticket("已取消")
    cancelled.status = "cancelled"

    assert supervisor.continue_next_ticket(model="mock") == "当前没有可继续执行的 Ticket"


def test_cancel_pending_tickets_marks_pending_only() -> None:
    supervisor = Supervisor()
    pending = supervisor.create_ticket("待取消")
    done = supervisor.create_ticket("已完成")
    done.status = "done"

    supervisor.cancel_pending_tickets([pending, done], "不需要了")

    assert pending.status == "cancelled"
    assert "Ticket 已取消: 不需要了" in pending.log[-1]
    assert done.status == "done"


def test_supervisor_initializes_project_context(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def app(): pass\n", encoding="utf-8")

    supervisor = Supervisor(state_root=str(tmp_path))

    assert "项目上下文" in supervisor.memory.project_context
    assert "app.py" in supervisor.memory.project_context
    assert "functions=app" in supervisor.memory.project_context


def test_supervisor_configures_harness_with_project_root(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))

    assert supervisor.harness.state_manager.project_root == tmp_path.resolve()


def test_format_context_without_project_context() -> None:
    supervisor = Supervisor()
    supervisor.memory.set_project_context("")

    assert supervisor.format_context() == "当前没有项目上下文"


def test_refresh_project_context_updates_repo_map(tmp_path: Path) -> None:
    (tmp_path / "first.py").write_text("def first(): pass\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    assert "first.py" in supervisor.format_context()
    assert "second.py" not in supervisor.format_context()

    (tmp_path / "second.py").write_text("def second(): pass\n", encoding="utf-8")
    context = supervisor.refresh_project_context()

    assert context == supervisor.memory.project_context
    assert "second.py" in supervisor.format_context()
    assert "functions=second" in supervisor.format_context()


def test_parse_constraints_disallows_file_reads() -> None:
    supervisor = Supervisor()

    constraints = supervisor._parse_constraints("请基于项目上下文回答，不要读取文件")

    assert "read_file" in constraints.disallowed_tools
    assert "list_dir" in constraints.disallowed_tools
    assert "search_files" in constraints.disallowed_tools
    assert "search_content" in constraints.disallowed_tools


def test_parse_constraints_disallows_all_tools() -> None:
    supervisor = Supervisor()

    constraints = supervisor._parse_constraints("请直接回答，不要调用工具")

    assert "read_file" in constraints.disallowed_tools
    assert "write_file" in constraints.disallowed_tools
    assert "run_shell" in constraints.disallowed_tools
    assert "web_search" in constraints.disallowed_tools


def test_worker_on_step_rejects_disallowed_tool(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    ticket = supervisor.create_ticket("基于上下文回答，不要读取文件")
    supervisor.current_constraints = supervisor._parse_constraints(ticket.description)
    tc = ToolCall(id="call_read", name="read_file", arguments={"path": "README.md"})

    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=tc)

    assert directive.approved is False
    assert directive.inject_message is not None
    assert "不要调用 read_file" in directive.inject_message
    assert "工具被拒绝: read_file" in ticket.log[-1]


def test_worker_on_step_rejects_write_file_for_existing_file(tmp_path: Path) -> None:
    existing = tmp_path / "app.py"
    existing.write_text("VALUE = 1\n", encoding="utf-8")
    supervisor = Supervisor(state_root=str(tmp_path))
    ticket = supervisor.create_ticket("修改 app.py")
    tc = ToolCall(id="call_write", name="write_file", arguments={"path": str(existing), "content": "VALUE = 2\n"})

    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=tc)

    assert directive.approved is False
    assert directive.inject_message is not None
    assert "apply_patch" in directive.inject_message
    assert "工具被拒绝: write_file" in ticket.log[-1]


def test_worker_on_step_allows_write_file_for_new_file(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    ticket = supervisor.create_ticket("创建 app.py")
    target = tmp_path / "app.py"
    tc = ToolCall(id="call_write", name="write_file", arguments={"path": str(target), "content": "VALUE = 1\n"})

    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=tc)

    assert directive.approved is True
    assert "工具调用: write_file" in ticket.log[-1]


def test_worker_on_step_rejects_apply_patch_without_context(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    ticket = supervisor.create_ticket("修改 app.py")
    tc = ToolCall(
        id="call_patch",
        name="apply_patch",
        arguments={
            "path": str(target),
            "patch_text": "--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,1 @@\n-VALUE = 1\n+VALUE = 2\n",
        },
    )

    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=tc)

    assert directive.approved is False
    assert directive.inject_message is not None
    assert "先调用 read_file" in directive.inject_message
    assert "工具被拒绝: apply_patch" in ticket.log[-1]


def test_worker_on_step_allows_apply_patch_after_reading_target(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    ticket = supervisor.create_ticket("修改 app.py")
    read_tc = ToolCall(id="call_read", name="read_file", arguments={"path": str(target)})
    patch_tc = ToolCall(
        id="call_patch",
        name="apply_patch",
        arguments={
            "path": str(target),
            "patch_text": "--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,1 @@\n-VALUE = 1\n+VALUE = 2\n",
        },
    )
    read_result = ToolResult(tool="read_file", ok=True, text="VALUE = 1\n")

    supervisor._worker_on_step(
        "after_tool_call",
        ticket=ticket,
        tool_call=read_tc,
        result=read_result.text,
        tool_result=read_result,
    )
    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=patch_tc)

    assert directive.approved is True
    assert "工具调用: apply_patch" in ticket.log[-1]


def test_worker_on_step_allows_apply_patch_after_search(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    ticket = supervisor.create_ticket("修改 app.py")
    search_tc = ToolCall(id="call_search", name="search_content", arguments={"path": ".", "pattern": "VALUE"})
    patch_tc = ToolCall(
        id="call_patch",
        name="apply_patch",
        arguments={
            "path": str(target),
            "patch_text": "--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,1 @@\n-VALUE = 1\n+VALUE = 2\n",
        },
    )
    search_result = ToolResult(tool="search_content", ok=True, text="app.py:1:> VALUE = 1")

    supervisor._worker_on_step(
        "after_tool_call",
        ticket=ticket,
        tool_call=search_tc,
        result=search_result.text,
        tool_result=search_result,
    )
    directive = supervisor._worker_on_step("before_tool_call", ticket=ticket, tool_call=patch_tc)

    assert directive.approved is True


def test_start_ticket_clears_edit_context(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    first = supervisor.create_ticket("读取 app.py")
    second = supervisor.create_ticket("修改 app.py")
    read_tc = ToolCall(id="call_read", name="read_file", arguments={"path": str(target)})
    read_result = ToolResult(tool="read_file", ok=True, text="VALUE = 1\n")

    supervisor._worker_on_step(
        "after_tool_call",
        ticket=first,
        tool_call=read_tc,
        result=read_result.text,
        tool_result=read_result,
    )
    assert supervisor.context_files_seen

    supervisor.start_ticket(second)

    assert supervisor.context_files_seen == set()
    assert supervisor.context_search_performed is False


def test_handle_prompt_honors_no_read_file_constraint(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    readme = tmp_path / "README.md"
    readme.write_text("secret", encoding="utf-8")

    tc = ToolCall(id="call_read", name="read_file", arguments={"path": str(readme)})
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "回答核心模块"}]'),
        LLMResponse(content="我想读文件", tool_calls=[tc]),
        LLMResponse(content="基于项目上下文回答：cli/supervisor/worker/harness", tool_calls=None),
    ]
    supervisor.worker.llm_service = supervisor.llm_service

    response = supervisor.handle_prompt("请基于项目上下文回答，不要读取文件", model="mock")

    assert "基于项目上下文回答" in response
    assert not supervisor.worker.last_steps[0].tool_results
    assert any("工具被拒绝: read_file" in item for item in supervisor.current_ticket.log)


def test_handle_prompt_creates_ticket() -> None:
    supervisor = Supervisor()
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "模拟响应"
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "测试 prompt"}]')
    response = supervisor.handle_prompt("测试 prompt", model="deepseek-v4-flash")
    assert supervisor.tickets
    assert supervisor.tickets[0].status == "done"
    assert "测试 prompt" in supervisor.tickets[0].description
    assert response is not None


def test_handle_prompt_appends_verification_suggestion(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    target = tmp_path / "generated.py"
    tc = ToolCall(id="call_write", name="write_file", arguments={"path": str(target), "content": "def f():\n    return 1\n"})
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "创建 Python 文件"}]'),
        LLMResponse(content="写入文件", tool_calls=[tc]),
        LLMResponse(content="已完成", tool_calls=None),
    ]
    supervisor.worker.llm_service = supervisor.llm_service

    response = supervisor.handle_prompt("创建 Python 文件", model="mock")

    assert "已完成" in response
    assert "Result" in response
    assert "Changes" in response
    assert "Tests" in response
    assert "pytest -q" in response
    assert "generated.py" in response
    assert response.count("pytest -q") == 1


def test_state_transitions() -> None:
    supervisor = Supervisor()
    assert supervisor.state == SupervisorState.IDLE
    supervisor._transition(SupervisorState.PLANNING)
    assert supervisor.state == SupervisorState.PLANNING
    supervisor._transition(SupervisorState.DISPATCHING)
    assert supervisor.state == SupervisorState.DISPATCHING
    supervisor._transition(SupervisorState.WAITING_WORKER)
    assert supervisor.state == SupervisorState.WAITING_WORKER
    supervisor._transition(SupervisorState.REVIEWING)
    assert supervisor.state == SupervisorState.REVIEWING
    supervisor._transition(SupervisorState.COMPLETE)
    assert supervisor.state == SupervisorState.COMPLETE
    supervisor._transition(SupervisorState.IDLE)
    assert supervisor.state == SupervisorState.IDLE


def test_invalid_state_transition_raises() -> None:
    supervisor = Supervisor()
    try:
        supervisor._transition(SupervisorState.COMPLETE)
        assert False, "应抛出 ValueError"
    except ValueError as e:
        assert "非法状态转换" in str(e)


def test_handle_prompt_full_lifecycle() -> None:
    supervisor = Supervisor()
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "结果"
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "生命周期测试"}]')
    assert supervisor.state == SupervisorState.IDLE
    response = supervisor.handle_prompt("生命周期测试", model="deepseek-v4-flash")
    assert "结果" in response
    assert supervisor.state == SupervisorState.IDLE
    assert supervisor.tickets[0].status == "done"


def test_handle_prompt_failure_state() -> None:
    supervisor = Supervisor()

    def failing_execute(ticket, model, on_step=None):
        raise RuntimeError("模拟失败")

    supervisor.worker.execute_ticket = failing_execute
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "失败测试"}]')
    try:
        supervisor.handle_prompt("失败测试", model="deepseek-v4-flash")
        assert False, "应抛出异常"
    except RuntimeError:
        pass
    assert supervisor.state == SupervisorState.IDLE


def test_handle_prompt_resets_stale_loaded_state(tmp_path: Path) -> None:
    state_manager = StateManager(root=tmp_path)
    state_manager.save_supervisor_state({"state": "planning"})

    supervisor = Supervisor(state_root=str(tmp_path))
    assert supervisor.state == SupervisorState.PLANNING

    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "结果"
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "新任务"}]')

    response = supervisor.handle_prompt("新任务", model="mock")

    assert "结果" in response
    assert supervisor.state == SupervisorState.IDLE


def test_state_persistence(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor._transition(SupervisorState.PLANNING)
    supervisor._transition(SupervisorState.DISPATCHING)

    state = StateManager(root=tmp_path).load_supervisor_state()
    assert state is not None
    assert state["state"] == "dispatching"

    new_supervisor = Supervisor(state_root=str(tmp_path))
    assert new_supervisor.state == SupervisorState.DISPATCHING


def test_load_state_marks_running_tickets_blocked(tmp_path: Path) -> None:
    state_manager = StateManager(root=tmp_path)
    state_manager.save_tickets([
        {
            "ticket_id": "T-001",
            "status": "running",
            "description": "中断前运行中的任务",
            "log": ["Ticket 开始执行"],
        },
        {
            "ticket_id": "T-002",
            "status": "pending",
            "description": "等待任务",
            "log": [],
        },
    ])

    supervisor = Supervisor(state_root=str(tmp_path))

    assert supervisor.tickets[0].status == "blocked"
    assert supervisor.tickets[1].status == "pending"
    assert "上次中断" in supervisor.tickets[0].log[-1]

    persisted = StateManager(root=tmp_path).load_tickets()
    assert persisted[0]["status"] == "blocked"
    assert "上次中断" in persisted[0]["log"][-1]


def test_continue_ticket_resumes_recovered_running_ticket(tmp_path: Path) -> None:
    state_manager = StateManager(root=tmp_path)
    state_manager.save_tickets([
        {
            "ticket_id": "T-001",
            "status": "running",
            "description": "中断前运行中的任务",
            "log": [],
        },
    ])
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.run_existing_ticket = MagicMock(return_value="继续完成")

    result = supervisor.continue_ticket("T-001", model="mock")

    assert result == "继续完成"
    assert supervisor.tickets[0].status == "pending"
    supervisor.run_existing_ticket.assert_called_once_with(supervisor.tickets[0], model="mock")


def test_supervisor_persistence(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "结果"
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "持久化测试"}]')
    supervisor.handle_prompt("持久化测试", model="deepseek-v4-flash")
    assert (tmp_path / ".harness_state" / "tickets.json").exists()
    assert (tmp_path / ".harness_state" / "audit_log.json").exists()

    new_supervisor = Supervisor(state_root=str(tmp_path))
    assert new_supervisor.tickets
    assert new_supervisor.tickets[0].description == "持久化测试"


# --- 子任务拆分测试 ---


def test_parse_plan_valid_json() -> None:
    supervisor = Supervisor()
    plan = supervisor._parse_plan('[{"description": "读取文件"}, {"description": "修改文件"}]')
    assert len(plan) == 2
    assert plan[0]["description"] == "读取文件"
    assert plan[1]["description"] == "修改文件"


def test_parse_plan_invalid_json() -> None:
    supervisor = Supervisor()
    plan = supervisor._parse_plan("这不是 JSON")
    assert plan == []


def test_parse_plan_embedded_json() -> None:
    supervisor = Supervisor()
    text = '好的，以下是计划：\n```json\n[{"description": "步骤1"}, {"description": "步骤2"}]\n```'
    plan = supervisor._parse_plan(text)
    assert len(plan) == 2


def test_plan_task_returns_subtasks() -> None:
    supervisor = Supervisor()
    mock_response = LLMResponse(
        content='[{"description": "读取 auth.ts"}, {"description": "分析超时逻辑"}, {"description": "生成修复"}]'
    )
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    plan = supervisor.plan_task("修复登录超时", model="mock")
    assert len(plan) == 3
    assert plan[0]["description"] == "读取 auth.ts"


def test_plan_task_fallback_on_empty() -> None:
    supervisor = Supervisor()
    mock_response = LLMResponse(content="无法解析的计划")
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    plan = supervisor.plan_task("简单任务", model="mock")
    assert plan == []


def test_should_skip_planning_for_simple_file_edit() -> None:
    supervisor = Supervisor()

    assert supervisor._should_skip_planning("修改 scratch_demo.py，把默认参数从 World 改成 Codex") is True
    assert supervisor._should_skip_planning("重构整个项目架构并修改 scratch_demo.py") is False


def test_handle_prompt_skips_planning_for_simple_file_edit(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = MagicMock(return_value="已完成")
    supervisor.llm_service = MagicMock()

    response = supervisor.handle_prompt("修改 scratch_demo.py，把默认参数从 World 改成 Codex", model="mock")

    assert "已完成" in response
    supervisor.llm_service.chat.assert_not_called()
    assert len(supervisor.tickets) == 1
    assert supervisor.worker.execute_ticket.call_args[0][0].description == "修改 scratch_demo.py，把默认参数从 World 改成 Codex"


def test_handle_prompt_with_subtasks(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"

    mock_response = LLMResponse(
        content='[{"description": "步骤A"}, {"description": "步骤B"}]'
    )
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    response = supervisor.handle_prompt("多步骤任务", model="mock")
    assert "步骤A" in response
    assert "步骤B" in response
    assert "Plan" in response
    assert "1. 步骤A" in response
    assert "2. 步骤B" in response
    assert any("步骤A -> 步骤B" in item for item in supervisor.memory.recent_decisions)
    assert supervisor.state == SupervisorState.IDLE
    assert len(supervisor.tickets) == 3  # 1 parent + 2 children


def test_handle_prompt_single_subtask_fallback(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "结果"

    mock_response = LLMResponse(content='[{"description": "简单任务"}]')
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    response = supervisor.handle_prompt("简单任务", model="mock")
    assert "结果" in response
    assert len(supervisor.tickets) == 1  # parent only, no split


def test_child_ticket_parent_reference(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "ok"

    mock_response = LLMResponse(
        content='[{"description": "子任务1"}, {"description": "子任务2"}]'
    )
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    supervisor.handle_prompt("父任务", model="mock")
    parent = supervisor.tickets[0]
    children = [t for t in supervisor.tickets if t.parent_ticket_id == parent.ticket_id]
    assert len(children) == 2
    assert all(c.parent_ticket_id == parent.ticket_id for c in children)


def test_on_step_records_tool_in_ticket_log(tmp_path) -> None:
    """on_step 回调应将工具调用记录到 ticket 日志"""
    from deepseek_code.worker import StepDirective as SD
    from unittest.mock import MagicMock
    from deepseek_code.llm_service import ToolCall

    supervisor = Supervisor(state_root=str(tmp_path))

    step_log: list[dict] = []
    def record_step(step_type, **kwargs):
        step_log.append({"type": step_type, **kwargs})
        return SD()

    supervisor._worker_on_step = record_step
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=record_step: "完成"
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "子任务"}]')

    supervisor.handle_prompt("测试监督", model="mock")
    # on_step 应该没有被直接调用（因为 execute_ticket 被 mock 了）
    # 但 _worker_on_step 已被替换
    assert len(step_log) == 0  # mock 没走真实流程


def test_on_step_progress_check_injects_message(tmp_path) -> None:
    """progress_check 回调应返回 inject_message"""
    supervisor = Supervisor()
    directive = supervisor._worker_on_step(
        "progress_check",
        ticket=MagicMock(description="写单元测试"),
        iteration=5,
    )
    assert directive.inject_message is not None
    assert "进度检查" in directive.inject_message
    assert "写单元测试" in directive.inject_message


# --- 动态循环测试 ---


def test_parse_evaluation_valid_json() -> None:
    """解析正常的 JSON 评审结果"""
    from deepseek_code.supervisor import EvaluationAction
    supervisor = Supervisor()
    
    result = supervisor._parse_evaluation('{"action": "continue"}')
    assert result.action == "continue"
    
    result = supervisor._parse_evaluation('{"action": "skip_remaining", "reason": "已完成"}')
    assert result.action == "skip_remaining"
    assert result.reason == "已完成"
    
    result = supervisor._parse_evaluation('{"action": "add_tasks", "new_tasks": [{"description": "新任务"}]}')
    assert result.action == "add_tasks"
    assert len(result.new_tasks) == 1


def test_parse_evaluation_invalid_json() -> None:
    """解析非 JSON 格式应返回 continue"""
    supervisor = Supervisor()
    result = supervisor._parse_evaluation("这不是 JSON")
    assert result.action == "continue"


def test_parse_evaluation_missing_action() -> None:
    """缺失 action 字段应返回 continue"""
    supervisor = Supervisor()
    result = supervisor._parse_evaluation('{"reason": "测试"}')
    assert result.action == "continue"


def test_parse_evaluation_embedded_json() -> None:
    """解析嵌入在其他文本中的 JSON"""
    supervisor = Supervisor()
    text = '好的，决策如下：\n```json\n{"action": "re_plan", "reason": "需要调整"}\n```'
    result = supervisor._parse_evaluation(text)
    assert result.action == "re_plan"
    assert result.reason == "需要调整"


def test_create_child_ticket() -> None:
    """创建子 Ticket 并关联父 Ticket"""
    supervisor = Supervisor()
    parent = supervisor.create_ticket("父任务")
    
    child = supervisor._create_child_ticket(parent, {"description": "子任务1"})
    assert child.parent_ticket_id == parent.ticket_id
    assert child.description == "子任务1"
    
    child2 = supervisor._create_child_ticket(parent, {
        "description": "子任务2",
        "acceptance_criteria": "通过测试"
    })
    assert child2.acceptance_criteria == "通过测试"


def test_handle_prompt_dynamic_skip_remaining(tmp_path) -> None:
    """动态跳过剩余任务"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "步骤A"}, {"description": "步骤B"}, {"description": "步骤C"}]'),
        LLMResponse(content='{"action": "skip_remaining", "reason": "步骤A已满足目标"}'),
    ]
    
    response = supervisor.handle_prompt("多步骤任务", model="mock")
    assert "步骤A" in response
    assert "步骤B" not in response
    assert "步骤C" not in response
    assert any("skip_remaining" in item for item in supervisor.memory.recent_decisions)

    parent = supervisor.tickets[0]
    assert "跳过剩余任务" in parent.log[-2]
    cancelled = [ticket for ticket in supervisor.tickets if ticket.status == "cancelled"]
    assert [ticket.description for ticket in cancelled] == ["步骤B", "步骤C"]
    assert all("步骤A已满足目标" in ticket.log[-1] for ticket in cancelled)


def test_handle_prompt_dynamic_add_tasks(tmp_path) -> None:
    """动态追加新任务"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "步骤A"}, {"description": "步骤B"}]'),
        LLMResponse(content='{"action": "add_tasks", "new_tasks": [{"description": "新步骤C"}]}'),
        LLMResponse(content='{"action": "continue"}'),
    ]
    
    response = supervisor.handle_prompt("多步骤任务", model="mock")
    assert "步骤A" in response
    assert "步骤B" in response
    assert "新步骤C" in response
    
    parent = supervisor.tickets[0]
    assert "追加 1 个新任务" in parent.log[-2]


def test_handle_prompt_dynamic_re_plan(tmp_path) -> None:
    """动态重新规划"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "步骤A"}, {"description": "步骤B"}]'),
        LLMResponse(content='{"action": "re_plan", "reason": "需要调整计划"}'),
        LLMResponse(content='[{"description": "新步骤C"}]'),
        LLMResponse(content='{"action": "continue"}'),
    ]
    
    response = supervisor.handle_prompt("多步骤任务", model="mock")
    assert "步骤A" in response
    assert "步骤B" not in response
    assert "新步骤C" in response
    
    parent = supervisor.tickets[0]
    assert "重新规划" in parent.log[-2]


def test_handle_prompt_max_iterations(tmp_path) -> None:
    """达到 Supervisor 最大循环次数"""
    from deepseek_code.supervisor import MAX_SUPERVISOR_ITERATIONS
    supervisor = Supervisor(state_root=str(tmp_path))
    
    call_counts = {"count": 0}
    def mock_execute(ticket, model, on_step=None):
        call_counts["count"] += 1
        return f"完成: {ticket.description}"
    
    supervisor.worker.execute_ticket = mock_execute
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "步骤A"}, {"description": "步骤B"}]'),
    ] + [LLMResponse(content='{"action": "add_tasks", "new_tasks": [{"description": "新步骤"}]}') for _ in range(MAX_SUPERVISOR_ITERATIONS)]
    
    response = supervisor.handle_prompt("无限任务", model="mock")
    
    parent = supervisor.tickets[0]
    assert f"达到 Supervisor 最大循环次数 {MAX_SUPERVISOR_ITERATIONS}" in parent.log[-2]


def test_handle_prompt_no_pending_skips_evaluation(tmp_path) -> None:
    """无 pending 时跳过决策"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "单任务"}]')
    
    response = supervisor.handle_prompt("单任务", model="mock")
    assert "单任务" in response
    
    assert supervisor.llm_service.chat.call_count == 1


def test_handle_prompt_backward_compatibility(tmp_path) -> None:
    """向后兼容：单任务仍正常执行"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: "结果"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = LLMResponse(content='[{"description": "简单任务"}]')
    
    response = supervisor.handle_prompt("简单任务", model="mock")
    assert "结果" in response
    assert len(supervisor.tickets) == 1
    assert supervisor.tickets[0].status == "done"


def test_handle_prompt_injects_previous_results(tmp_path) -> None:
    """将之前的结果注入到记忆"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model, on_step=None: f"完成: {ticket.description}"
    
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.side_effect = [
        LLMResponse(content='[{"description": "步骤A"}, {"description": "步骤B"}]'),
        LLMResponse(content='{"action": "continue"}'),
    ]
    
    response = supervisor.handle_prompt("多步骤任务", model="mock")
    assert "步骤A" in response
    assert "步骤B" in response
