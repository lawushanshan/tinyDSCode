from unittest.mock import MagicMock, patch

from deepseek_code.harness import Harness
from deepseek_code.llm_service import LLMResponse, ToolCall, LLMService
from deepseek_code.memory import MemoryManager
from deepseek_code.supervisor import Ticket
from deepseek_code.worker import Worker


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
