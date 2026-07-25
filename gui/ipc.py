"""NDJSON serialization for IPC between GUI and deskflow-core daemon.

Source: plan/mouser 阶段 4 step 23
Design: spec/mouser "Integration layer" — NDJSON over stderr/stdin.

The daemon (C++) writes JSON lines to stderr; the GUI (Python) reads them.
The GUI writes JSON lines to the daemon's stdin; the daemon reads them.

This module only handles (de)serialization and binary path resolution.
Spawning the daemon subprocess lives in `gui.daemon`.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, TextIO

__all__ = ["serialize_message", "deserialize_ndjson_stream", "bundled_binary"]

Message = Dict[str, Any]


def serialize_message(msg: Message) -> str:
    """Serialize a message dict to a single NDJSON line (ending with \\n).

    Uses compact separators to keep wire size minimal. Non-ASCII characters
    are preserved as UTF-8 (ensure_ascii=False) — both Python's json and
    Qt's QJsonDocument handle UTF-8 natively.
    """
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False) + "\n"


def deserialize_ndjson_stream(stream: TextIO) -> Iterator[Message]:
    """Yield parsed message dicts from a text stream of NDJSON lines.

    Blank lines and malformed JSON lines are silently skipped. NDJSON
    consumers must tolerate malformed lines (e.g. partial writes from
    a crashing daemon) without aborting the whole stream.
    """
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _bundle_root() -> Path:
    """Return the directory where PyInstaller collected datas/binaries.

    - Onefile: the _MEIxxxxx temp extraction dir.
    - Onedir:  dist/<name>/_internal/  (PyInstaller 6+).
    - Dev run: the current working directory (so `python main.py` from
      the repo root finds `./bin/deskflow-core`).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path.cwd()


def bundled_binary(name: str) -> str:
    """Return absolute path to an embedded native binary.

    `name` is the basename (e.g. "deskflow-core" on macOS/Linux,
    "deskflow-core.exe" on Windows). The spec collects it under 'bin/'.

    On Unix, ensures the executable bit is set (defensive: `binaries=`
    in PyInstaller should preserve it, but onefile extraction on some
    filesystems drops it).

    Raises FileNotFoundError if the binary is not present.
    """
    p = _bundle_root() / "bin" / name
    if not p.exists():
        raise FileNotFoundError(f"Embedded binary missing: {p}")
    if sys.platform != "win32":
        mode = p.stat().st_mode
        if not (mode & stat.S_IXUSR):
            p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)
