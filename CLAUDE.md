# CLAUDE.md

Project direction and current iteration are tracked in `ROADMAP.md`. Read it first in a new session.

This project builds a mini Claude Code-style local CLI coding agent. The current roadmap iterations 1-10 are complete for the single-worker CLI scope. The next phase is v0.2: reliability, user-facing polish, and real REPL dogfood testing before larger architecture changes.

请始终用中文回复用户。开始编码前先做定向上下文获取，并说明本轮调整要解决的问题。功能开发完成后补测试，测试通过后再进入下一步。需要人工验证时，明确告诉用户测试命令、交互步骤和预期结果。

## Project

DeepSeek Code Harness is a Claude Code-style AI coding assistant CLI built in Python. It uses a Supervisor + Worker + Harness architecture with ticket-based task management and DeepSeek/OpenAI-compatible APIs for LLM inference.

## Commands

```bash
# Install in editable mode
pip install -e .

# Run a single task
deepseek-code run "修复 auth.ts 的登录超时 bug"

# Start interactive REPL
deepseek-code repl

# Common REPL inspection commands
/tickets
/ticket T-001
/report
/review
/notes
/memory
/diff
/verify
/checkpoint
/rollback

# Run all tests
python -m pytest tests/

# On this Windows environment, prefer a writable pytest base temp directory
set PYTEST_ADDOPTS=--basetemp=.pytest-tmp && python -m pytest tests/
```

## Environment Variables

- `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`: API key. Falls back to mock response if unset.
- `DEEPSEEK_API_BASE` / `OPENAI_API_BASE`: API endpoint URL.
- `DEEPSEEK_API_VERSION`, `DEEPSEEK_API_TYPE`: optional OpenAI compatibility params.
- `DEEPSEEK_CODE_CURRENT_FILE`, `DEEPSEEK_CODE_CURRENT_LINE`: optional editor current-file context.
- `DEEPSEEK_CODE_SELECTION`, `DEEPSEEK_CODE_SELECTION_FILE`, `DEEPSEEK_CODE_SELECTION_START_LINE`, `DEEPSEEK_CODE_SELECTION_END_LINE`: optional editor selection context.

## Architecture

```text
CLI (cli.py)
  └── Supervisor (supervisor.py)
        ├── LLMService (llm_service.py)
        ├── MemoryManager (memory.py)
        ├── Worker (worker.py)
        ├── Harness (harness.py)
        └── ToolRegistry / Tools (tools.py)
```

- `Supervisor`: creates and resumes Tickets, drives planning, coordinates Worker execution, formats REPL output, reports, review summaries, checkpoint and rollback guidance.
- `Worker`: runs the tool-using agent loop for one Ticket and guards against repeated calls or no-progress loops.
- `Harness`: validates and executes tool calls, keeps operations project-scoped, records audit logs, and prompts for shell approval in interactive mode.
- `MemoryManager`: builds LLM messages from system prompt, Repo Map, editor context, session notes, recent decisions, and trimmed working history.
- `RepoMapBuilder`: detects language, package manager, test commands, entry points, and Python file summaries.

## Conventions

- Source code lives under `src/deepseek_code/`; tests live under `tests/`.
- Python 3.11+.
- Existing-file edits should go through `apply_patch`; `write_file` is for new files.
- `apply_patch` requires prior context evidence from `read_file`, `search_files`, or `search_content` in the same Ticket.
- Interrupted `running` Tickets are recovered as `blocked` on startup and can be resumed with `/continue <id>`.
- Final task output uses stable `Result`, `Plan`, `Changes`, `Tests`, and `Notes` sections.
- `/checkpoint`, `/rollback`, `/report`, and `/review` are read-only inspection helpers. They must not commit, reset, clean, or roll back automatically.
- Before moving into multi-worker architecture, prioritize v0.2 reliability, clean user-facing text, and real REPL testing.
