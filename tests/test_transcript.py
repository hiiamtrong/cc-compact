from __future__ import annotations

from hooks.lib import transcript


def test_parse_jsonl_empty_file(copy_fixture):
    path = copy_fixture("transcript_empty.jsonl")
    assert transcript.parse_jsonl(str(path)) == []


def test_parse_jsonl_returns_messages_in_order(copy_fixture):
    path = copy_fixture("transcript_single_turn.jsonl")
    messages = transcript.parse_jsonl(str(path))
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "hello"
    assert messages[0].index == 0
    assert messages[1].role == "assistant"
    assert messages[1].content == "hi there"
    assert messages[1].index == 1


def test_parse_jsonl_missing_file_returns_empty(tmp_path):
    assert transcript.parse_jsonl(str(tmp_path / "nope.jsonl")) == []
