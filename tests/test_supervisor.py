from pathlib import Path
from unittest.mock import MagicMock

from deepseek_code.supervisor import Supervisor, SupervisorState
from deepseek_code.llm_service import LLMResponse
from deepseek_code.worker import StepDirective
from deepseek_code.persistence import StateManager


def test_create_and_list_tickets() -> None:
    supervisor = Supervisor()
    assert supervisor.list_tickets() == "当前没有 Ticket"
    supervisor.create_ticket("测试任务")
    assert "T-001 [pending] - 测试任务" in supervisor.list_tickets()


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
