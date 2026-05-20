from pathlib import Path

from deepseek_code.persistence import StateManager
from deepseek_code.supervisor import Supervisor


def test_state_manager_save_load(tmp_path: Path) -> None:
    manager = StateManager(root=tmp_path)
    tickets = [{"ticket_id": "T-001", "description": "测试", "status": "done"}]
    manager.save_tickets(tickets)
    assert manager.load_tickets() == tickets

    audit = [{"action": "test", "message": "ok"}]
    manager.save_audit_log(audit)
    assert manager.load_audit_log() == audit


def test_supervisor_persistence(tmp_path: Path) -> None:
    supervisor = Supervisor(state_root=str(tmp_path))
    supervisor.worker.execute_ticket = lambda ticket, model: "结果"
    supervisor.handle_prompt("持久化测试", model="deepseek-v4-flash")
    assert (tmp_path / ".harness_state" / "tickets.json").exists()
    assert (tmp_path / ".harness_state" / "audit_log.json").exists()

    new_supervisor = Supervisor(state_root=str(tmp_path))
    assert new_supervisor.tickets
    assert new_supervisor.tickets[0].description == "持久化测试"