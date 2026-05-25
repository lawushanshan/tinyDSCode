from unittest.mock import MagicMock, patch

from deepseek_code.harness import Harness
from deepseek_code.llm_service import LLMResponse, ToolCall, LLMService
from deepseek_code.memory import MemoryManager
from deepseek_code.supervisor import Ticket
from deepseek_code.worker import Worker, StepDirective


def _make_worker(tmp_path=None) -> Worker:
    harness = Harness(state_root=str(tmp_path) if tmp_path else None)
    llm_service = LLMService(model="mock")
    memory = MemoryManager()
    return Worker(harness=harness, llm_service=llm_service, memory=memory)


def test_execute_ticket_single_response(tmp_path) -> None:
    worker = _make_worker(tmp_path)
    mock_response = LLMResponse(content="任务完成，无需工具调用。", tool_calls=None)
    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = mock_response

    ticket = Ticket(ticket_id="T-001", description="测试任务")
    result = worker.execute_ticket(ticket)
    assert result == "任务完成，无需工具调用。"
    assert ticket.status == "done"


def test_execute_ticket_with_tool_calls(tmp_path) -> None:
    worker = _make_worker(tmp_path)
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello", encoding="utf-8")
    tc = ToolCall(id="call_1", name="read_file", arguments={"path": str(test_file)})
    response_with_tool = LLMResponse(content="让我读取文件", tool_calls=[tc])
    response_final = LLMResponse(content="文件内容是空的", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [response_with_tool, response_final]

    ticket = Ticket(ticket_id="T-001", description="读取文件")
    result = worker.execute_ticket(ticket)
    assert result == "文件内容是空的"
    assert ticket.status == "done"
    assert worker.llm_service.chat.call_count == 2
    assert len(worker.last_steps) == 2
    assert worker.last_steps[0].iteration == 1
    assert worker.last_steps[0].assistant_content == "让我读取文件"
    assert worker.last_steps[0].tool_calls == [tc]
    assert worker.last_steps[0].tool_results[0].ok is True
    assert worker.last_steps[1].done_reason == "assistant_final"


def test_agent_steps_reset_between_tickets(tmp_path) -> None:
    worker = _make_worker(tmp_path)
    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = LLMResponse(content="完成", tool_calls=None)

    first = Ticket(ticket_id="T-001", description="第一项")
    second = Ticket(ticket_id="T-002", description="第二项")

    worker.execute_ticket(first)
    assert len(worker.last_steps) == 1
    assert worker.last_steps[0].ticket_id == "T-001"

    worker.execute_ticket(second)
    assert len(worker.last_steps) == 1
    assert worker.last_steps[0].ticket_id == "T-002"
    assert worker.last_steps[0].done_reason == "assistant_final"


def test_max_loop_iterations(tmp_path) -> None:
    worker = _make_worker(tmp_path)
    infinite_tool = ToolCall(id="call_1", name="list_dir", arguments={"path": str(tmp_path)})
    always_tool = LLMResponse(content="继续操作", tool_calls=[infinite_tool])

    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = always_tool

    ticket = Ticket(ticket_id="T-001", description="无限循环测试", max_loop_iterations=3)
    result = worker.execute_ticket(ticket)
    assert worker.llm_service.chat.call_count == 3
    assert result is not None


def test_consecutive_no_progress_terminates(tmp_path) -> None:
    worker = _make_worker(tmp_path)
    same_response = LLMResponse(content="我不知道该做什么", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = same_response

    ticket = Ticket(ticket_id="T-001", description="无进展测试", max_loop_iterations=10)
    result = worker.execute_ticket(ticket)
    assert "无进展" in result or worker.llm_service.chat.call_count <= 3


def test_worker_continues_after_tool_failure(tmp_path) -> None:
    """Ralph 循环：工具执行失败后，错误信息反馈给 LLM，LLM 可以继续尝试"""
    worker = _make_worker(tmp_path)

    # 第一次：LLM 调用一个不存在的 shell 命令（会失败）
    fail_tc = ToolCall(id="call_1", name="run_shell", arguments={"command": "nonexistent_cmd_xyz"})
    response_with_bad_tool = LLMResponse(content="我来执行命令", tool_calls=[fail_tc])

    # 第二次：LLM 收到错误信息后，换一种方式完成任务（无工具调用）
    response_final = LLMResponse(content="已改用其他方式完成", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [response_with_bad_tool, response_final]

    ticket = Ticket(ticket_id="T-002", description="容错测试")
    result = worker.execute_ticket(ticket)

    # 应该调用了两次 LLM：第一次工具失败，第二次 LLM 改变策略
    assert worker.llm_service.chat.call_count == 2
    assert result == "已改用其他方式完成"
    assert ticket.status == "done"


def test_worker_retries_after_shell_error(tmp_path) -> None:
    """Ralph 循环：shell 命令失败后 LLM 重试正确命令"""
    worker = _make_worker(tmp_path)

    # 第一次：调用 ps aux（Windows 上不可用）
    fail_tc = ToolCall(id="call_1", name="run_shell", arguments={"command": "ps aux"})
    response_fail = LLMResponse(content="查看进程", tool_calls=[fail_tc])

    # 第二次：LLM 收到错误后改用 tasklist（Windows 命令）
    retry_tc = ToolCall(id="call_2", name="run_shell", arguments={"command": "tasklist"})
    response_retry = LLMResponse(content="换用 tasklist", tool_calls=[retry_tc])

    # 第三次：完成任务
    response_done = LLMResponse(content="已获取进程列表", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [response_fail, response_retry, response_done]

    ticket = Ticket(ticket_id="T-003", description="重试测试", max_loop_iterations=5)
    result = worker.execute_ticket(ticket)

    assert worker.llm_service.chat.call_count == 3
    assert result == "已获取进程列表"
    assert ticket.status == "done"


def test_identical_tool_calls_terminate(tmp_path) -> None:
    """连续相同工具调用应被检测并终止循环"""
    worker = _make_worker(tmp_path)
    same_tc = ToolCall(id="call_1", name="list_dir", arguments={"path": str(tmp_path)})
    always_same = LLMResponse(content=None, tool_calls=[same_tc])

    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = always_same

    ticket = Ticket(ticket_id="T-004", description="重复调用测试", max_loop_iterations=10)
    result = worker.execute_ticket(ticket)
    assert "重复" in result or "终止" in result
    # 应在第 4 次循环终止（连续 3 次相同后触发）
    assert worker.llm_service.chat.call_count <= 4
    assert worker.last_steps[-1].done_reason == "repeated_tool_calls"


def test_different_tool_calls_reset_counter(tmp_path) -> None:
    """不同的工具调用应重置重复计数器，不误终止"""
    worker = _make_worker(tmp_path)

    tc1 = ToolCall(id="c1", name="list_dir", arguments={"path": str(tmp_path)})
    tc2 = ToolCall(id="c2", name="read_file", arguments={"path": str(tmp_path / "test.txt")})
    tc3 = ToolCall(id="c3", name="list_dir", arguments={"path": str(tmp_path)})
    response_final = LLMResponse(content="完成", tool_calls=None)

    r1 = LLMResponse(content=None, tool_calls=[tc1])
    r2 = LLMResponse(content=None, tool_calls=[tc2])
    r3 = LLMResponse(content=None, tool_calls=[tc3])
    r4 = LLMResponse(content="完成", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [r1, r2, r3, response_final]

    ticket = Ticket(ticket_id="T-005", description="混合调用测试", max_loop_iterations=10)
    result = worker.execute_ticket(ticket)
    assert result == "完成"
    assert ticket.status == "done"
    assert worker.llm_service.chat.call_count == 4


def test_on_step_reject_tool_call(tmp_path) -> None:
    """Supervisor 拒绝工具调用时，Worker 跳过并继续循环"""
    worker = _make_worker(tmp_path)
    call_count = {"n": 0}

    def reject_first_tool(step_type, **kwargs):
        call_count["n"] += 1
        if step_type == "before_tool_call" and call_count["n"] == 1:
            return StepDirective(approved=False, inject_message="不要执行这个操作，请换一种方式。")
        return StepDirective()

    (tmp_path / "test.txt").write_text("ok", encoding="utf-8")
    tc_rejected = ToolCall(id="c1", name="run_shell", arguments={"command": "rm -rf /"})
    tc_alternative = ToolCall(id="c2", name="read_file", arguments={"path": str(tmp_path / "test.txt")})
    response_with_rejected = LLMResponse(content="尝试危险操作", tool_calls=[tc_rejected])
    response_with_ok = LLMResponse(content="换读文件", tool_calls=[tc_alternative])
    response_final = LLMResponse(content="已完成", tool_calls=None)

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [response_with_rejected, response_with_ok, response_final]

    ticket = Ticket(ticket_id="T-006", description="拒绝测试", max_loop_iterations=5)
    result = worker.execute_ticket(ticket, on_step=reject_first_tool)
    assert result == "已完成"
    assert ticket.status == "done"


def test_on_step_receives_ticket_for_tool_events(tmp_path) -> None:
    """工具调用前后回调应携带当前 Ticket，便于 Supervisor 记录日志"""
    worker = _make_worker(tmp_path)
    seen: list[tuple[str, Ticket | None, object | None]] = []

    def record_ticket(step_type, **kwargs):
        if step_type in {"before_tool_call", "after_tool_call"}:
            seen.append((step_type, kwargs.get("ticket"), kwargs.get("tool_result")))
        return StepDirective()

    test_file = tmp_path / "test.txt"
    test_file.write_text("ok", encoding="utf-8")
    tc = ToolCall(id="c1", name="read_file", arguments={"path": str(test_file)})
    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = [
        LLMResponse(content="读取文件", tool_calls=[tc]),
        LLMResponse(content="完成", tool_calls=None),
    ]

    ticket = Ticket(ticket_id="T-010", description="读取文件")
    result = worker.execute_ticket(ticket, on_step=record_ticket)

    assert result == "完成"
    assert seen[0] == ("before_tool_call", ticket, None)
    assert seen[1][0] == "after_tool_call"
    assert seen[1][1] is ticket
    assert seen[1][2].ok is True
    assert seen[1][2].tool == "read_file"


def test_on_step_abort(tmp_path) -> None:
    """Supervisor 中止任务时，Worker 立即停止"""
    worker = _make_worker(tmp_path)

    def abort_on_first(step_type, **kwargs):
        if step_type == "before_tool_call":
            return StepDirective(abort=True)
        return StepDirective()

    tc = ToolCall(id="c1", name="read_file", arguments={"path": str(tmp_path / "x.txt")})
    response = LLMResponse(content="读文件", tool_calls=[tc])

    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = response

    ticket = Ticket(ticket_id="T-007", description="中止测试", max_loop_iterations=5)
    result = worker.execute_ticket(ticket, on_step=abort_on_first)
    assert "中止" in result
    assert ticket.status == "failed"


def test_on_step_progress_check(tmp_path) -> None:
    """进度检查在指定间隔注入消息"""
    worker = _make_worker(tmp_path)
    injected: list[str] = []

    def track_progress(step_type, **kwargs):
        if step_type == "progress_check":
            injected.append(kwargs.get("iteration", 0))
            return StepDirective(inject_message=f"第{kwargs.get('iteration')}次检查")
        return StepDirective()

    tc1 = ToolCall(id="c1", name="list_dir", arguments={"path": str(tmp_path)})
    tc2 = ToolCall(id="c2", name="read_file", arguments={"path": str(tmp_path / "test.txt")})
    responses = [
        LLMResponse(content="继续", tool_calls=[tc1]),
        LLMResponse(content="继续", tool_calls=[tc2]),
        LLMResponse(content="继续", tool_calls=[tc1]),
        LLMResponse(content="继续", tool_calls=[tc2]),
        LLMResponse(content="继续", tool_calls=[tc1]),
        LLMResponse(content="完成", tool_calls=None),
    ]

    worker.llm_service = MagicMock()
    worker.llm_service.chat.side_effect = responses

    ticket = Ticket(ticket_id="T-008", description="进度检查测试", max_loop_iterations=10)
    result = worker.execute_ticket(ticket, on_step=track_progress)
    assert result == "完成"
    # PROGRESS_CHECK_INTERVAL=5, 第 5 次循环会触发进度检查
    assert 5 in injected


def test_no_on_step_backward_compatible(tmp_path) -> None:
    """不传 on_step 时行为与之前完全一致"""
    worker = _make_worker(tmp_path)
    mock_response = LLMResponse(content="直接完成", tool_calls=None)
    worker.llm_service = MagicMock()
    worker.llm_service.chat.return_value = mock_response

    ticket = Ticket(ticket_id="T-009", description="兼容测试")
    result = worker.execute_ticket(ticket)
    assert result == "直接完成"
    assert ticket.status == "done"
