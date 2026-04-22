"""In-process tests for hook_runner — covers run_hook's soft-fail contract."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from cc_compact.lib import hook_runner
from cc_compact.lib import memory as mem_lib


def _set_stdin(monkeypatch: pytest.MonkeyPatch, payload: str) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))


def test_run_hook_dispatches_payload_to_fn(project_root, monkeypatch, capsys):
    monkeypatch.chdir(project_root)
    _set_stdin(monkeypatch, json.dumps({"session_id": "sid-ok", "x": 1}))

    seen: list[dict] = []

    def fn(payload: dict) -> None:
        seen.append(payload)
        json.dump({"ok": True}, sys.stdout)

    hook_runner.run_hook(fn, "TestHook")
    out = capsys.readouterr().out
    assert json.loads(out) == {"ok": True}
    assert seen == [{"session_id": "sid-ok", "x": 1}]


def test_run_hook_soft_fails_on_bad_stdin(project_root, monkeypatch, capsys):
    """Malformed JSON must not propagate — stdout=`{}`, exit=0."""
    monkeypatch.chdir(project_root)
    _set_stdin(monkeypatch, "not json at all")

    with pytest.raises(SystemExit) as exc:
        hook_runner.run_hook(lambda p: None, "TestHook")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out) == {}


def test_run_hook_soft_fails_on_payload_exception_and_traces(project_root, monkeypatch, capsys):
    """If payload_fn raises, the error must be traced under session_id."""
    monkeypatch.chdir(project_root)
    _set_stdin(monkeypatch, json.dumps({"session_id": "sid-boom"}))

    def boom(_payload: dict) -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(SystemExit) as exc:
        hook_runner.run_hook(boom, "TestHook")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out) == {}

    trace = mem_lib.trace_path(project_root, "sid-boom")
    assert trace.exists()
    event = json.loads(trace.read_text().strip().splitlines()[0])
    assert event["hook"] == "TestHook"
    assert event["error_type"] == "RuntimeError"
    assert event["error"] == "kaboom"


def test_safe_trace_noop_when_no_session_id(project_root):
    """safe_trace must silently skip when session_id is falsy (no file written)."""
    hook_runner.safe_trace(project_root, None, {"hook": "X"})
    hook_runner.safe_trace(project_root, "", {"hook": "X"})
    # Nothing should exist under compact-memory.
    mem_dir = project_root / ".claude" / "compact-memory"
    assert not mem_dir.exists() or not any(mem_dir.iterdir())


def test_safe_trace_swallows_io_errors(project_root, monkeypatch):
    """safe_trace must not propagate exceptions from memory.append_trace."""
    def boom(*_a, **_kw):
        raise OSError("disk full")

    monkeypatch.setattr(hook_runner.memory, "append_trace", boom)
    # Should not raise.
    hook_runner.safe_trace(project_root, "sid-x", {"hook": "Y"})
