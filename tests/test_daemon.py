"""Tests for gui.daemon: DaemonProcess subprocess lifecycle + IPC.

Uses a Python "fake daemon" script as the spawned binary to avoid
needing the real C++ deskflow-core binary for testing.
"""

from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest

from gui.daemon import DaemonProcess


@pytest.fixture
def fake_daemon(tmp_path: Path) -> Path:
    """Create a Python script that mimics deskflow-core IPC behavior.

    - Reads NDJSON from stdin
    - Writes NDJSON to stderr (Hello on start, Pong on Ping, Status on Start)
    - Exits cleanly on Stop
    """
    script = tmp_path / "fake_daemon.py"
    script.write_text(
        textwrap.dedent(
            """
            import json, sys, os

            def send(msg):
                sys.stderr.write(json.dumps(msg, separators=(',', ':')) + '\\n')
                sys.stderr.flush()

            # Hello on startup
            send({"type": "Hello", "version": "1.0", "pid": os.getpid()})

            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = msg.get("type")
                if t == "Ping":
                    send({"type": "Pong"})
                elif t == "Start":
                    send({"type": "Status", "state": "connecting", "detail": "starting"})
                    send({"type": "Status", "state": "connected", "detail": "peer"})
                elif t == "Stop":
                    send({"type": "Status", "state": "disconnected", "detail": "stopping"})
                    break
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_daemon_spawn_receives_hello(fake_daemon: Path) -> None:
    """DaemonProcess.start() spawns binary and receives Hello within timeout."""
    received: list[dict] = []

    dp = DaemonProcess(
        binary_path=sys.executable,
        binary_args=[str(fake_daemon)],
        on_message=received.append,
    )

    dp.start()
    try:
        # Wait for Hello message (up to 2s)
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            m.get("type") == "Hello" for m in received
        ):
            time.sleep(0.05)
    finally:
        dp.stop(timeout=1.0)

    hello_msgs = [m for m in received if m.get("type") == "Hello"]
    assert len(hello_msgs) == 1
    assert hello_msgs[0]["version"] == "1.0"
    assert isinstance(hello_msgs[0]["pid"], int)


def test_daemon_send_ping_receives_pong(fake_daemon: Path) -> None:
    """DaemonProcess.send_message(Ping) triggers Pong response."""
    received: list[dict] = []

    dp = DaemonProcess(
        binary_path=sys.executable,
        binary_args=[str(fake_daemon)],
        on_message=received.append,
    )

    dp.start()
    try:
        # Wait for Hello first
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            m.get("type") == "Hello" for m in received
        ):
            time.sleep(0.05)

        received.clear()
        dp.send_message({"type": "Ping"})

        # Wait for Pong
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            m.get("type") == "Pong" for m in received
        ):
            time.sleep(0.05)
    finally:
        dp.stop(timeout=1.0)

    assert any(m.get("type") == "Pong" for m in received)


def test_daemon_stop_sends_stop_and_waits(fake_daemon: Path) -> None:
    """DaemonProcess.stop() sends Stop message and waits for process exit."""
    dp = DaemonProcess(
        binary_path=sys.executable,
        binary_args=[str(fake_daemon)],
        on_message=lambda _m: None,
    )

    dp.start()
    assert dp.is_running()

    dp.stop(timeout=2.0)

    assert not dp.is_running()


def test_daemon_send_start_emits_status(fake_daemon: Path) -> None:
    """DaemonProcess.send_message(Start) triggers Status messages."""
    received: list[dict] = []

    dp = DaemonProcess(
        binary_path=sys.executable,
        binary_args=[str(fake_daemon)],
        on_message=received.append,
    )

    dp.start()
    try:
        # Wait for Hello
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            m.get("type") == "Hello" for m in received
        ):
            time.sleep(0.05)

        received.clear()
        dp.send_message({"type": "Start", "mode": "server", "config": {}})

        # Wait for connected Status
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            m.get("state") == "connected" for m in received
        ):
            time.sleep(0.05)
    finally:
        dp.stop(timeout=1.0)

    states = [m.get("state") for m in received if m.get("type") == "Status"]
    assert "connecting" in states
    assert "connected" in states
