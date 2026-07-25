"""Tests for gui.config: MouserConfig round-trip serialization."""

from __future__ import annotations

import json
from pathlib import Path

from gui.config import MouserConfig, ScreenConfig


def test_config_roundtrip_server_mode(tmp_path: Path) -> None:
    """Server-mode config serialized to JSON and back preserves all fields."""
    original = MouserConfig(
        mode="server",
        port=24800,
        local_host="192.168.1.10",
        screens=[
            ScreenConfig(host="win-client", position="right"),
            ScreenConfig(host="mac-other", position="left"),
        ],
    )

    path = tmp_path / "config.json"
    original.save(path)

    loaded = MouserConfig.load(path)

    assert loaded.mode == "server"
    assert loaded.port == 24800
    assert loaded.local_host == "192.168.1.10"
    assert loaded.screens == [
        ScreenConfig(host="win-client", position="right"),
        ScreenConfig(host="mac-other", position="left"),
    ]


def test_config_roundtrip_client_mode(tmp_path: Path) -> None:
    """Client-mode config (empty screens) round-trips correctly."""
    original = MouserConfig(
        mode="client",
        port=24800,
        local_host="192.168.1.20",
        screens=[],
    )

    path = tmp_path / "config.json"
    original.save(path)

    loaded = MouserConfig.load(path)

    assert loaded.mode == "client"
    assert loaded.screens == []


def test_config_defaults(tmp_path: Path) -> None:
    """Default-constructed config has sensible defaults."""
    cfg = MouserConfig()

    assert cfg.mode == "server"
    assert cfg.port == 24800
    assert cfg.local_host == ""
    assert cfg.screens == []


def test_config_json_shape(tmp_path: Path) -> None:
    """Serialized JSON has the documented top-level keys."""
    cfg = MouserConfig(mode="client", port=12345, local_host="x", screens=[])
    path = tmp_path / "config.json"
    cfg.save(path)

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert set(raw.keys()) == {"mode", "port", "local_host", "screens"}
    assert raw["mode"] == "client"
    assert raw["port"] == 12345


def test_screen_config_rejects_invalid_position() -> None:
    """ScreenConfig.position must be one of left/right/top/bottom."""
    import pytest

    with pytest.raises(ValueError):
        ScreenConfig(host="x", position="middle")  # type: ignore[arg-type]
