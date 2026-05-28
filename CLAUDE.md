# CLAUDE.md

Project direction and current iteration are tracked in `ROADMAP.md`. Read it first in a new session: the product goal is to build a mini version of Claude Code. Iterations 1-6 are complete for the current single-worker/read-only workflow scope; Iteration 7 (safer execution and approval UX) is next. Use `ROADMAP.md` as the source of truth before planning or implementing the next iteration.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
后续请始终用中文回答我
编辑前必须先做定向上下文获取，并说明本轮调整要解决的问题
功能开发完成之后，请编写测试编码，测试通过之后，在进行下一步
如果需要的话，也可以引导用户进行手动测试，确保功能没问题
函数注释或者是提示，使用中文，确保用户能够理解

## Project

DeepSeek Code Harness — a Claude Code-style AI coding assistant CLI built in Python. It uses a Supervisor + Worker + Harness layered architecture with ticket-based task management and DeepSeek API (OpenAI-compatible) for LLM inference.

## Commands

```bash
# Install (editable mode)
pip install -e .

# Run a single task
deepseek-code run "修复 auth.ts 的登录超时 bug"

# Start interactive REPL
deepseek-code repl

# Run REPL inspection commands
/tickets
/ticket T-001
/report
/notes
/memory
/diff
/checkpoint
/rollback

# Run all tests
python -m pytest tests/

# On this Windows environment, prefer a writable pytest base temp directory
set PYTEST_ADDOPTS=--basetemp=.pytest-tmp && python -m pytest tests/

# Run a single test file
python -m pytest tests/test_harness.py

# Run a single test by name
python -m pytest tests/test_supervisor.py::test_parse_plan_valid_json -v
```

## Environment Variables

- `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` — API key (falls back to mock response if unset)
- `DEEPSEEK_API_BASE` / `OPENAI_API_BASE` — API endpoint URL
- `DEEPSEEK_API_VERSION`, `DEEPSEEK_API_TYPE` — Optional OpenAI compat params

## Architecture

Four-layer design with dependency injection:

```
CLI (cli.py)
  └── Supervisor (supervisor.py)
        ├── LLMService (llm_service.py) — LLM 调用独立模块
        ├── MemoryManager (memory.py) — 共享上下文，token 预算驱动裁剪
        ├── Worker (worker.py) — Ralph 循环执行引擎
        ├── Harness (harness.py) — 安全执行层（权限、审计）
        └── ToolRegistry (tools.py) — 工具自描述注册机制
```

- **Supervisor** (`supervisor.py`): 接收用户输入，LLM 驱动子任务拆分（`plan_task()`），管理 Ticket 生命周期，状态机（`SupervisorState` 枚举：idle→planning→dispatching→waiting_worker→reviewing→complete/failed），REPL 交互。Memory 在此级别共享。REPL 支持 `/tickets`、`/ticket <id>`、`/revise <id> <描述>`、`/continue [id]`、`/report`、`/notes`、`/memory`、`/diff`、`/verify`、`/checkpoint` 和 `/rollback`。

- **LLMService** (`llm_service.py`): 独立 LLM 调用模块。使用新版 `openai.OpenAI()` SDK + function calling。返回结构化 `LLMResponse(content, tool_calls)`。无 API key 时返回模拟响应。

- **Worker** (`worker.py`): Ralph 循环执行引擎。max_loop_iterations 保护（默认 10），连续无进展检测（3 次终止）。LLM 调用走 `llm_service`，工具执行走 `harness.execute_tool_call()`。

- **Harness** (`harness.py`): 安全层。文件操作自动允许，shell 需人工确认。`run_shell` 确认提示会显示风险等级、风险原因和完整命令。所有操作记录审计日志到 `.harness_state/audit_log.json`。

- **ToolRegistry** (`tools.py`): `ToolDef`（name/description/parameters/handler）自描述注册，`to_openai_schema()` 生成 function calling 格式。默认注册工具包括 `read_file`、`write_file`、`list_dir`、`run_shell`、`apply_patch`、`search_files` 和 `search_content`。

- **MemoryManager** (`memory.py`): 增强版 system prompt（含工具说明 + Ralph 循环引导），token 预算驱动裁剪（`_estimate_tokens` ≈ len//2），规则版结构化摘要压缩（`_summarize_history`），并把持久化 session notes 作为紧凑 system context 注入 LLM 调用。

Key data flow: `CLI → Supervisor.handle_prompt() → plan_task() [LLM拆分] → Worker.execute_ticket() [Ralph循环: llm_service.chat() → harness.execute_tool_call()]* → response`

## Conventions

- All source code under `src/deepseek_code/`, tests under `tests/`
- Python 3.11+, uses `from __future__ import annotations` consistently
- Dependencies: rich (terminal UI), pydantic (data models), openai (LLM client)
- Ticket model is a Pydantic `BaseModel` with statuses: `pending`, `running`, `blocked`, `done`, `failed`, `cancelled`; includes `max_loop_iterations` (default 10) and `parent_ticket_id` for subtask hierarchy
- Existing-file edits should go through `apply_patch`; `write_file` is for new files. `apply_patch` requires prior context evidence from `read_file`, `search_files`, or `search_content` in the same Ticket.
- Interrupted `running` tickets are recovered as `blocked` on startup and can be resumed with `/continue <id>`.
- Final task output uses stable `Result`, `Plan`, `Changes`, `Tests`, and `Notes` sections. Multi-file changes should prompt the user to run `/checkpoint`.
- `/checkpoint` and `/rollback` are read-only git-aware helpers. `/rollback` provides manual guidance only and must not run destructive git commands automatically.
- The design document `ARCHITECTURE.md` describes the full target architecture (v0.1-v0.4+); current implementation is still single-worker and intentionally avoids multi-worker complexity.
