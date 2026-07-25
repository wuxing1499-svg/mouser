"""Tests for ipc-protocol/messages.json schema validity.

Source: plan/mouser 阶段 5 step 29.
The schema is shared between C++ (deskflow-core IpcChannel) and Python (gui.ipc).
Both sides must agree on message types and field names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REQUIRED_MESSAGE_TYPES = {
    "Hello",
    "Start",
    "Stop",
    "Status",
    "Error",
    "ClipboardUpdate",
    "Ping",
    "Pong",
}

SCHEMA_PATH = Path(__file__).parent.parent / "ipc-protocol" / "messages.json"


@pytest.fixture(scope="module")
def schema() -> dict:
    """Load and parse the schema file once per test module."""
    if not SCHEMA_PATH.exists():
        pytest.fail(f"Schema file missing: {SCHEMA_PATH}")
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_has_version(schema: dict) -> None:
    """Schema declares a version string for future compatibility checks."""
    assert "version" in schema
    assert isinstance(schema["version"], str)
    assert schema["version"]  # non-empty


def test_schema_has_messages_section(schema: dict) -> None:
    """Schema has a top-level 'messages' object."""
    assert "messages" in schema
    assert isinstance(schema["messages"], dict)


def test_schema_includes_all_required_message_types(schema: dict) -> None:
    """All 8 required message types are present in the schema."""
    present = set(schema["messages"].keys())
    missing = REQUIRED_MESSAGE_TYPES - present
    assert not missing, f"Missing message types: {missing}"


def test_each_message_has_fields_definition(schema: dict) -> None:
    """Each message type declares its fields (may be empty dict)."""
    for msg_type, definition in schema["messages"].items():
        assert "fields" in definition, f"Message type {msg_type!r} missing 'fields' key"
        assert isinstance(definition["fields"], dict), (
            f"Message type {msg_type!r} 'fields' must be a dict"
        )


def test_hello_message_fields(schema: dict) -> None:
    """Hello message declares version and pid fields."""
    fields = schema["messages"]["Hello"]["fields"]
    assert "version" in fields
    assert "pid" in fields


def test_status_message_fields(schema: dict) -> None:
    """Status message declares state and detail fields."""
    fields = schema["messages"]["Status"]["fields"]
    assert "state" in fields
    assert "detail" in fields


def test_error_message_fields(schema: dict) -> None:
    """Error message declares code and message fields."""
    fields = schema["messages"]["Error"]["fields"]
    assert "code" in fields
    assert "message" in fields


def test_start_message_has_mode_field(schema: dict) -> None:
    """Start message declares mode field (server|client)."""
    fields = schema["messages"]["Start"]["fields"]
    assert "mode" in fields


def test_clipboard_update_has_text_field(schema: dict) -> None:
    """ClipboardUpdate message declares text field."""
    fields = schema["messages"]["ClipboardUpdate"]["fields"]
    assert "text" in fields
