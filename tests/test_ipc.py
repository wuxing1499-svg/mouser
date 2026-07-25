"""Tests for gui.ipc: NDJSON serialization and parsing."""

from __future__ import annotations

import io

from gui.ipc import deserialize_ndjson_stream, serialize_message


def test_serialize_message_single_line() -> None:
    """serialize_message produces exactly one JSON line ending with \\n."""
    out = serialize_message({"type": "Hello", "version": "1.0", "pid": 123})

    assert out.endswith("\n")
    assert out.count("\n") == 1
    assert "\r" not in out


def test_serialize_message_compact_separator() -> None:
    """JSON uses compact separators (no spaces after , or :)."""
    out = serialize_message({"type": "Ping"})

    assert out == '{"type":"Ping"}\n'


def test_serialize_message_utf8_preserved() -> None:
    """Non-ASCII text is preserved as UTF-8 characters, not escaped."""
    out = serialize_message({"type": "ClipboardUpdate", "text": "héllo"})

    assert "héllo" in out
    assert "\\u" not in out


def test_deserialize_yields_each_message() -> None:
    """A stream of 3 NDJSON lines yields 3 dicts in order."""
    stream = io.StringIO(
        '{"type":"Hello","pid":1}\n'
        '{"type":"Status","state":"connecting"}\n'
        '{"type":"Pong"}\n'
    )

    msgs = list(deserialize_ndjson_stream(stream))

    assert msgs == [
        {"type": "Hello", "pid": 1},
        {"type": "Status", "state": "connecting"},
        {"type": "Pong"},
    ]


def test_deserialize_skips_blank_lines() -> None:
    """Blank lines in the stream are skipped, not yielded as None or empty."""
    stream = io.StringIO('\n{"type":"Ping"}\n\n{"type":"Pong"}\n')

    msgs = list(deserialize_ndjson_stream(stream))

    assert msgs == [{"type": "Ping"}, {"type": "Pong"}]


def test_deserialize_skips_malformed_lines() -> None:
    """Malformed JSON lines are skipped (not crash), valid lines still yielded."""
    stream = io.StringIO(
        '{"type":"Hello"}\n'
        'this is not json\n'
        '{"type":"Pong"}\n'
    )

    msgs = list(deserialize_ndjson_stream(stream))

    assert msgs == [{"type": "Hello"}, {"type": "Pong"}]
