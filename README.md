# DeepSeek Code CLI

一个 Claude Code 风格的 AI 编码助手，基于 Python + Rich + Pydantic。支持自动任务拆分、工具调用、状态恢复和记忆压缩。

## 安装

```powershell
pip install -e .
```

## 快速开始

```powershell
# 执行单次任务
deepseek-code run "列出当前目录的文件"

# 启动交互式 REPL（多轮对话）
deepseek-code repl

# 指定模型
deepseek-code run "修复 auth.ts 的登录超时 bug" --model deepseek-v4-pro
```

## 环境变量

```powershell
# 必需（二选一）
setx DEEPSEEK_API_KEY "your_deepseek_key"
setx OPENAI_API_KEY "your_openai_key"

# 可选
setx DEEPSEEK_API_BASE "https://api.deepseek.com"

# 临时生效（仅当前终端）
set DEEPSEEK_API_KEY=your_key
```

> 如果未设置 API Key，程序返回模拟响应，适合开发调试。

## CLI 使用方式

### `deepseek-code run <任务描述>`

单次执行模式。Supervisor 自动将任务拆分为子 Ticket，Worker 通过 Ralph 循环（观察→分析→决策→执行）完成任务。

```powershell
deepseek-code run "读取 README.md 并总结"
deepseek-code run "创建一个 hello.py 文件"
deepseek-code run "列出 src 目录下所有 Python 文件"
```

执行流程：
1. Supervisor 调用 LLM 将任务拆分为子步骤
2. Worker 逐个执行子任务（调用工具：读文件、写文件、执行命令等）
3. 汇总所有子任务结果并输出

### `deepseek-code repl`

交互式 REPL 模式，支持多轮对话和内置命令：

```powershell
deepseek-code repl
```

进入 REPL 后可用的命令：

| 命令 | 说明 |
|------|------|
| `:help` | 显示帮助信息 |
| `:tickets` | 查看当前会话的所有 Ticket 及状态 |
| `:status` | 查看当前正在执行的 Ticket 详情 |
| `:new <描述>` | 创建并执行新 Ticket |
| `exit` / `quit` | 退出会话 |

直接输入任意文本也会当作任务执行：

```
DeepSeek> 读取 src/deepseek_code/cli.py 的内容
DeepSeek> :tickets
DeepSeek> exit
```

### 工具能力

Worker 可以通过 function calling 调用以下工具：

| 工具 | 说明 | 权限 |
|------|------|------|
| `read_file` | 读取文件内容 | 自动允许 |
| `write_file` | 写入文件（自动创建目录） | 自动允许 |
| `apply_patch` | 应用 unified diff 补丁 | 自动允许 |
| `list_dir` | 列出目录内容 | 自动允许 |
| `run_shell` | 执行 shell 命令 | 需人工确认 |

## 本地状态与审计

运行时在当前目录下创建 `.harness_state/`，用于持久化：

| 文件 | 说明 |
|------|------|
| `tickets.json` | 所有 Ticket 列表及状态 |
| `audit_log.json` | 操作审计日志（最近 1000 条） |
| `supervisor.json` | Supervisor 状态机状态 |

会话中断后可通过 `deepseek-code repl` 恢复 Ticket 列表和历史。

## 可用模型

| 模型 | 说明 |
|------|------|
| `deepseek-v4-flash`（默认） | 快速推理，适合日常任务 |
| `deepseek-v4-pro` | 高质量推理，适合复杂任务 |

## 目录结构

```
src/deepseek_code/
├── cli.py           # CLI 入口
├── supervisor.py    # 任务调度 + 状态机 + 子任务拆分
├── worker.py        # Ralph 循环执行引擎
├── harness.py       # 安全执行层（权限、审计）
├── llm_service.py   # LLM 调用独立模块
├── tools.py         # 工具注册机制 + 实现
├── memory.py        # 记忆管理 + Token 预算裁剪
└── persistence.py   # 状态持久化
```
