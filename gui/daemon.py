"""DaemonProcess: manages the deskflow-core subprocess lifecycle and IPC.

Source: plan/mouser 阶段 4 step 22
Design: spec/mouser "Python GUI 流程" — spawn deskflow-core, read stderr
NDJSON, write stdin NDJSON.

Threading model:
- Main thread: GUI event loop calls start()/send_message()/stop().
- Reader thread: continuously reads stderr, parses NDJSON, invokes
  on_message callback. Started once at start(), joined at stop().

The reader thread is daemon-threaded so it won't block interpreter exit
if stop() is never called (e.g. test crash).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

from gui.ipc import deserialize_ndjson_stream, serialize_message

__all__ = ["DaemonProcess"]

Message = Dict[str, Any]
MessageCallback = Callable[[Message], None]


class DaemonProcess:
    """Wraps a deskflow-core subprocess with NDJSON IPC over stdin/stderr.

    The binary is expected to:
    - Write NDJSON messages to stderr (one JSON object per line).
    - Read NDJSON commands from stdin.
    - Exit cleanly after receiving a Stop command (or on stdin EOF).
    """

    def __init__(
        self,
        binary_path: str,
        binary_args: Optional[List[str]] = None,
        on_message: Optional[MessageCallback] = None,
    ) -> None:
        self._binary_path = binary_path
        self._binary_args = binary_args or []
        self._on_message = on_message
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stdin_lock = threading.Lock()

    def start(self) -> None:
        """Spawn the daemon subprocess and begin reading its stderr."""
        if self._proc is not None:
            raise RuntimeError("Daemon already started")

        argv = [self._binary_path] + list(self._binary_args)
        kwargs: Dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "bufsize": 1,  # line-buffered
        }
        # On Windows, suppress the console window for GUI integration.
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NO_WINDOW", 0
            )

        self._proc = subprocess.Popen(argv, **kwargs)

        # stderr must be read continuously to avoid pipe deadlock when
        # the OS buffer fills. Daemon thread so it won't block exit.
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="daemon-stderr-reader",
            daemon=True,
        )
        self._reader_thread.start()

    def send_message(self, msg: Message) -> None:
        """Write one NDJSON command to the daemon's stdin."""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Daemon not started or stdin closed")
        line = serialize_message(msg)
        with self._stdin_lock:
            self._proc.stdin.write(line)
            self._proc.stdin.flush()

    def is_running(self) -> bool:
        """True if the subprocess is still alive."""
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        """Send Stop, wait for exit; force-kill on timeout."""
        if self._proc is None:
            return

        if self.is_running():
            try:
                self.send_message({"type": "Stop"})
            except (OSError, RuntimeError):
                pass  # stdin may already be closed

            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=1.0)

        # Close stdin to signal EOF (helps reader thread exit if still alive).
        if self._proc.stdin and not self._proc.stdin.closed:
            try:
                self._proc.stdin.close()
            except OSError:
                pass

        if self._reader_thread is not None and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1.0)

        if self._proc.stderr and not self._proc.stderr.closed:
            try:
                self._proc.stderr.close()
            except OSError:
                pass

        self._proc = None
        self._reader_thread = None

    def _reader_loop(self) -> None:
        """Read stderr NDJSON lines until EOF, invoking on_message per msg."""
        assert self._proc is not None and self._proc.stderr is not None
        for msg in deserialize_ndjson_stream(self._proc.stderr):
            if self._on_message is not None:
                try:
                    self._on_message(msg)
                except Exception:
                    # Callback errors must not kill the reader thread.
                    pass
