# LLM 服务模块

## 概述

LLM 服务模块封装了 LLM API 调用，支持 OpenAI 兼容模式，提供 Function Calling 功能，并内置模拟响应模式用于开发调试。

## 组件

### LLMService
- **位置**: [llm_service.py](../../src/deepseek_code/llm_service.py)
- **用途**: 封装 LLM API 调用
- **关键类**:
  - `ToolCall`: 工具调用数据结构
  - `LLMResponse`: LLM 响应数据结构
  - `LLMService`: LLM 服务类

### 数据结构

#### ToolCall
- **字段**:
  - `id`: 工具调用 ID
  - `name`: 工具名称
  - `arguments`: 工具参数（字典）
- **用途**: 表示 LLM 返回的工具调用

#### LLMResponse
- **字段**:
  - `content`: 文本内容（可选）
  - `tool_calls`: 工具调用列表（可选）
- **用途**: 表示 LLM 的完整响应

### API 配置
- **环境变量**:
  - `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`: API 密钥
  - `DEEPSEEK_API_BASE` / `OPENAI_API_BASE`: API 地址
  - `DEEPSEEK_API_VERSION` / `OPENAI_API_VERSION`: API 版本
  - `DEEPSEEK_API_TYPE` / `OPENAI_API_TYPE`: API 类型
- **配置来源**:
  1. 构造函数传入的 `env` 参数
  2. 环境变量
- **优先级**: 构造函数参数 > 环境变量

### OpenAI 客户端
- **创建**: `_create_client()`
- **库**: `openai`
- **参数**:
  - `api_key`: API 密钥
  - `base_url`: API 地址（可选）
  - `default_headers`: API 版本（可选）
- **兼容性**: 支持 DeepSeek API（OpenAI 兼容模式）

### 调用方法
- **方法**: `chat()`
- **参数**:
  - `messages`: 消息列表
  - `tools`: 工具定义（可选）
- **返回**: `LLMResponse`
- **调用参数**:
  - `model`: 模型名称
  - `messages`: 消息列表
  - `temperature`: 温度（默认 0.2）
  - `max_tokens`: 最大 Token（默认 4096）
  - `tools`: 工具定义（可选）
  - `tool_choice`: 工具选择策略（"auto"）

### 模拟响应模式
- **触发条件**: 未配置 API Key
- **响应内容**: "[模拟响应] 未配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。请设置环境变量后再执行真实调用。"
- **用途**: 开发调试，避免真实 API 调用

### 工具调用解析
- **流程**:
  1. 检查响应中的 `tool_calls`
  2. 解析每个工具调用的参数（JSON）
  3. 创建 `ToolCall` 对象
  4. 返回工具调用列表
- **错误处理**: JSON 解析失败时跳过该工具调用

### 响应处理
- **流程**:
  1. 检查响应是否有 choices
  2. 提取 message 内容和 tool_calls
  3. 解析工具调用（如果有）
  4. 处理空响应情况
- **空响应处理**: 如果无工具调用且无内容，返回提示消息

## 关键特性

### 1. OpenAI 兼容
- 支持 DeepSeek API
- 标准 OpenAI 格式
- Function Calling 支持

### 2. 灵活配置
- 多种配置来源
- 环境变量支持
- 构造函数参数

### 3. 模拟模式
- 无 API Key 时自动切换
- 开发调试友好
- 避免真实调用

### 4. 错误处理
- JSON 解析失败处理
- 空响应处理
- 异常捕获

## 使用示例

### 基本调用
```python
llm_service = LLMService(model="deepseek-v4-flash")
messages = [{"role": "user", "content": "你好"}]
response = llm_service.chat(messages=messages)
print(response.content)
```

### 工具调用
```python
tools_schema = tool_registry.to_openai_schema()
response = llm_service.chat(messages=messages, tools=tools_schema)
if response.tool_calls:
    for tc in response.tool_calls:
        print(f"工具: {tc.name}, 参数: {tc.arguments}")
```

### 自定义配置
```python
env = {
    "api_key": "your_key",
    "api_base": "https://api.deepseek.com"
}
llm_service = LLMService(model="deepseek-chat", env=env)
```

### 模拟模式
```python
llm_service = LLMService(model="test-model")  # 无 API Key
response = llm_service.chat(messages=messages)
print(response.content)  # 模拟响应
```

## 支持的模型

| 模型预设 | 模型字符串 | API 地址 |
|---------|-----------|---------|
| deepseek-flash | deepseek-chat | https://api.deepseek.com |
| deepseek-v4-flash | deepseek-chat | https://api.deepseek.com |
| deepseek-v4-pro | deepseek-chat | https://api.deepseek.com |

## 依赖
- `openai`: OpenAI 客户端库
- `pydantic`: 数据验证
- `json`: JSON 解析
- `os`: 环境变量