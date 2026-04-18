"""Pure functions for parsing a Claude Code transcript (.jsonl)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

Role = Literal["user", "assistant", "system", "tool"]

VALID_ROLES = {"user", "assistant", "system", "tool"}

# Slash commands that are META (session management, CLI control) — not task statements.
# Custom / project-specific slash commands are intentionally NOT listed here.
SLASH_COMMAND_SKIP_PREFIXES = (
    "/compact",
    "/clear",
    "/cost",
    "/context",
    "/status",
    "/help",
    "/memory",
    "/init",
    "/logout",
    "/login",
    "/model",
    "/review",
    "/config",
    "/bug",
    "/release-notes",
    "/doctor",
    "/pr",
    "/terminal-setup",
    "/mcp",
    "/permissions",
    "/hooks",
    "/ide",
)

_SLASH_CMD_RE = re.compile(r"<command-name>(/[a-zA-Z0-9_-]+)</command-name>")


def _extract_slash_command(content: str) -> str | None:
    """Return the /name portion if `content` starts with a slash-command marker."""
    if not content:
        return None
    stripped = content.lstrip()
    if not stripped.startswith("<command-name>"):
        return None
    m = _SLASH_CMD_RE.match(stripped)
    return m.group(1) if m else None


@dataclass
class Message:
    role: Role
    content: str
    raw: dict = field(default_factory=dict)
    index: int = 0


@dataclass
class TodoItem:
    content: str
    status: Literal["pending", "in_progress", "completed"]


def _flatten_content(raw_content) -> str:
    """Flatten Claude Code content (string or list of blocks) into plain text."""
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        parts: list[str] = []
        for block in raw_content:
            if isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(p for p in parts if p)
    return ""


def parse_jsonl(path: str) -> list[Message]:
    """Stream-read JSONL; skip corrupt lines and metadata; return ordered list."""
    p = Path(path)
    if not p.exists():
        return []
    messages: list[Message] = []
    idx = 0
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue

            # Real CLI format: role is nested in message.role
            # Synthetic test format: role is at top level
            msg_obj = raw.get("message") if isinstance(raw.get("message"), dict) else None
            role = None
            if msg_obj is not None:
                role = msg_obj.get("role")
            if role is None:
                role = raw.get("role")

            # Skip metadata lines that aren't real messages
            if role not in VALID_ROLES:
                continue

            # Content: prefer nested, fall back to top-level
            if msg_obj is not None and "content" in msg_obj:
                raw_content = msg_obj.get("content")
            else:
                raw_content = raw.get("content", "")

            content = _flatten_content(raw_content)
            messages.append(Message(role=role, content=content, raw=raw, index=idx))
            idx += 1
    return messages


def find_last_user_index(messages: list[Message]) -> Optional[int]:
    """Return index of last role=user message, skipping meta slash commands."""
    for msg in reversed(messages):
        if msg.role != "user":
            continue
        cmd = _extract_slash_command(msg.content)
        if cmd in SLASH_COMMAND_SKIP_PREFIXES:
            continue
        return msg.index
    return None


def slice_in_flight(messages: list[Message], from_index: Optional[int]) -> list[Message]:
    """Return messages[from_index:]. If from_index is None, return all."""
    if from_index is None:
        return list(messages)
    return [m for m in messages if m.index >= from_index]


def _message_content_blocks(msg: Message) -> list[dict]:
    """Return list content blocks from a Message's raw payload (handles both formats)."""
    raw = msg.raw
    # Real CLI format: content is nested in message.content
    if isinstance(raw.get("message"), dict):
        content = raw["message"].get("content")
        if isinstance(content, list):
            return [b for b in content if isinstance(b, dict)]
    # Synthetic test format: content is at top level
    content = raw.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def extract_latest_todos(messages: list[Message]) -> list[TodoItem]:
    """Find the most recent TodoWrite tool_use call and parse its todo list."""
    latest: list[TodoItem] = []
    for msg in messages:
        for block in _message_content_blocks(msg):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") != "TodoWrite":
                continue
            input_val = block.get("input", {})
            if not isinstance(input_val, dict):
                continue
            todos_raw = input_val.get("todos", [])
            parsed: list[TodoItem] = []
            for t in todos_raw:
                if not isinstance(t, dict):
                    continue
                content = t.get("content") or ""
                status = t.get("status") or "pending"
                if status not in ("pending", "in_progress", "completed"):
                    status = "pending"
                parsed.append(TodoItem(content=content, status=status))
            if parsed:
                latest = parsed  # later wins
    return latest
