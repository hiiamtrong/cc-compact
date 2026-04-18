# Claude Smart Compact

Two Claude Code CLI hooks that preserve task state, in-progress todos, and
user preferences across auto-compaction, without bloating the context window.

## How it works

- **PreCompact** runs when the CLI is about to auto-compact. It reads the
  session transcript, extracts the last user message + in-flight turns + the
  latest `TodoWrite` snapshot, and writes a Markdown memory file to
  `<project>/.claude/compact-memory/<session_id>.md`.
- **UserPromptSubmit** runs on every user prompt after the first compaction.
  It injects a short pointer telling the agent the memory file is available
  and may be read on demand.
- Preferences are **agent-authored** — the hook preserves a `## Preferences`
  section on every run, but does not populate it automatically. Append with
  the Edit tool when the user states a lasting preference.

## Install (per project)

1. Copy `hooks/` into your project's `.claude/hooks/`.
2. Copy `.claude/settings.json.example` to `.claude/settings.json`
   (or merge into your existing settings).
3. Make sure `python3` is on your `$PATH`.

## Verify

Run the manual trace script:

```bash
python3 tests/trace_run.py tests/fixtures/transcript_with_todos.jsonl
```

## Run tests

```bash
pip install -e ".[dev]"
pytest --cov=hooks
```

## Debug

Every hook run appends to `<project>/.claude/compact-memory/<session_id>.trace.jsonl`.
`tail -f` this file to watch the hooks work in real time.
