from unittest.mock import patch
from deepseek_code.llm_service import LLMService, LLMResponse, ToolCall


def test_mock_response_without_api_key() -> None:
    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
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


def test_llm_service_malformed_tool_args_ignored() -> None:
    """LLM 返回的 tool call 参数 JSON 不完整时，应跳过而不崩溃"""
    service = LLMService(model="mock")
    mock_message = type("Msg", (), {
        "content": None,
        "tool_calls": [
            type("TC", (), {
                "id": "c1",
                "function": type("Fn", (), {
                    "name": "read_file",
                    "arguments": '{"path": "/tmp/test.txt',  # 不完整 JSON
                })(),
            })(),
            type("TC", (), {
                "id": "c2",
                "function": type("Fn", (), {
                    "name": "write_file",
                    "arguments": '{"path": "/tmp/ok.txt", "content": "hello"}',
                })(),
            })(),
        ],
    })()
    mock_choice = type("Choice", (), {"message": mock_message})()
    mock_response = type("Resp", (), {"choices": [mock_choice]})()

    service._client = type("C", (), {"chat": type("Chat", (), {
        "completions": type("Comp", (), {"create": staticmethod(lambda **kw: mock_response)})(),
    })()})()

    result = service.chat(messages=[{"role": "user", "content": "test"}])
    assert result.tool_calls is not None
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "write_file"


def test_llm_service_all_tool_args_malformed() -> None:
    """所有 tool call 参数都解析失败时，返回提示文本而非崩溃"""
    service = LLMService(model="mock")
    mock_message = type("Msg", (), {
        "content": None,
        "tool_calls": [
            type("TC", (), {
                "id": "c1",
                "function": type("Fn", (), {
                    "name": "read_file",
                    "arguments": 'NOT JSON AT ALL',
                })(),
            })(),
        ],
    })()
    mock_choice = type("Choice", (), {"message": mock_message})()
    mock_response = type("Resp", (), {"choices": [mock_choice]})()

    service._client = type("C", (), {"chat": type("Chat", (), {
        "completions": type("Comp", (), {"create": staticmethod(lambda **kw: mock_response)})(),
    })()})()

    result = service.chat(messages=[{"role": "user", "content": "test"}])
    assert result.tool_calls is None
    assert "工具调用参数格式错误" in result.content
