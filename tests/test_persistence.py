from pathlib import Path
from unittest.mock import MagicMock

from deepseek_code.llm_service import LLMResponse
from deepseek_code.persistence import StateManager
from deepseek_code.supervisor import Supervisor


def test_state_manager_save_load(tmp_path: Path) -> None:
    manager = StateManager(root=tmp_path)
    assert manager.project_root == tmp_path
    tickets = [{"ticket_id": "T-001", "description": "测试", "status": "done"}]
    manager.save_tickets(tickets)
    assert manager.load_tickets() == tickets

    audit = [{"action": "test", "message": "ok"}]
    manager.save_audit_log(audit)
    assert manager.load_audit_log() == audit

    notes = [
        {"category": "decision", "text": "保持 rollback 只读", "source": "manual"},
        {"category": "decision", "text": "保持 rollback 只读", "source": "duplicate"},
    ]
    manager.save_session_notes(notes)
    assert manager.load_session_notes() == [
        {
            "category": "decision",
            "text": "保持 rollback 只读",
            "source": "manual",
            "created_at": "",
        }
    ]


def test_session_notes_are_pruned(tmp_path: Path) -> None:
    manager = StateManager(root=tmp_path)
    manager.save_session_notes([
        {"category": "note", "text": f"note {index}"}
        for index in range(205)
    ])

    notes = manager.load_session_notes()

    assert len(notes) == 200
    assert notes[0]["text"] == "note 5"
    assert notes[-1]["text"] == "note 204"


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
