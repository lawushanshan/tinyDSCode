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

# 启动测试集
deepseek-code eval 

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
| `/help` | 显示帮助信息 |
| `/tickets` | 查看当前会话的所有 Ticket、状态和状态汇总 |
| `/ticket <id>` | 查看指定 Ticket 详情 |
| `/status` | 查看当前正在执行的 Ticket 详情 |
| `/trace` | 查看最近一次执行轨迹 |
| `/report` | 查看最近一次任务复盘报告 |
| `/context` | 查看当前项目上下文 |
| `/refresh` | 刷新项目上下文 |
| `/diff` | 查看当前变更 diff |
| `/verify` | 运行最近一次建议验证命令 |
| `/checkpoint` | 查看当前 git 分支、HEAD 和工作区变更概况 |
| `/rollback` | 查看安全回滚指引，不自动执行回滚 |
| `/revise <id> <描述>` | 修改 pending/blocked/failed Ticket 描述 |
| `/continue [id]` | 继续执行指定 Ticket；不填 id 时继续下一个未完成 Ticket |
| `/new <描述>` | 创建并执行新 Ticket |
| `exit` / `quit` | 退出会话 |

兼容旧输入形式：`:help`、`:tickets` 等冒号命令仍可使用；`help`、`tickets`、`verify` 等裸命令也会自动识别。

直接输入任意文本也会当作任务执行：

```
DeepSeek> 读取 src/deepseek_code/cli.py 的内容
DeepSeek> /tickets
DeepSeek> exit
```

任务完成后会按固定结构输出 `Result`、`Plan`、`Changes`、`Tests` 和 `Notes`，便于快速查看执行结果、变更文件、建议验证命令和最近执行轨迹。
如果一次任务修改了多个文件，`Notes` 会提示运行 `/checkpoint` 查看当前 git 状态。

### 工具能力

Worker 可以通过 function calling 调用以下工具：

| 工具 | 说明 | 权限 |
|------|------|------|
| `read_file` | 读取文件内容 | 自动允许 |
| `write_file` | 写入文件（自动创建目录） | 自动允许 |
| `apply_patch` | 应用 unified diff 补丁 | 自动允许 |
| `list_dir` | 列出目录内容 | 自动允许 |
| `run_shell` | 执行 shell 命令 | 需人工确认 |

交互式 REPL 中的 `run_shell` 会在执行前请求确认，并显示风险等级、风险原因和完整命令。

## 本地状态与审计

运行时在当前目录下创建 `.harness_state/`，用于持久化：

| 文件 | 说明 |
|------|------|
| `tickets.json` | 所有 Ticket 列表及状态 |
| `audit_log.json` | 操作审计日志（最近 1000 条） |
| `supervisor.json` | Supervisor 状态机状态 |

会话中断后可通过 `deepseek-code repl` 恢复 Ticket 列表和历史；上次中断时仍为 `running` 的 Ticket 会在加载时标记为 `blocked`，可用 `/continue <id>` 继续。

Ticket 状态：

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `blocked` | 暂时阻塞，需要外部处理 |
| `done` | 已完成 |
| `failed` | 执行失败，可修改后继续 |
| `cancelled` | 调度器判断不再需要执行 |

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
