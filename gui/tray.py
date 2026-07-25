"""Mouser system tray icon.

Source: plan/mouser 阶段 4 step 25-26
Design: spec/mouser "Python GUI 流程" — tray icon reflects daemon state.

State machine:
  disconnected  --[start]-->  connecting  --[connected]-->  connected
  connected     --[stop]---->  disconnected
  any           --[error]-->   error  --[restart]-->  connecting

The tray emits user actions via callbacks so gui.main can wire them to
DaemonProcess without tray.py depending on daemon.py.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

__all__ = ["TrayState", "MouserTray"]

RESOURCES_DIR = Path(__file__).parent / "resources"


class TrayState:
    """Daemon states mirrored to tray icon + status label."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class MouserTray(QObject):
    """System tray icon with mode toggle, start/stop, and quit actions.

    Signals (emitted on user action, connected by gui.main):
        start_requested(str mode)  — user clicked Start
        stop_requested()           — user clicked Stop
        restart_requested()        — user clicked Restart (after error)
        mode_changed(str mode)     — user switched mode in menu
        quit_requested()           — user clicked Quit
    """

    start_requested = Signal(str)
    stop_requested = Signal()
    restart_requested = Signal()
    mode_changed = Signal(str)
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._icons = {
            TrayState.DISCONNECTED: self._load_icon("tray-disconnected.svg"),
            TrayState.CONNECTING: self._load_icon("tray-connecting.svg"),
            TrayState.CONNECTED: self._load_icon("tray-connected.svg"),
            TrayState.ERROR: self._load_icon("tray-error.svg"),
        }

        self._tray = QSystemTrayIcon(self._icons[TrayState.DISCONNECTED], self)
        self._tray.setToolTip("Mouser — disconnected")

        self._mode = "server"
        self._state = TrayState.DISCONNECTED
        self._build_menu()
        self._refresh_actions()

    @staticmethod
    def _load_icon(name: str) -> QIcon:
        """Load an SVG icon from gui/resources/. Fallback to empty icon."""
        path = RESOURCES_DIR / name
        if not path.exists():
            return QIcon()
        # QPixmap can render SVG via Qt's SVG support.
        pix = QPixmap(str(path))
        if pix.isNull():
            return QIcon()
        return QIcon(pix)

    def _build_menu(self) -> None:
        """Construct the right-click context menu."""
        menu = QMenu()

        # Mode submenu (Server / Client)
        mode_menu = menu.addMenu("Mode")
        self._act_server = QAction("Server", mode_menu, checkable=True)
        self._act_client = QAction("Client", mode_menu, checkable=True)
        self._act_server.setChecked(True)
        grp = QActionGroup(mode_menu)
        grp.addAction(self._act_server)
        grp.addAction(self._act_client)
        mode_menu.addAction(self._act_server)
        mode_menu.addAction(self._act_client)
        self._act_server.triggered.connect(lambda: self._on_mode("server"))
        self._act_client.triggered.connect(lambda: self._on_mode("client"))

        menu.addSeparator()

        # Start / Stop / Restart
        self._act_start = QAction("Start", menu)
        self._act_stop = QAction("Stop", menu)
        self._act_restart = QAction("Restart daemon", menu)
        self._act_start.triggered.connect(
            lambda: self.start_requested.emit(self._mode)
        )
        self._act_stop.triggered.connect(self.stop_requested.emit)
        self._act_restart.triggered.connect(self.restart_requested.emit)
        menu.addAction(self._act_start)
        menu.addAction(self._act_stop)
        menu.addAction(self._act_restart)

        menu.addSeparator()

        # Status (non-interactive)
        self._act_status = QAction("Status: disconnected", menu)
        self._act_status.setEnabled(False)
        menu.addAction(self._act_status)

        menu.addSeparator()

        # Quit
        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._tray.setContextMenu(menu)

    def _on_mode(self, mode: str) -> None:
        self._mode = mode
        self.mode_changed.emit(mode)

    def _refresh_actions(self) -> None:
        """Enable/disable actions based on current state."""
        can_start = self._state in (TrayState.DISCONNECTED, TrayState.ERROR)
        can_stop = self._state in (TrayState.CONNECTING, TrayState.CONNECTED)
        can_restart = self._state == TrayState.ERROR

        self._act_start.setEnabled(can_start)
        self._act_stop.setEnabled(can_stop)
        self._act_restart.setEnabled(can_restart)

        # Mode toggle only when fully stopped.
        mode_enabled = self._state == TrayState.DISCONNECTED
        self._act_server.setEnabled(mode_enabled)
        self._act_client.setEnabled(mode_enabled)

    def show(self) -> None:
        """Show the tray icon. QApplication must already be running."""
        self._tray.show()

    def set_state(self, state: str, detail: str = "") -> None:
        """Update icon + tooltip + status label + action availability."""
        self._state = state
        icon = self._icons.get(state, self._icons[TrayState.DISCONNECTED])
        self._tray.setIcon(icon)
        tooltip = f"Mouser — {state}"
        if detail:
            tooltip += f" ({detail})"
        self._tray.setToolTip(tooltip)
        self._act_status.setText(f"Status: {state}" + (f" — {detail}" if detail else ""))
        self._refresh_actions()

    def show_message(self, title: str, body: str) -> None:
        """Show a balloon notification (best-effort; some platforms suppress)."""
        self._tray.showMessage(title, body, QSystemTrayIcon.Information, 3000)

    def setToolTip(self, text: str) -> None:
        """Update the tray icon tooltip text."""
        self._tray.setToolTip(text)

    def is_available(self) -> bool:
        """True if the system tray is available on this platform."""
        return QSystemTrayIcon.isSystemTrayAvailable()
