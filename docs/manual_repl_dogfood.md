# Manual REPL Dogfood Checklist

This checklist covers the v0.2 reliability and user-facing polish pass. Run it from the repository root after installing the package in editable mode.

```powershell
pip install -e .
deepseek-code repl
```

## 1. Read-only context smoke test

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

## 2. Low-risk shell approval

Ask the agent:

```text
运行 python --version
```

Expected:

- The shell approval prompt shows risk level, reason, working directory, and command.
- Approve it.
- The command succeeds or reports a normal command result.
- `/report` shows an approved shell permission and a `run_shell` result.

## 3. Denied risky shell command

Ask the agent:

```text
运行 git clean -n
```

Expected:

- The shell approval prompt marks the command as high risk because it is a `git clean` command.
- Deny it.
- The Ticket should not leave the state ambiguous.
- `/report` shows `permission shell: denied` with risk and command details.
- `/review` includes the recent denied activity.

## 4. Verification flow

After a task that changes a Python file, run:

```text
/verify
/review
```

Expected:

- `/verify` runs the suggested command only after shell approval in REPL.
- `/review` shows the last verification result or clearly says verification was not run.

## 5. Recovery flow

If a Ticket becomes `failed` or `blocked`, run:

```text
/ticket T-001
/continue T-001
```

Expected:

- `/ticket T-001` shows `Resume Context`.
- `/continue T-001` resumes with prior failure context rather than blindly restarting.

Record any confusing prompt text, unexpected state, or missing audit detail as v0.2 follow-up work.
