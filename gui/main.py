"""Mouser application entry point.

Source: plan/mouser 阶段 4 step 27
Design: spec/mouser "Python GUI 流程" — load config, spawn deskflow-core,
wire tray signals to DaemonProcess, run Qt event loop, heartbeat every 5s.

Usage:
    python -m gui.main           # run with default config path
    python -m gui.main --config /path/to/config.json
    MOUSER_BINARY=/path/to/deskflow-core python -m gui.main  # dev override
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication

from gui.config import MouserConfig
from gui.daemon import DaemonProcess
from gui.ipc import bundled_binary
from gui.tray import MouserTray, TrayState

__all__ = ["main"]

HEARTBEAT_INTERVAL_SEC = 5.0
HEARTBEAT_MISS_THRESHOLD = 3
DEFAULT_CONFIG_NAME = "config.json"


def _default_config_path() -> Path:
    """Return platform-appropriate config path via platformdirs."""
    try:
        from platformdirs import user_config_path
    except ImportError:
        # Fallback if platformdirs not installed (shouldn't happen in venv).
        return Path.home() / ".config" / "mouser" / DEFAULT_CONFIG_NAME
    return user_config_path("mouser") / DEFAULT_CONFIG_NAME


def _resolve_binary() -> str:
    """Locate deskflow-core binary.

    Priority:
      1. MOUSER_BINARY env var (dev / debugging).
      2. Bundled binary via PyInstaller _MEIPASS / cwd.
      3. System PATH lookup (last resort).
    """
    env = os.environ.get("MOUSER_BINARY")
    if env and Path(env).exists():
        return env
    try:
        name = "deskflow-core.exe" if sys.platform == "win32" else "deskflow-core"
        return bundled_binary(name)
    except FileNotFoundError:
        # Last-resort: assume it's on PATH.
        return "deskflow-core"


def _build_start_config_message(cfg: MouserConfig) -> dict:
    """Translate MouserConfig into a Start IPC message payload."""
    return {
        "type": "Start",
        "mode": cfg.mode,
        "config": {
            "port": cfg.port,
            "local_host": cfg.local_host,
            "screens": [
                {"host": s.host, "position": s.position} for s in cfg.screens
            ],
        },
    }


class MouserApp:
    """Wires tray, daemon, config, and heartbeat together.

    Owned by main(). Holds references so Qt parent-child ownership
    doesn't garbage-collect them mid-event-loop.
    """

    def __init__(self, config: MouserConfig, binary_path: str) -> None:
        self._config = config
        self._binary_path = binary_path
        self._daemon: DaemonProcess | None = None
        self._tray: MouserTray | None = None
        self._heartbeat_timer: QTimer | None = None
        self._last_pong_time = 0.0
        self._missed_pings = 0

    def start(self, app: QApplication) -> None:
        """Create tray, wire signals, start heartbeat timer."""
        self._tray = MouserTray(parent=app)
        if not self._tray.is_available():
            print(
                "WARNING: system tray not available on this platform; "
                "GUI will run headless.",
                file=sys.stderr,
            )
        self._tray.start_requested.connect(self._on_start)
        self._tray.stop_requested.connect(self._on_stop)
        self._tray.restart_requested.connect(self._on_restart)
        self._tray.mode_changed.connect(self._on_mode_changed)
        self._tray.quit_requested.connect(self._on_quit)
        self._tray.set_state(TrayState.DISCONNECTED, "ready")
        self._tray.show()

        # Heartbeat: every HEARTBEAT_INTERVAL_SEC, ping the daemon.
        self._heartbeat_timer = QTimer(parent=app)
        self._heartbeat_timer.setInterval(int(HEARTBEAT_INTERVAL_SEC * 1000))
        self._heartbeat_timer.timeout.connect(self._on_heartbeat)
        self._heartbeat_timer.setTimerType(Qt.PreciseTimer)

    # ---- tray signal handlers -----------------------------------------------

    def _on_start(self, mode: str) -> None:
        if self._daemon is not None and self._daemon.is_running():
            return
        self._config.mode = mode  # type: ignore[assignment]
        self._spawn_daemon()

    def _on_stop(self) -> None:
        self._stop_daemon()

    def _on_restart(self) -> None:
        self._stop_daemon()
        # Brief delay so port release completes; Qt single-shot.
        QTimer.singleShot(300, self._spawn_daemon)

    def _on_mode_changed(self, mode: str) -> None:
        self._config.mode = mode  # type: ignore[assignment]

    def _on_quit(self) -> None:
        self._stop_daemon()
        QApplication.quit()

    # ---- daemon lifecycle ---------------------------------------------------

    def _spawn_daemon(self) -> None:
        """Start DaemonProcess and send Start with current config."""
        assert self._tray is not None
        self._tray.set_state(TrayState.CONNECTING, "spawning daemon")

        # daemon args: positional 'server' or 'client' (per spec D9 / deskflow-core --help)
        mode_arg = "server" if self._config.mode == "server" else "client"
        self._daemon = DaemonProcess(
            binary_path=self._binary_path,
            binary_args=[mode_arg, "--new-instance"],
            on_message=self._on_daemon_message,
        )
        try:
            self._daemon.start()
        except OSError as e:
            self._tray.set_state(TrayState.ERROR, f"spawn failed: {e}")
            self._tray.show_message("Mouser", f"Failed to start daemon:\n{e}")
            self._daemon = None
            return

        self._last_pong_time = time.time()
        self._missed_pings = 0
        self._heartbeat_timer.start()

        # Send Start once daemon is alive. (Hello will arrive async.)
        QTimer.singleShot(100, lambda: self._send_start())

    def _send_start(self) -> None:
        if self._daemon is None or not self._daemon.is_running():
            return
        try:
            self._daemon.send_message(_build_start_config_message(self._config))
        except (OSError, RuntimeError) as e:
            assert self._tray is not None
            self._tray.set_state(TrayState.ERROR, f"start failed: {e}")

    def _stop_daemon(self) -> None:
        assert self._tray is not None
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()
        if self._daemon is None:
            self._tray.set_state(TrayState.DISCONNECTED, "ready")
            return
        try:
            self._daemon.stop(timeout=3.0)
        except Exception as e:  # noqa: BLE001
            self._tray.show_message("Mouser", f"Daemon stop error:\n{e}")
        finally:
            self._daemon = None
            self._tray.set_state(TrayState.DISCONNECTED, "ready")

    # ---- daemon message handler --------------------------------------------

    def _on_daemon_message(self, msg: dict) -> None:
        """Dispatch incoming NDJSON messages from the daemon."""
        assert self._tray is not None
        t = msg.get("type")

        if t == "Hello":
            # Daemon ready; nothing to do (Start was queued in _spawn_daemon).
            pass
        elif t == "Status":
            state = msg.get("state", "")
            detail = msg.get("detail", "")
            if state == "connecting":
                self._tray.set_state(TrayState.CONNECTING, detail)
            elif state == "connected":
                self._tray.set_state(TrayState.CONNECTED, detail)
            elif state == "disconnected":
                self._tray.set_state(TrayState.DISCONNECTED, detail)
        elif t == "Error":
            self._tray.set_state(
                TrayState.ERROR, msg.get("message", "unknown error")
            )
            self._tray.show_message(
                "Mouser error", msg.get("message", "Daemon reported an error")
            )
        elif t == "ClipboardUpdate":
            # v1: clipboard sync is daemon-internal. Surface to tray tooltip only.
            text = msg.get("text", "")
            preview = text[:40] + ("…" if len(text) > 40 else "")
            self._tray.setToolTip(f"Mouser — clipboard: {preview}")
        elif t == "Pong":
            self._last_pong_time = time.time()
            self._missed_pings = 0

    # ---- heartbeat ----------------------------------------------------------

    def _on_heartbeat(self) -> None:
        if self._daemon is None or not self._daemon.is_running():
            self._heartbeat_timer.stop()
            return
        try:
            self._daemon.send_message({"type": "Ping"})
        except (OSError, RuntimeError):
            # stdin broken; daemon likely dead.
            self._missed_pings += 1
        else:
            now = time.time()
            if now - self._last_pong_time > HEARTBEAT_INTERVAL_SEC * 2:
                self._missed_pings += 1
            else:
                self._missed_pings = 0

        if self._missed_pings >= HEARTBEAT_MISS_THRESHOLD:
            assert self._tray is not None
            self._tray.set_state(TrayState.ERROR, "daemon hung (no Pong)")
            self._tray.show_message(
                "Mouser", "Daemon not responding. Click Restart to recover."
            )
            self._heartbeat_timer.stop()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Parse --config path (simple parse; v1 doesn't need argparse for one flag).
    config_path = _default_config_path()
    i = 0
    while i < len(argv):
        if argv[i] == "--config" and i + 1 < len(argv):
            config_path = Path(argv[i + 1])
            i += 2
        else:
            i += 1

    config = MouserConfig.load(config_path)
    binary_path = _resolve_binary()

    # Allow Ctrl-C to terminate the Qt event loop cleanly.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # tray-only app; no main window

    mouser = MouserApp(config, binary_path)
    mouser.start(app)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
