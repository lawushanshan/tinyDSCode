"""端到端集成测试 — mock LLM 模拟完整 tool_calls 链"""
from pathlib import Path
from unittest.mock import MagicMock

from deepseek_code.llm_service import LLMResponse, ToolCall, LLMService
from deepseek_code.supervisor import Supervisor


def test_e2e_single_task_read_and_summarize(tmp_path: Path) -> None:
    """模拟完整流程：LLM 先读取文件，再返回总结"""
    supervisor = Supervisor(state_root=str(tmp_path))

    test_file = tmp_path / "hello.py"
    test_file.write_text("print('hello world')\n", encoding="utf-8")

    read_tc = ToolCall(id="call_1", name="read_file", arguments={"path": str(test_file)})
    final_response = LLMResponse(
        content="文件 hello.py 包含一行代码：print('hello world')",
        tool_calls=None,
    )

    mock_service = MagicMock(spec=LLMService)
    mock_service.chat.side_effect = [
        LLMResponse(content="让我读取文件", tool_calls=[read_tc]),
        final_response,
    ]
    supervisor.llm_service = mock_service
    supervisor.worker.llm_service = mock_service

    result = supervisor.handle_prompt("分析 hello.py", model="mock")

    assert "hello" in result.lower() or "print" in result
    assert supervisor.tickets[0].status == "done"
    assert supervisor.state == __import__("deepseek_code.supervisor", fromlist=["SupervisorState"]).SupervisorState.IDLE
    assert mock_service.chat.call_count == 2


def test_e2e_subtask_workflow(tmp_path: Path) -> None:
    """模拟子任务拆分 + 依次执行"""
    supervisor = Supervisor(state_root=str(tmp_path))

    plan_response = LLMResponse(
        content='[{"description": "创建文件"}, {"description": "验证文件"}]',
        tool_calls=None,
    )
    file_a = tmp_path / "test.txt"
    write_tc = ToolCall(id="call_1", name="write_file", arguments={"path": str(file_a), "content": "data"})
    read_tc = ToolCall(id="call_2", name="read_file", arguments={"path": str(file_a)})

    mock_service = MagicMock(spec=LLMService)
    mock_service.chat.side_effect = [
        plan_response,
        LLMResponse(content="创建中", tool_calls=[write_tc]),
        LLMResponse(content="文件已创建", tool_calls=None),
        LLMResponse(content="验证中", tool_calls=[read_tc]),
        LLMResponse(content="验证通过", tool_calls=None),
    ]
    supervisor.llm_service = mock_service
    supervisor.worker.llm_service = mock_service

    result = supervisor.handle_prompt("创建并验证文件", model="mock")

    assert file_a.exists()
    assert file_a.read_text(encoding="utf-8") == "data"
    assert len(supervisor.tickets) == 3  # 1 parent + 2 children
    assert supervisor.state == __import__("deepseek_code.supervisor", fromlist=["SupervisorState"]).SupervisorState.IDLE


def test_e2e_persistence_round_trip(tmp_path: Path) -> None:
    """状态持久化 + 恢复"""
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model: "持久化结果"
    supervisor.handle_prompt("持久化测试", model="mock")

    supervisor2 = Supervisor(state_root=str(tmp_path))
    assert len(supervisor2.tickets) == 1
    assert supervisor2.tickets[0].description == "持久化测试"
    assert supervisor2.tickets[0].status == "done"
    assert (tmp_path / ".harness_state" / "supervisor.json").exists()


def test_e2e_plan_fallback_to_single_ticket(tmp_path: Path) -> None:
    """plan_task 解析失败时降级为单 Ticket"""
    supervisor = Supervisor(state_root=str(tmp_path))

    mock_service = MagicMock(spec=LLMService)
    mock_service.chat.return_value = LLMResponse(content="无法解析", tool_calls=None)
    supervisor.llm_service = mock_service
    supervisor.worker.llm_service = mock_service
    supervisor.worker.execute_ticket = lambda ticket, model: "降级结果"

    result = supervisor.handle_prompt("简单任务", model="mock")

    assert "降级结果" in result
    assert len(supervisor.tickets) == 1
