from deepseek_code.llm_service import LLMService, LLMResponse, ToolCall


def test_mock_response_without_api_key() -> None:
    service = LLMService(model="deepseek-v4-flash")
    response = service.chat(messages=[{"role": "user", "content": "hello"}])
    assert response.content is not None
    assert "模拟响应" in response.content
    assert response.tool_calls is None


def test_llm_response_model() -> None:
    resp = LLMResponse(content="你好", tool_calls=None)
    assert resp.content == "你好"

    tc = ToolCall(id="call_1", name="read_file", arguments={"path": "a.txt"})
    resp2 = LLMResponse(content=None, tool_calls=[tc])
    assert resp2.content is None
    assert len(resp2.tool_calls) == 1
    assert resp2.tool_calls[0].name == "read_file"
    assert resp2.tool_calls[0].arguments == {"path": "a.txt"}


def test_llm_response_no_tool_calls() -> None:
    resp = LLMResponse(content="完成")
    assert resp.tool_calls is None
