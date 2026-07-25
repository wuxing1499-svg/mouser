# PyInstaller spec for Mouser on Windows.
#
# Source: plan/mouser 阶段 6 step 33
# Design: spec/mouser "打包流程" — onedir + zip portable.
#
# Build (PowerShell or cmd):
#   pyinstaller packaging\mouser-win.spec --noconfirm --clean
#
# Prerequisites:
#   - deskflow-core.exe built (Windows MSVC build, out of scope for v1 macOS dev)
#   - Python deps: pip install -r requirements-build.txt
#
# Output:
#   dist\Mouser\Mouser.exe  (onedir, portable)

import os
import tempfile
from pathlib import Path

# Ensure PyInstaller CONF is initialized (for runpy-based spec loading in tests).
from PyInstaller.config import CONF
if "workpath" not in CONF:
    CONF["workpath"] = tempfile.mkdtemp(prefix="pyinstaller-test-")
if "distpath" not in CONF:
    CONF["distpath"] = str(Path.cwd() / "dist")

from PyInstaller.building.build_main import Analysis, COLLECT, EXE
from PyInstaller.utils.hooks import collect_data_files

# SPECPATH is the spec file's directory (packaging/), so parent is repo root.
# When loaded via runpy for tests (no SPECPATH), fall back to __file__.
REPO_ROOT = (
    Path(SPECPATH).resolve().parent
    if "SPECPATH" in dir()
    else Path(__file__).resolve().parent.parent
)

# Locate the deskflow-core.exe binary.
BINARY_CANDIDATES = [
    REPO_ROOT / "build" / "bin" / "deskflow-core.exe",
    REPO_ROOT / "bin" / "deskflow-core.exe",
]

binary_path = None
for candidate in BINARY_CANDIDATES:
    if candidate.exists():
        binary_path = candidate
        break

if binary_path is None:
    raise FileNotFoundError(
        "deskflow-core.exe binary not found. Build it first with cmake on Windows.\n"
        f"Expected one of: {[str(c) for c in BINARY_CANDIDATES]}"
    )

qt_data = collect_data_files("PySide6", include_py_files=False)

protocol_data = [
    (str(REPO_ROOT / "ipc-protocol" / "messages.json"), "ipc-protocol"),
]

resources_data = [
    (str(REPO_ROOT / "gui" / "resources"), "gui/resources"),
]

a = Analysis(
    [str(REPO_ROOT / "gui" / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[
        (str(binary_path), "bin"),
    ],
    datas=qt_data + protocol_data + resources_data,
    hiddenimports=["platformdirs"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebSockets",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPdfWidgets",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtTest",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPrintSupport",
        "PySide6.QtDesigner",
        "PySide6.QtHelp",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSvgWidgets",
        "PySide6.QtUiTools",
        "PySide6.QtXml",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mouser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI app; no console window (gui.daemon adds CREATE_NO_WINDOW)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mouser",
)
