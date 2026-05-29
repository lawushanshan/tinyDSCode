from deepseek_code.memory import MemoryManager


def test_build_messages_truncates_history() -> None:
    memory = MemoryManager(max_context_tokens=500)
    for i in range(50):
        memory.history.append({"role": "user", "content": f"long history message {i} for trimming"})

    messages = memory.build_messages()

    assert messages[0]["role"] == "system"
    has_summary = any(
        "actions_taken" in msg.get("content", "")
        for msg in messages
        if msg["role"] == "system" and msg is not messages[0]
    )
    assert has_summary


def test_build_system_prompt_includes_tool_descriptions() -> None:
    memory = MemoryManager()
    messages = memory.build_messages()
    system_content = messages[0]["content"]

    assert "read_file" in system_content
    assert "write_file" in system_content
    assert "run_shell" in system_content
    assert "apply_patch" in system_content
    assert "Ralph" in system_content
    assert "Repo Map" in system_content
    assert "test_commands" in system_content
    assert "Python" in system_content


def test_token_budget_trimming() -> None:
    memory = MemoryManager(max_context_tokens=200)
    for i in range(100):
        memory.history.append({"role": "user", "content": f"long message {i} " * 20})

    messages = memory.build_messages()
    total = sum(len(m["content"]) // 2 for m in messages)
    system_tokens = len(messages[0]["content"]) // 2

    assert len(messages) <= 3
    assert total <= system_tokens + 120


def test_summarize_history_extracts_files() -> None:
    memory = MemoryManager()
    memory.history = [
        {"role": "assistant", "content": "工具执行结果：已写入 src/test.py"},
        {"role": "assistant", "content": "工具执行结果：已应用补丁到 src/main.py"},
        {"role": "assistant", "content": "工具执行结果：命令执行失败 npm test"},
    ]

    summary = memory._summarize_history(memory.history)

    assert "src/test.py" in summary["content"]
    assert "src/main.py" in summary["content"]


def test_empty_history_build_messages() -> None:
    memory = MemoryManager()

    messages = memory.build_messages()

    assert len(messages) == 1
    assert messages[0]["role"] == "system"


def test_build_messages_includes_project_context() -> None:
    memory = MemoryManager()
    memory.set_project_context("## Project Context\n- src/app.py")

    messages = memory.build_messages()

    assert len(messages) == 2
    assert messages[1]["role"] == "system"
    assert "src/app.py" in messages[1]["content"]


def test_build_messages_includes_editor_context() -> None:
    memory = MemoryManager()
    memory.set_editor_context("## Editor Context\n- current_file: src/app.py:12")

    messages = memory.build_messages()

    assert len(messages) == 2
    assert messages[1]["role"] == "system"
    assert "Editor Context" in messages[1]["content"]
    assert "src/app.py:12" in messages[1]["content"]


def test_build_messages_includes_recent_decisions() -> None:
    memory = MemoryManager()
    memory.record_decision("plan", "read file -> patch file")

    messages = memory.build_messages()

    assert len(messages) == 2
    assert messages[1]["role"] == "system"
    assert "Recent Decisions" in messages[1]["content"]
    assert "read file -> patch file" in messages[1]["content"]


def test_build_messages_includes_session_notes() -> None:
    memory = MemoryManager()
    memory.set_session_notes([
        {"category": "decision", "text": "编辑前必须先做定向上下文获取", "source": "manual"},
    ])

    messages = memory.build_messages()

    assert len(messages) == 2
    assert messages[1]["role"] == "system"
    assert "Session Notes" in messages[1]["content"]
    assert "[decision] 编辑前必须先做定向上下文获取 (manual)" in messages[1]["content"]


def test_session_notes_are_compacted_for_context() -> None:
    memory = MemoryManager()
    memory.set_session_notes([
        {"category": "decision", "text": f"note {index}", "source": f"T-{index:03d}"}
        for index in range(15)
    ])

    messages = memory.build_messages()
    notes_message = messages[1]["content"]

    assert "note 2" not in notes_message
    assert "note 7" in notes_message
    assert "note 14" in notes_message


def test_clear_working() -> None:
    memory = MemoryManager()
    memory.history.append({"role": "user", "content": "test"})

    memory.clear_working()

    assert len(memory.history) == 0


def test_no_trimming_when_within_budget() -> None:
    memory = MemoryManager(max_context_tokens=8000)
    for i in range(3):
        memory.history.append({"role": "user", "content": f"short message {i}"})

    messages = memory.build_messages()

    assert len(messages) == 4
