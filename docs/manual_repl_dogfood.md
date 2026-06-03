# Manual REPL Dogfood Checklist

This checklist covers the v0.2 reliability and user-facing polish pass. Run it from the repository root after installing the package in editable mode.

```powershell
pip install -e .
deepseek-code repl
```

## 1. Read-Only Context Smoke Test

In REPL:

```text
/context
/tickets
/review
```

Expected:

- `/context` prints project context, and editor context if the `DEEPSEEK_CODE_*` variables are set.
- `/tickets` works even when there are no Tickets.
- `/review` is read-only and does not run tests or mutate files.

## 2. Low-Risk Shell Approval

Ask the agent:

```text
运行 python --version
```

Expected:

- The shell approval prompt shows risk level, reason, working directory, and command.
- Approve it.
- The command succeeds or reports a normal command result.
- `/report` shows an approved shell permission and a `run_shell` result.

## 3. Denied Risky Shell Command

Ask the agent:

```text
运行 git clean -n
```

Expected:

- The shell approval prompt marks the command as high risk because it is a `git clean` command.
- Deny it.
- The Ticket should not leave the state ambiguous.
- `/report` shows `permission shell: denied` with risk and command details.
- `/review` includes the recent denied activity and a `Next steps` section with `/continue <id>`, `/trace`, `/diff`, and `/rollback` when the Ticket is blocked.

## 4. Verification Flow

After a task that changes a Python file, run:

```text
/verify
/review
```

Expected:

- `/verify` runs the suggested command only after shell approval in REPL.
- `/review` shows the last verification result or clearly says verification was not run.

## 5. Recovery Flow

If a Ticket becomes `failed` or `blocked`, run:

```text
/ticket T-001
/continue T-001
```

Expected:

- `/ticket T-001` shows `Resume Context`.
- `/continue T-001` resumes with prior failure context rather than blindly restarting.
- `/review` on a blocked or failed Ticket includes concrete recovery commands.

## 6. v0.2 Edit Polish Regression

Ask the agent:

```text
/new 给 index.html 添加一个 h3，内容是 测试最终输出是否简洁
/report
```

Expected:

- The task runs as one Ticket rather than separate "open/save/close file" Tickets.
- `Result` and `/report` keep a concise edit summary.
- Full HTML file bodies, fenced file dumps, raw `工具执行结果：<!DOCTYPE...` text, absolute path detail lines, and process-only checklist items do not appear in the final outcome.
- `Changes` lists `index.html`.

Manual pass:

- 2026-06-03: passed with `deepseek-chat` in `deepseek-code repl`; `/report` kept the concise inline `<h3>` edit summary and did not include full HTML dumps.

## 7. Non-Actionable Planning Regression

Ask the agent:

```text
/new 请打开 index.html，查看文件内容，在 body 里添加一个段落，然后保存并关闭文件
```

Expected:

- Planning does not create standalone Tickets for "打开文件", "查看文件内容", "保存文件", or "关闭文件".
- Final `Result` keeps the actual edit outcome and filters process-only checklist rows such as "读取文件" and "保存并关闭".
- `Changes` lists `index.html`.

Manual pass:

- 2026-06-03: partially passed before follow-up filtering; the task stayed in one Ticket and changed `index.html`, then code was updated to filter process-only checklist rows.

Record any confusing prompt text, unexpected state, or missing audit detail as v0.2 follow-up work.
