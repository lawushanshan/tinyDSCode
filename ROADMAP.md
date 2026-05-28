# Mini Claude Code Roadmap

## Product Direction

This project is evolving into a mini version of Claude Code: a local CLI coding agent that can understand a repository, plan work, edit files, run verification, recover from failures, and expose enough traceability for the user to inspect and steer the process.

The goal is not a generic chat CLI. The goal is an agentic coding loop with these properties:

- Project-aware: builds and refreshes a concise map of the repository.
- Task-driven: turns user requests into tickets and executable steps.
- Tool-using: reads files, searches code, patches files, runs commands, and reports results through controlled tools.
- Safe by default: routes actions through Harness for approval, audit, and change tracking.
- Verifiable: suggests and runs relevant tests after file changes.
- Recoverable: persists tickets, audit logs, and supervisor state under `.harness_state/`.

## Current Architecture

- CLI entry: `src/deepseek_code/cli.py`
- Task orchestration: `src/deepseek_code/supervisor.py`
- Agent loop: `src/deepseek_code/worker.py`
- Tool execution guard: `src/deepseek_code/harness.py`
- Tool registry and implementations: `src/deepseek_code/tools.py`
- LLM adapter: `src/deepseek_code/llm_service.py`
- Context/memory: `src/deepseek_code/memory.py`, `src/deepseek_code/repo_map.py`
- Persistence: `src/deepseek_code/persistence.py`
- Evaluation harness: `src/deepseek_code/eval/`

## Iteration 1: Reliable Single-Task Coding Loop (Done)

Objective: make one coding task run end-to-end reliably in the style of a small Claude Code session.

Scope:

- Keep existing-file edits on `apply_patch`; use `write_file` only for new files.
- Make final task output consistently include changed files, verification suggestion, and a compact trace summary.
- Make `/diff` and `/verify` core parts of the development loop.
- Improve changed-file tracking for `write_file` and `apply_patch`.
- Strengthen Worker safeguards for repeated calls, no-progress loops, and post-mutation final summaries.
- Fix or replace corrupted Chinese text in user-facing documentation and critical prompts.
- Add/adjust tests for planning, tool rejection, file change tracking, verification suggestions, and trace formatting.

Definition of done:

- `deepseek-code run "<small code change>"` can modify a file, summarize the change, and suggest a test command.
- `deepseek-code repl` supports inspecting tickets, trace, diff, and verification after a task.
- Python test suite passes with `python -m pytest tests/`.
- New behavior is covered by focused tests.

Implementation notes:

- Existing-file edits are guarded to use `apply_patch`; `write_file` is reserved for new files.
- Final task output includes changed files, verification suggestions, compact trace summary, and an executed plan for multi-step work.
- REPL supports `/diff`, `/verify`, `/trace`, `/tickets`, `/status`, `/context`, and `/refresh`.
- Changed-file tracking covers `write_file` and `apply_patch`.
- Worker loop now guards repeated tool calls, no-progress loops, rejected tool calls, and post-mutation final summaries.
- User-facing documentation and critical prompts are valid UTF-8 Chinese.
- On this Windows environment, run tests with a writable pytest base temp directory, for example:
  `set PYTEST_ADDOPTS=--basetemp=.pytest-tmp && python -m pytest tests/`

## Iteration 2: Stronger Project Understanding

Objective: make the agent choose better context and verification commands before editing.

Status: partially implemented.

Planned work:

- Extend RepoMap with package manager, test framework, entry point, and key config detection. (Done)
- Prefer targeted search and file reads before editing.
- Suggest narrower verification commands such as a relevant test file when possible. (Done for common Python, Node, Go, Rust, Java, Gradle, and .NET projects)
- Track recent user and agent decisions in a compact project memory. (Done)

## Iteration 3: Better Interactive Control

Objective: make REPL feel closer to a controllable coding assistant.

Status: partially implemented.

Planned work:

- Show an explicit plan before multi-step work. (Done in final task output for executed multi-step work)
- Let the user inspect, continue, or revise tickets.
- Improve approval prompts for risky commands.
- Add resumable task workflow after interruption.
- Improve structured output sections: plan, changes, tests, notes. (Partially done: plan, changes, suggested tests, trace summary)

## Longer-Term Direction

- Multi-worker or specialized worker roles: planner, coder, reviewer.
- Stronger sandboxing and safer shell execution.
- Git-aware checkpoints and optional rollback guidance.
- Long-term memory with semantic retrieval.
- IDE/editor integration.
