from pathlib import Path
from unittest.mock import MagicMock

from deepseek_code.supervisor import Supervisor, SupervisorState
from deepseek_code.llm_service import LLMResponse
from deepseek_code.persistence import StateManager


def test_create_and_list_tickets() -> None:
    supervisor = Supervisor()
    assert supervisor.list_tickets() == "当前没有 Ticket"
    supervisor.create_ticket("测试任务")
    assert "T-001 [pending] - 测试任务" in supervisor.list_tickets()


def test_handle_prompt_creates_ticket() -> None:
    supervisor = Supervisor()
    supervisor.worker.execute_ticket = lambda ticket, model: "模拟响应"
    response = supervisor.handle_prompt("测试 prompt", model="deepseek-v4-flash")
    assert supervisor.tickets
    assert supervisor.tickets[0].status == "done"
    assert "测试 prompt" in supervisor.tickets[0].description
    assert response is not None


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
    supervisor.worker.execute_ticket = lambda ticket, model: "结果"
    assert supervisor.state == SupervisorState.IDLE
    response = supervisor.handle_prompt("生命周期测试", model="deepseek-v4-flash")
    assert "结果" in response
    assert supervisor.state == SupervisorState.IDLE
    assert supervisor.tickets[0].status == "done"


def test_handle_prompt_failure_state() -> None:
    supervisor = Supervisor()

    def failing_execute(ticket, model):
        raise RuntimeError("模拟失败")

    supervisor.worker.execute_ticket = failing_execute
    try:
        supervisor.handle_prompt("失败测试", model="deepseek-v4-flash")
        assert False, "应抛出异常"
    except RuntimeError:
        pass
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
    supervisor.worker.execute_ticket = lambda ticket, model: "结果"
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


def test_handle_prompt_with_subtasks(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model: f"完成: {ticket.description}"

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
    supervisor.worker.execute_ticket = lambda ticket, model: "结果"

    mock_response = LLMResponse(content='[{"description": "简单任务"}]')
    supervisor.llm_service = MagicMock()
    supervisor.llm_service.chat.return_value = mock_response

    response = supervisor.handle_prompt("简单任务", model="mock")
    assert "结果" in response
    assert len(supervisor.tickets) == 1  # parent only, no split


def test_child_ticket_parent_reference(tmp_path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model: "ok"

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
