"""Tests for gui.ipc.bundled_binary: PyInstaller bundle path resolution.

Source: plan/mouser 阶段 4 step 23 — bundled_binary() function.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from unittest import mock

import pytest

from gui.ipc import bundled_binary


def test_dev_mode_returns_path_next_to_package(tmp_path: Path) -> None:
    """When not running under PyInstaller, binary is resolved from cwd."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    binary = bin_dir / "deskflow-core"
    binary.write_text("fake")
    if sys.platform != "win32":
        binary.chmod(0o755)

    with mock.patch.object(sys, "_MEIPASS", None, create=True), \
         mock.patch.object(Path, "cwd", return_value=tmp_path):
        # On non-Windows, also patch the platform check to avoid chmod on fake binary
        result = bundled_binary("deskflow-core")

    assert Path(result).name == "deskflow-core"
    assert Path(result).exists()


def test_meipass_mode_returns_path_in_bundle(tmp_path: Path) -> None:
    """When running under PyInstaller, binary is resolved from sys._MEIPASS."""
    bundle = tmp_path / "bundle"
    bin_dir = bundle / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "deskflow-core"
    binary.write_text("fake")
    if sys.platform != "win32":
        binary.chmod(0o755)

    with mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
        result = bundled_binary("deskflow-core")

    assert result == str(bundle / "bin" / "deskflow-core")


def test_missing_binary_raises_filenotfound(tmp_path: Path) -> None:
    """Missing embedded binary raises FileNotFoundError, not silent failure."""
    with mock.patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
        with pytest.raises(FileNotFoundError):
            bundled_binary("nonexistent-binary")


@pytest.mark.skipif(sys.platform == "win32", reason="exec bit is Unix-only concept")
def test_exec_bit_set_on_unix(tmp_path: Path) -> None:
    """On Unix, bundled_binary ensures the file has +x permission."""
    bundle = tmp_path / "bundle"
    bin_dir = bundle / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / "deskflow-core"
    binary.write_text("fake")
    binary.chmod(0o644)  # no exec bit

    assert not (binary.stat().st_mode & stat.S_IXUSR)

    with mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
        bundled_binary("deskflow-core")

    assert binary.stat().st_mode & stat.S_IXUSR
