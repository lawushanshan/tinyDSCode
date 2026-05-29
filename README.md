# DeepSeek Code CLI

一个 Claude Code 风格的本地 AI 编码助手，基于 Python、Rich、Pydantic 和 OpenAI 兼容 API。它围绕 Ticket 驱动的任务执行循环构建，支持项目上下文理解、工具调用、状态恢复、审计日志、验证建议和提交前审查。

## 安装

```powershell
pip install -e .
```

## 快速开始

```powershell
# 执行单次任务
deepseek-code run "列出当前目录的文件"

# 启动交互式 REPL
deepseek-code repl

# 运行评估任务
deepseek-code eval

# 指定模型
deepseek-code run "修复 auth.ts 的登录超时 bug" --model deepseek-v4-pro
```

## 环境变量

```powershell
# 必需，二选一
setx DEEPSEEK_API_KEY "your_deepseek_key"
setx OPENAI_API_KEY "your_openai_key"

# 可选
setx DEEPSEEK_API_BASE "https://api.deepseek.com"

# 可选：编辑器或 IDE 调用时注入当前文件上下文
setx DEEPSEEK_CODE_CURRENT_FILE "src/app.py"
setx DEEPSEEK_CODE_CURRENT_LINE "12"
setx DEEPSEEK_CODE_SELECTION "selected code text"
setx DEEPSEEK_CODE_SELECTION_START_LINE "12"
setx DEEPSEEK_CODE_SELECTION_END_LINE "18"

# 临时生效，仅当前终端
set DEEPSEEK_API_KEY=your_key
```

未设置 API key 时，程序会返回模拟响应，适合开发调试。

## CLI 命令

### `deepseek-code run <任务描述>`

单次执行任务。Supervisor 会创建 Ticket，必要时拆分子任务；Worker 通过工具读取文件、搜索代码、应用 patch、执行命令，并输出结构化结果。

```powershell
deepseek-code run "读取 README.md 并总结"
deepseek-code run "创建一个 hello.py 文件"
deepseek-code run "列出 src 目录下所有 Python 文件"
```

### `deepseek-code repl`

启动交互式会话，支持多轮任务和检查命令。

```powershell
deepseek-code repl
```

常用 REPL 命令：

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示帮助 |
| `/tickets` | 查看 Ticket 列表和状态汇总 |
| `/ticket <id>` | 查看指定 Ticket 详情和恢复提示 |
| `/status` | 查看当前运行中的 Ticket |
| `/trace` | 查看最近一次执行轨迹 |
| `/report` | 查看最近一次任务复盘报告 |
| `/review` | 查看提交前只读审查摘要 |
| `/notes` | 查看持久化 session notes |
| `/memory` | `/notes` 的别名 |
| `/context` | 查看项目上下文和编辑器上下文 |
| `/refresh` | 刷新项目上下文 |
| `/diff` | 查看当前变更 diff |
| `/verify` | 运行最近一次建议验证命令 |
| `/checkpoint` | 查看 git 分支、HEAD 和工作区变更 |
| `/rollback` | 查看安全回滚指引，不自动执行回滚 |
| `/revise <id> <描述>` | 修改 pending/blocked/failed Ticket 描述 |
| `/continue [id]` | 继续执行指定 Ticket 或下一个未完成 Ticket |
| `/new <描述>` | 创建并执行新 Ticket |
| `exit` / `quit` | 退出会话 |

兼容输入形式：`:help`、`:tickets` 这类冒号命令仍可使用；`help`、`tickets`、`verify` 等裸命令会自动识别。

任务完成后会输出稳定结构：

- `Result`
- `Plan`
- `Changes`
- `Tests`
- `Notes`

如果一次任务修改多个文件，`Notes` 会提示运行 `/checkpoint` 查看当前 git 状态。

## 工具能力

Worker 通过 function calling 调用工具，所有操作都经过 Harness。

| 工具 | 说明 | 权限 |
| --- | --- | --- |
| `read_file` | 读取文件内容 | 自动允许 |
| `write_file` | 创建新文件并写入内容 | 自动允许 |
| `apply_patch` | 对已有文件应用 unified diff | 自动允许 |
| `list_dir` | 列出目录内容 | 自动允许 |
| `search_files` | 按 glob 搜索文件 | 自动允许 |
| `search_content` | 按正则搜索文件内容 | 自动允许 |
| `run_shell` | 执行 shell 命令 | REPL 中需要人工确认 |
| `web_search` | 联网搜索 | 通过 Harness 执行 |

`run_shell` 审批会显示风险等级、风险原因、工作目录和完整命令。审计日志会记录批准、拒绝、成功、失败和风险信息。

## 本地状态

运行时会在当前项目下创建 `.harness_state/`：

| 文件 | 说明 |
| --- | --- |
| `tickets.json` | Ticket 列表和状态 |
| `audit_log.json` | 工具调用和权限审计日志，保留最近 1000 条 |
| `supervisor.json` | Supervisor 状态机状态 |
| `session_notes.json` | 持久化 session notes |

中断后重新进入 `deepseek-code repl` 会恢复 Ticket 列表。上次中断时仍为 `running` 的 Ticket 会被标记为 `blocked`，可以用 `/ticket <id>` 查看恢复提示，用 `/continue <id>` 继续。

Ticket 状态：

| 状态 | 说明 |
| --- | --- |
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `blocked` | 被阻塞，需要外部处理或人工决策 |
| `done` | 已完成 |
| `failed` | 执行失败，可修订或继续 |
| `cancelled` | 调度器判断无需继续执行 |

## 当前能力基线

- 单 Worker 的 Ticket 驱动编码循环。
- 项目 Repo Map、测试命令建议和编辑器上下文注入。
- REPL 检查命令：`/report`、`/review`、`/diff`、`/verify`、`/checkpoint`、`/rollback`。
- 持久化 Ticket、审计日志和 session notes。
- 安全 shell 审批和风险审计。
- 失败和中断 Ticket 的恢复上下文注入。

## 目录结构

```text
src/deepseek_code/
├── cli.py           # CLI 入口
├── supervisor.py    # 任务调度、Ticket、REPL、报告
├── worker.py        # Worker 执行循环
├── harness.py       # 安全执行层和审计
├── llm_service.py   # OpenAI 兼容 LLM 适配
├── tools.py         # 工具注册和实现
├── memory.py        # 上下文、session notes、编辑器上下文
├── repo_map.py      # 项目结构扫描
├── persistence.py   # 本地状态持久化
└── eval/            # 评估任务框架
```

## 测试

```powershell
set PYTEST_ADDOPTS=--basetemp=.pytest-tmp
python -m pytest tests/ -q
```

## 人工 REPL 验证

v0.2 的真实交互验证清单在 [docs/manual_repl_dogfood.md](docs/manual_repl_dogfood.md)，覆盖只读检查、低风险 shell 允许、高风险 shell 拒绝、验证流和恢复流。
