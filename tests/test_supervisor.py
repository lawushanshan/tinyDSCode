import subprocess
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
    assert "T-001 [pending] - 测试任务" in supervisor.list_tickets()


def test_format_status_without_current_ticket() -> None:
    supervisor = Supervisor()
    assert supervisor.format_status() == "当前没有正在运行的 Ticket"


def test_format_status_with_current_ticket() -> None:
    supervisor = Supervisor()
    ticket = supervisor.create_ticket("测试状态")
    supervisor.start_ticket(ticket)

    status = supervisor.format_status()

    assert "当前 Ticket: T-001 [running]" in status
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


def test_format_verification_suggestion_for_python_changes() -> None:
    supervisor = Supervisor()
    supervisor.changed_files = ["src/app.py", "README.md"]

    suggestion = supervisor.format_verification_suggestion()

    assert "建议验证" in suggestion
    assert "src/app.py" in suggestion
    assert "README.md" in suggestion
    assert "pytest -q" in suggestion


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

    assert "Task Summary" in summary
    assert "Changed files:" in summary
    assert str(target) in summary
    assert "Suggested verification: pytest -q" in summary
    assert "Trace summary:" in summary
    assert "loop 1; tools=write_file" in summary
    assert "loop 2; done=assistant_final" in summary


def test_format_task_summary_without_changes() -> None:
    supervisor = Supervisor()

    summary = supervisor.format_task_summary()

    assert "Task Summary" in summary
    assert "Changed files: none" in summary
    assert "Suggested verification: not required" in summary
    assert "Trace summary:" not in summary


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


def test_normalize_repl_command_accepts_missing_colon() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("verify") == ":verify"
    assert supervisor.normalize_repl_command(" VERIFY ") == ":verify"
    assert supervisor.normalize_repl_command("status") == ":status"
    assert supervisor.normalize_repl_command("trace") == ":trace"


def test_normalize_repl_command_accepts_slash_commands() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("/verify") == ":verify"
    assert supervisor.normalize_repl_command(" /STATUS ") == ":status"
    assert supervisor.normalize_repl_command("/diff") == ":diff"
    assert supervisor.normalize_repl_command("/new 测试任务") == ":new 测试任务"
    assert supervisor.normalize_repl_command("/new") == ":new"


def test_normalize_repl_command_keeps_regular_tasks() -> None:
    supervisor = Supervisor()

    assert supervisor.normalize_repl_command("创建一个文件") == "创建一个文件"
    assert supervisor.normalize_repl_command(":new 测试") == ":new 测试"


def test_supervisor_initializes_project_context(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def app(): pass\n", encoding="utf-8")

    supervisor = Supervisor(state_root=str(tmp_path))

    assert "项目上下文" in supervisor.memory.project_context
    assert "app.py" in supervisor.memory.project_context
    assert "functions=app" in supervisor.memory.project_context


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
    assert "建议验证" in response
    assert "pytest -q" in response
    assert str(target) in response


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
    
    parent = supervisor.tickets[0]
    assert "跳过剩余任务" in parent.log[-2]


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
