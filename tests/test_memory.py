from deepseek_code.memory import MemoryManager


def test_build_messages_truncates_history() -> None:
    memory = MemoryManager(max_context_tokens=500)
    for i in range(50):
        memory.history.append({"role": "user", "content": f"这是一条较长的测试消息编号{i}用来填充历史记录"})
    messages = memory.build_messages()
    assert messages[0]["role"] == "system"
    has_summary = any("actions_taken" in msg.get("content", "") or "早期对话已裁剪" in msg.get("content", "")
                      for msg in messages if msg["role"] == "system" and msg is not messages[0])
    assert has_summary, "裁剪后应包含摘要消息"


def test_build_system_prompt_includes_tool_descriptions() -> None:
    memory = MemoryManager()
    messages = memory.build_messages()
    system_content = messages[0]["content"]
    assert "read_file" in system_content
    assert "write_file" in system_content
    assert "run_shell" in system_content
    assert "apply_patch" in system_content
    assert "Ralph" in system_content


def test_token_budget_trimming() -> None:
    memory = MemoryManager(max_context_tokens=200)
    for i in range(100):
        memory.history.append({"role": "user", "content": f"长消息{i} " * 20})
    messages = memory.build_messages()
    total = sum(len(m["content"]) // 2 for m in messages)
    assert total < 400, f"裁剪后 token 应远小于 400，实际 {total}"


def test_summarize_history_extracts_files() -> None:
    memory = MemoryManager()
    memory.history = [
        {"role": "assistant", "content": "工具执行结果：已写入 src/test.py"},
        {"role": "assistant", "content": "工具执行结果：已应用补丁到 src/main.py"},
        {"role": "assistant", "content": "工具执行结果：命令执行失败: npm test"},
    ]
    summary = memory._summarize_history(memory.history)
    assert "src/test.py" in summary["content"]
    assert "src/main.py" in summary["content"]


def test_empty_history_build_messages() -> None:
    memory = MemoryManager()
    messages = memory.build_messages()
    assert len(messages) == 1
    assert messages[0]["role"] == "system"


def test_clear_working() -> None:
    memory = MemoryManager()
    memory.history.append({"role": "user", "content": "test"})
    memory.clear_working()
    assert len(memory.history) == 0


def test_no_trimming_when_within_budget() -> None:
    memory = MemoryManager(max_context_tokens=8000)
    for i in range(3):
        memory.history.append({"role": "user", "content": f"短消息{i}"})
    messages = memory.build_messages()
    assert len(messages) == 4  # 1 system + 3 history
