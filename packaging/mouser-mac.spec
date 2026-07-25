# PyInstaller spec for Mouser on macOS.
#
# Source: plan/mouser 阶段 6 step 32
# Design: spec/mouser "打包流程" — onedir + .app bundle + ad-hoc signing.
#
# Build:
#   pyinstaller packaging/mouser-mac.spec --noconfirm --clean
#
# Prerequisites:
#   - deskflow-core binary built and placed at build/bin/Deskflow.app/Contents/MacOS/deskflow-core
#   - Python deps installed: pip install -r requirements-build.txt
#
# Output:
#   dist/Mouser.app/  (macOS app bundle, ad-hoc signed)
#
# The binary is collected as `binaries=` (not `datas=`) to preserve the
# executable bit. See spec drift D6.

import os
import sys
import tempfile
from pathlib import Path

# PyInstaller's Analysis/EXE/COLLECT are imported automatically when running
# `pyinstaller foo.spec`. When loading the spec via runpy for tests, we must
# ensure CONF['workpath'] is set (PyInstaller's TOC machinery needs it).
from PyInstaller.config import CONF
if "workpath" not in CONF:
    CONF["workpath"] = tempfile.mkdtemp(prefix="pyinstaller-test-")
if "distpath" not in CONF:
    CONF["distpath"] = str(Path.cwd() / "dist")

from PyInstaller.building.build_main import Analysis, COLLECT, EXE
from PyInstaller.utils.hooks import collect_data_files

REPO_ROOT = Path(SPECPATH).resolve() if "SPECPATH" in dir() else Path(__file__).resolve().parent.parent

# Locate the deskflow-core binary. CI builds it to build/bin/...; local dev
# may have it elsewhere. We try multiple candidates.
BINARY_CANDIDATES = [
    REPO_ROOT / "build" / "bin" / "Deskflow.app" / "Contents" / "MacOS" / "deskflow-core",
    REPO_ROOT / "bin" / "deskflow-core",
]

binary_path = None
for candidate in BINARY_CANDIDATES:
    if candidate.exists():
        binary_path = candidate
        break

if binary_path is None:
    raise FileNotFoundError(
        "deskflow-core binary not found. Build it first with:\n"
        "  cmake -S vendor/deskflow -B build -DCMAKE_OSX_SYSROOT=$(xcrun --show-sdk-path) "
        "-DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt -DBUILD_X11_SUPPORT=OFF\n"
        "  cmake --build build --target deskflow-core -j 4\n"
        f"Expected one of: {[str(c) for c in BINARY_CANDIDATES]}"
    )

# Collect Qt plugins, translations, resources for PySide6.
qt_data = collect_data_files("PySide6", include_py_files=False)

# ipc-protocol/messages.json is needed at runtime by gui.ipc for schema validation.
protocol_data = [
    (
        str(REPO_ROOT / "ipc-protocol" / "messages.json"),
        "ipc-protocol",
    ),
]

# Tray SVG icons are loaded from gui/resources/ at runtime.
resources_data = [
    (
        str(REPO_ROOT / "gui" / "resources"),
        "gui/resources",
    ),
]

a = Analysis(
    [str(REPO_ROOT / "gui" / "main.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[
        # (source_path, dest_dir_inside_bundle)
        # dest_dir 'bin' matches gui.ipc.bundled_binary()'s expectation.
        (str(binary_path), "bin"),
    ],
    datas=qt_data + protocol_data + resources_data,
    hiddenimports=["platformdirs"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Trim Qt modules we don't use to reduce bundle size (~80-100MB).
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
    console=False,  # GUI app; no terminal window
    icon=str(REPO_ROOT / "gui" / "resources" / "tray-connected.svg"),  # fallback if no .icns
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mouser",
    app_bundle=True,  # Produce Mouser.app/Contents/MacOS/Mouser
)
