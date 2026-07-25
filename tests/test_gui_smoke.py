"""Smoke test for gui.tray + gui.main wiring using Qt offscreen platform.

Source: plan/mouser 阶段 4 — GUI has no pytest-runnable verification entry
per dev-tdd Step 1, but we can at least verify the app initializes without
crashing under QT_QPA_PLATFORM=offscreen.

This is NOT a full functional test — it verifies:
- MouserTray can be constructed
- MouserApp.start() wires signals without exception
- Mode change signal propagates
- State transitions update tray state
- Heartbeat timer is created but not started (no daemon running)

It does NOT verify:
- Actual subprocess spawn (covered by test_daemon.py)
- Real tray icon rendering (needs display)
- User click interactions (needs display + input)
"""

from __future__ import annotations

import os
import sys

# Force offscreen BEFORE Qt is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from gui.config import MouserConfig
from gui.main import MouserApp, _build_start_config_message
from gui.tray import MouserTray, TrayState


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Single QApplication shared across tests in this module."""
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
    # Don't call app.quit() — it would tear down Qt for subsequent modules.


def test_tray_constructs(qapp: QApplication) -> None:
    """MouserTray can be constructed without a system tray available."""
    MouserTray(parent=qapp)
    # Under offscreen, isSystemTrayAvailable() may be False; that's fine.
    # Construction itself must not crash.


def test_tray_state_transitions(qapp: QApplication) -> None:
    """set_state() updates internal state and refreshes actions."""
    tray = MouserTray(parent=qapp)

    tray.set_state(TrayState.CONNECTING, "spawning")
    assert tray._state == TrayState.CONNECTING

    tray.set_state(TrayState.CONNECTED, "peer-001")
    assert tray._state == TrayState.CONNECTED

    tray.set_state(TrayState.ERROR, "access denied")
    assert tray._state == TrayState.ERROR


def test_tray_start_signal_emits_mode(qapp: QApplication) -> None:
    """start_requested signal carries the current mode string."""
    tray = MouserTray(parent=qapp)
    received: list[str] = []
    tray.start_requested.connect(lambda m: received.append(m))

    # Default mode is 'server'.
    tray._act_start.trigger()
    qapp.processEvents()

    assert received == ["server"]


def test_tray_mode_switch(qapp: QApplication) -> None:
    """Switching to client mode emits mode_changed('client')."""
    tray = MouserTray(parent=qapp)
    received: list[str] = []
    tray.mode_changed.connect(lambda m: received.append(m))

    tray._act_client.trigger()
    qapp.processEvents()

    assert received == ["client"]
    assert tray._mode == "client"


def test_tray_quit_signal(qapp: QApplication) -> None:
    """Quit menu action emits quit_requested."""
    tray = MouserTray(parent=qapp)
    received: list[bool] = []
    tray.quit_requested.connect(lambda: received.append(True))

    # Find the Quit action in the context menu.
    menu = tray._tray.contextMenu()
    quit_act = None
    for act in menu.actions():
        if act.text() == "Quit":
            quit_act = act
            break
    assert quit_act is not None, "Quit action not found in tray menu"

    quit_act.trigger()
    qapp.processEvents()

    assert received == [True]


def test_mouser_app_start_wires_signals(qapp: QApplication) -> None:
    """MouserApp.start() creates tray and heartbeat timer without exception."""
    cfg = MouserConfig()
    # Use a fake binary path so _resolve_binary doesn't fail.
    app = MouserApp(cfg, binary_path=sys.executable)
    app.start(qapp)

    assert app._tray is not None
    assert app._heartbeat_timer is not None
    # Heartbeat should NOT be running yet (no daemon spawned).
    assert not app._heartbeat_timer.isActive()


def test_build_start_config_message_serializes_screens() -> None:
    """_build_start_config_message produces correct IPC payload."""
    from gui.config import ScreenConfig

    cfg = MouserConfig(
        mode="server",
        port=24800,
        local_host="10.0.0.1",
        screens=[ScreenConfig(host="peer", position="right")],
    )

    msg = _build_start_config_message(cfg)

    assert msg["type"] == "Start"
    assert msg["mode"] == "server"
    assert msg["config"]["port"] == 24800
    assert msg["config"]["local_host"] == "10.0.0.1"
    assert msg["config"]["screens"] == [{"host": "peer", "position": "right"}]


def test_mouser_app_handles_daemon_messages(qapp: QApplication) -> None:
    """_on_daemon_message dispatches Status/Error/ClipboardUpdate correctly."""
    cfg = MouserConfig()
    app = MouserApp(cfg, binary_path=sys.executable)
    app.start(qapp)

    # Status: connected
    app._on_daemon_message({"type": "Status", "state": "connected", "detail": "peer-1"})
    assert app._tray._state == TrayState.CONNECTED

    # Error
    app._on_daemon_message({"type": "Error", "code": "X", "message": "boom"})
    assert app._tray._state == TrayState.ERROR

    # ClipboardUpdate (should not crash, should update tooltip)
    app._on_daemon_message({"type": "ClipboardUpdate", "text": "hello world"})
    # No state change expected, but tooltip should contain clipboard text.
    assert "hello world" in app._tray._tray.toolTip()

    # Pong resets heartbeat tracking
    app._missed_pings = 5
    app._on_daemon_message({"type": "Pong"})
    assert app._missed_pings == 0
