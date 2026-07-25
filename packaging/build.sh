#!/usr/bin/env bash
# Build Mouser on macOS: C++ core (deskflow-core) + PyInstaller .app bundle.
#
# Source: plan/mouser 阶段 6 step 34
#
# Usage:
#   ./packaging/build.sh                # arm64 native (default)
#   ./packaging/build.sh x86_64         # x86_64 native (macos-13 runner)
#   ARCH=arm64 ./packaging/build.sh
#
# Prerequisites:
#   - Xcode Command Line Tools (xcrun --show-sdk-path works)
#   - Qt 6 installed via brew: brew install qt cmake ninja
#   - Python 3.10+ with: pip install -r requirements-build.txt
#
# Output:
#   build/bin/Deskflow.app/Contents/MacOS/deskflow-core  (C++ binary)
#   dist/Mouser.app/                                     (final bundle, ad-hoc signed)

set -euo pipefail

# Resolve repo root (parent of packaging/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Target arch: arm64 (Apple Silicon) or x86_64 (Intel).
ARCH="${1:-${ARCH:-$(uname -m)}}"

# Locate Qt. Prefer Homebrew path; fall back to CMAKE_PREFIX_PATH env var.
if [[ -z "${CMAKE_PREFIX_PATH:-}" ]]; then
  if [[ -d /opt/homebrew/opt/qt ]]; then
    CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt"
  elif [[ -d /usr/local/opt/qt ]]; then
    CMAKE_PREFIX_PATH="/usr/local/opt/qt"
  fi
fi

echo "==> Mouser macOS build"
echo "    repo:   ${REPO_ROOT}"
echo "    arch:   ${ARCH}"
echo "    qt:     ${CMAKE_PREFIX_PATH:-<not found>}"

# Step 1: Configure & build C++ core (deskflow-core only).
BUILD_DIR="${REPO_ROOT}/build"
echo "==> [1/3] cmake configure deskflow-core"
cmake -S vendor/deskflow -B "${BUILD_DIR}" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES="${ARCH}" \
  -DCMAKE_OSX_SYSROOT="$(xcrun --show-sdk-path)" \
  -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}" \
  -DBUILD_X11_SUPPORT=OFF

echo "==> [2/3] cmake build deskflow-core"
cmake --build "${BUILD_DIR}" --target deskflow-core -j "$(sysctl -n hw.ncpu)"

BINARY="${BUILD_DIR}/bin/Deskflow.app/Contents/MacOS/deskflow-core"
if [[ ! -x "${BINARY}" ]]; then
  echo "ERROR: deskflow-core binary not found at ${BINARY}" >&2
  exit 1
fi
echo "    built:  ${BINARY}"

# Step 2: PyInstaller.
echo "==> [3/3] pyinstaller mouser-mac.spec"
pyinstaller packaging/mouser-mac.spec --noconfirm --clean

APP_BUNDLE="${REPO_ROOT}/dist/Mouser.app"
if [[ ! -d "${APP_BUNDLE}" ]]; then
  echo "ERROR: Mouser.app not produced at ${APP_BUNDLE}" >&2
  exit 1
fi

# Step 3: Ad-hoc sign the .app bundle (required on Apple Silicon, see spec drift D7).
echo "==> codesign ad-hoc (Apple Silicon requirement)"
codesign --force --deep --sign - "${APP_BUNDLE}"
codesign --verify --verbose=2 "${APP_BUNDLE}" || true

echo "==> done: ${APP_BUNDLE}"
