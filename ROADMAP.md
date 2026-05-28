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

Status: done for the current single-worker architecture.

Planned work:

- Extend RepoMap with package manager, test framework, entry point, and key config detection. (Done)
- Prefer targeted search and file reads before editing. (Done: `apply_patch` is rejected until the current Ticket has read the target file or performed a code search)
- Suggest narrower verification commands such as a relevant test file when possible. (Done for common Python, Node, Go, Rust, Java, Gradle, and .NET projects)
- Track recent user and agent decisions in a compact project memory. (Done)

Implementation notes:

- Supervisor tracks per-Ticket context evidence from successful `read_file`, `search_files`, and `search_content` calls.
- `apply_patch` requires context evidence before it is approved, so the Worker is forced to inspect relevant code before editing.
- Context evidence is cleared when each Ticket starts to avoid stale context leaking across subtasks.

## Iteration 3: Better Interactive Control

Objective: make REPL feel closer to a controllable coding assistant.

Status: done for the current single-worker architecture.

Planned work:

- Show an explicit plan before multi-step work. (Done in final task output for executed multi-step work)
- Let the user inspect, continue, or revise tickets. (Done: `/tickets` includes status counts; `/ticket <id>`, `/revise <id> <description>`, and `/continue [id]`)
- Improve approval prompts for risky commands. (Done for `run_shell`: prompts show risk level, reasons, and command text)
- Add resumable task workflow after interruption. (Done)
- Improve structured output sections: plan, changes, tests, notes. (Done)

Implementation notes:

- REPL can inspect individual Ticket details without rerunning work.
- `/tickets` shows status counts before the detailed Ticket list.
- `pending`, `blocked`, and `failed` tickets can be revised; blocked/failed tickets are reset to `pending` after revision.
- `/continue [id]` resumes the selected pending/blocked/failed Ticket in place, preserving the original Ticket ID; without an id it resumes the first unfinished Ticket.
- Interrupted `running` tickets are recovered as `blocked` on startup so `/continue [id]` can resume them.
- Coordinator-driven task reduction uses `cancelled` instead of deleting Tickets: when `skip_remaining` fires, skipped pending subtasks are marked `cancelled` and will not be resumed by `/continue`.
- Shell approvals now include simple risk classification (`low`, `medium`, `high`) and persist risk reasons to the audit log.
- Final task output uses stable `Result`, `Plan`, `Changes`, `Tests`, and `Notes` sections without duplicating verification suggestions.

## Iteration 4: Safer Git-Aware Workflows

Objective: make longer coding sessions easier to inspect and recover without adding destructive automation.

Status: done for the current read-only rollback guidance scope.

Planned work:

- Show a read-only checkpoint summary of branch, HEAD, and working tree changes. (Done: `/checkpoint`)
- Add optional checkpoint guidance before risky or multi-file changes. (Done for multi-file final output notes)
- Add rollback guidance that explains safe manual options without running destructive git commands automatically. (Done: `/rollback`)

Implementation notes:

- `/checkpoint` is read-only and runs `git branch --show-current`, `git rev-parse --short HEAD`, and `git status --short`.
- The checkpoint command reports non-git directories clearly instead of failing with raw git errors.
- Final task notes suggest `/checkpoint` after multi-file changes.
- `/rollback` is read-only guidance: it recommends `/checkpoint`, `/diff`, and manual `git restore`/`git clean -n` review steps without executing them.

## Iteration 5: Session Report and Audit UX

Objective: make each coding session easy to review after the agent has acted, especially when a task touched multiple files or failed partway through.

Status: done for the current read-only session report scope.

Planned work:

- Add `/report` to summarize the latest session in one place: Ticket, plan, changed files, suggested tests, checkpoint status, and compact trace. (Done in first version)
- Turn recent audit log entries into a human-readable tool activity summary. (Done in first version)
- Include failure-oriented next steps when the latest Ticket is `failed` or `blocked`, such as `/trace`, `/diff`, `/continue <id>`, `/checkpoint`, and `/rollback`. (Done in first version)
- Keep `/report` read-only. It should not run tests, mutate files, or execute git commands beyond the existing read-only status checks. (Done)

Definition of done:

- `deepseek-code repl` supports `/report`.
- `/report` works when no task has run, after a successful task, and after a failed or blocked Ticket.
- Report output is stable enough for tests and useful for copy/paste into an issue or commit note.
- Focused tests cover report formatting, audit summary, and failure next-step guidance.

Implementation notes:

- Prefer reusing existing `format_structured_output()`, `format_trace_summary()`, `format_checkpoint()`, `list_tickets()`, and persisted audit log data.
- Do not introduce automatic commit, rollback, or verification execution in this iteration.
- First `/report` version is read-only and covers no-task, successful-task, and failed/blocked-task paths.
- `/report` shows child Ticket plans when a task was split into subtasks.
- `/report` can recover changed files from persisted Ticket results after process restart.
- `/report` audit summaries use `tool_result`/`tool_error` entries so tool statuses match the persisted audit log.
- `/report` includes a compact Outcome section extracted from persisted Ticket results for issue or commit-note reuse.

## Iteration 6: Persistent Session Notes

