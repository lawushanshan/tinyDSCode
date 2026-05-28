from __future__ import annotations
import json
from pathlib import Path
from typing import Any


class StateManager:
    def __init__(self, root: Path | str | None = None) -> None:
        base = (Path(root) if root is not None else Path.cwd()).resolve()
        self.project_root = base
        # always store state under a .harness_state directory
        self.root = base / ".harness_state"
        self.root.mkdir(parents=True, exist_ok=True)
        self.tickets_file = self.root / "tickets.json"
        self.audit_file = self.root / "audit_log.json"
        self.session_notes_file = self.root / "session_notes.json"

    def save_tickets(self, tickets: list[dict[str, Any]]) -> None:
        self._write_json(self.tickets_file, tickets)

    def load_tickets(self) -> list[dict[str, Any]]:
        if not self.tickets_file.exists():
            return []
        return self._read_json(self.tickets_file)

    def save_audit_log(self, audit_log: list[dict[str, Any]]) -> None:
        # 限制审计日志条目数，避免无限增长（保留最近 N 条）
        max_entries = 1000
        if isinstance(audit_log, list):
            trimmed = audit_log[-max_entries:]
        else:
            trimmed = audit_log
        self._write_json(self.audit_file, trimmed)

    def load_audit_log(self) -> list[dict[str, Any]]:
        if not self.audit_file.exists():
            return []
        return self._read_json(self.audit_file)

    def save_session_notes(self, notes: list[dict[str, Any]]) -> None:
        seen: set[tuple[str, str]] = set()
        compact: list[dict[str, Any]] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            category = str(note.get("category", "general")).strip() or "general"
            text = str(note.get("text", "")).strip()
            if not text:
                continue
            key = (category, text)
            if key in seen:
                continue
            seen.add(key)
            compact.append({
                "category": category,
                "text": text,
                "source": str(note.get("source", "")).strip(),
                "created_at": str(note.get("created_at", "")).strip(),
            })
        self._write_json(self.session_notes_file, compact[-200:])

    def load_session_notes(self) -> list[dict[str, Any]]:
        if not self.session_notes_file.exists():
            return []
        data = self._read_json(self.session_notes_file)
        return data if isinstance(data, list) else []

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def save_supervisor_state(self, state: dict[str, Any]) -> None:
        self._write_json(self.root / "supervisor.json", state)

    def load_supervisor_state(self) -> dict[str, Any] | None:
        path = self.root / "supervisor.json"
        if not path.exists():
            return None
        return self._read_json(path)