Objective: preserve important decisions and user preferences across CLI sessions without requiring semantic search or a multi-worker architecture.

Status: complete for the current scoped version.

Planned work:

- Persist compact session notes under `.harness_state/`, for example `session_notes.json`. (Done in first version)
- Record durable facts such as completed iterations, architecture decisions, user preferences, recurring commands, and known manual test results. (Done for coordinator plans, dynamic decisions, and running-ticket recovery)
- Add `/notes` or `/memory` to inspect the persisted notes from REPL. (Done: `/notes`, `/memory` alias)
- Load session notes into `MemoryManager` or Supervisor startup context so future tasks can reuse them. (Done: loaded into `MemoryManager.build_messages()`)
- Add simple pruning or deduplication so notes stay compact and readable. (Done in persistence layer)

Definition of done:

- Notes survive process restart.
- New sessions can show or use prior durable notes without reading unrelated ticket logs manually.
- Tests cover note persistence, deduplication/pruning, and REPL inspection.

Implementation notes:

- Start with structured JSON and deterministic summaries; do not add vector search or semantic retrieval yet.
- Keep private/project-local notes in `.harness_state/` and exclude them from repository maps.
- First version writes `session_notes.json`, deduplicates notes by category/text, keeps the latest 200 notes, and exposes `/notes`.
- Coordinator now records compact automatic notes for multi-step plans, `skip_remaining`, `add_tasks`, `re_plan`, and recovery of stale `running` tickets.
- Supervisor now syncs persisted notes into `MemoryManager`; LLM calls receive a compact `Session Notes` system section with the latest durable notes.
- `/memory` is a compatibility alias for `/notes`.

## Iteration 7: Safer Execution and Approval UX

Objective: make real project usage safer by improving how shell execution, approvals, and audit feedback communicate risk before anything potentially impactful runs.

Status: next.

Planned work:

- Review current Harness approval flow for `run_shell`, including risk labels, risk reasons, working directory, and command text.
- Make approve/deny outcomes easier to inspect in the audit log and `/report`.
- Strengthen classification for destructive, network, git, package-manager, and long-running commands without blocking low-risk read-only commands unnecessarily.
- Add clearer user-facing confirmation text so manual testers can understand what they are approving.
- Keep all destructive git operations manual; do not add automatic rollback or reset behavior.

Definition of done:

- Risky shell commands show enough context for a user to make a decision.
- Denied commands are recorded clearly and do not leave Ticket state ambiguous.
- `/report` or audit summaries can distinguish approved, denied, failed, and successful shell activity.
- Focused tests cover risk classification, approval/denial audit records, and report formatting.
- Manual testing verifies at least one allowed command and one denied command in REPL.

Implementation notes:

- Prefer incremental improvements to the existing Harness instead of adding a separate policy engine.
- Keep prompts concise: command purpose, working directory, risk level, risk reasons, and approve/deny choices.
- Treat command safety as explainability first; hard blocking can be added later for clearly destructive patterns.

## Iteration 8: Pre-Commit Review and Change Summary

Objective: turn the existing `/diff`, `/checkpoint`, `/verify`, and `/report` primitives into a reliable end-of-iteration review loop before the user commits changes.

Status: planned.

Planned work:

- Add a concise pre-commit style summary that includes changed files, test results, unresolved risks, and suggested commit message.
- Reuse existing read-only git helpers; do not auto-commit.
- Make failed or skipped verification explicit in the summary.
- Keep the output stable enough for issue comments or commit notes.

Definition of done:

- A user can inspect what changed and what was verified without manually combining `/diff`, `/checkpoint`, and `/report`.
- The summary makes it clear whether tests passed, failed, or were not run.
- Tests cover clean, dirty, failed-test, and no-git scenarios.

## Iteration 9: More Reliable Failure Recovery

Objective: make interrupted or failed work easier to resume without losing the original goal, trace, or last useful context.

Status: planned.

Planned work:

- Improve `/continue` context by carrying forward the last failure reason, compact trace, relevant notes, and remaining objective.
- Make blocked and failed Ticket recovery messages more actionable.
- Preserve enough context for resumed work without replaying noisy worker logs.

Definition of done:

- Resuming a failed or blocked Ticket gives the Worker enough context to avoid repeating the same failure.
- Users can inspect why a Ticket is resumable and what the next suggested action is.
- Tests cover failed, blocked, and recovered-running Ticket flows.

## Iteration 10: IDE/Editor Integration Seed

Objective: start connecting the CLI workflow to editor-centric usage without committing to a full IDE plugin.

Status: planned.

Planned work:

- Improve file/line references in outputs so editors can navigate them easily.
- Add lightweight current-file or selected-file context hooks if available from the calling environment.
- Keep the first version CLI-compatible; editor integrations should consume existing commands and reports.

Definition of done:

- Output paths are consistently useful for opening files from an editor or terminal.
- The integration path is documented without requiring a specific editor extension yet.

## Longer-Term Direction

- Multi-worker or specialized worker roles: planner, coder, reviewer.
- Stronger sandboxing and safer shell execution.
- Long-term memory with semantic retrieval after persistent session notes are proven useful.
- IDE/editor integration.
