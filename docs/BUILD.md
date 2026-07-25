# Build Mouser Locally

> Source: plan/mouser 阶段 9 step 42
> 本地构建步骤(macOS + Windows)。CI 配置见 `.github/workflows/`。

## 通用前置

1. **Git submodules** — Mouser 内嵌 Deskflow v1.26.0:
   ```bash
   git submodule update --init --recursive
   ```
2. **Python 3.10+** — 推荐用 pyenv / 官方安装器
3. **Python 依赖**:
   ```bash
   pip install -r requirements-build.txt
   ```
4. **CMake 3.27+** + **Ninja**(可选,但推荐)

## macOS 构建

### 依赖

```bash
brew install qt cmake ninja ccache
```

确认 Qt 路径:

```bash
brew --prefix qt
# /opt/homebrew/opt/qt  (Apple Silicon)
# /usr/local/opt/qt     (Intel)
```

### 一键构建

```bash
./packaging/build.sh
```

脚本会:
1. `cmake -S vendor/deskflow -B build` 配置(默认本机架构)
2. `cmake --build build --target deskflow-core` 编译 C++ core
3. `pyinstaller packaging/mouser-mac.spec` 打包成 `.app`
4. `codesign --force --deep --sign -` ad-hoc 签名(Apple Silicon 必需)

### 指定架构

```bash
./packaging/build.sh arm64    # Apple Silicon
./packaging/build.sh x86_64   # Intel
```

### 产物

- `build/bin/Deskflow.app/Contents/MacOS/deskflow-core` — C++ binary
- `dist/Mouser.app/` — 最终 .app bundle(ad-hoc 已签名)

### 创建 DMG(可选)

```bash
hdiutil create -volname "Mouser" -srcfolder dist/Mouser.app \
  -ov -format UDZO dist/Mouser-macos-$(uname -m).dmg
```

### 验证

```bash
# 签名校验
codesign --verify --verbose=4 dist/Mouser.app

# 启动测试(先重置 Accessibility 权限以模拟首次启动)
tccutil reset Accessibility com.ndq.mouser
open dist/Mouser.app
```

## Windows 构建

### 依赖

1. **Visual Studio 2022 Build Tools** — 含 MSVC v143 + Windows 10/11 SDK
   - 下载: https://visualstudio.microsoft.com/visual-cpp-build-tools/
   - 勾选 "Desktop development with C++"

2. **Qt 6.7.3** — 推荐用 `aqt` 或官方 Qt 在线安装器
   ```powershell
   pip install aqtinstall
   aqt install-qt windows desktop 6.7.3 win64_msvc2022_64
   # 默认装到 .\Qt\6.7.3\msvc2022_64\
   ```

3. **CMake + Ninja**
   ```powershell
   winget install Kitware.CMake
   winget install Ninja-build.Ninja
   ```

### 一键构建

```powershell
.\packaging\build.ps1 -QtPath 'C:\Qt\6.7.3\msvc2022_64'
```

脚本会:
1. `cmake -S vendor/deskflow -B build` 配置
2. `cmake --build build --target deskflow-core` 编译 C++ core
3. `pyinstaller packaging/mouser-win.spec` 打包成 onedir

### 产物

- `build\bin\deskflow-core.exe` — C++ binary
- `dist\Mouser\Mouser.exe` — 最终 onedir 产物

### 创建便携 zip

```powershell
Compress-Archive -Path dist\Mouser\* -DestinationPath dist\Mouser-windows-x86_64.zip -Force
```

### 验证

```powershell
# 启动测试
.\dist\Mouser\Mouser.exe
```

## 仅运行 GUI(开发调试)

不需要打包,直接运行 Python 入口:

```bash
# 用环境变量指定已构建的 deskflow-core binary
MOUSER_BINARY=./build/bin/Deskflow.app/Contents/MacOS/deskflow-core python -m gui.main
```

## 仅运行测试

```bash
pip install -r requirements-dev.txt
pytest                    # 全部单测
ruff check gui/ tests/    # lint
ruff format --check gui/ tests/
```

## CI

GitHub Actions 配置:

- `.github/workflows/test.yml` — 每次 push/PR 跑 ruff + pytest(快速)
- `.github/workflows/build-macos.yml` — tag `v*` 触发,产出 arm64 + x86_64 DMG
- `.github/workflows/build-windows.yml` — tag `v*` 触发,产出 x86_64 zip

## 常见问题

### `ld: library 'pthread' not found` (macOS)

macOS 现代版本无 `libpthread.dylib`,pthread 在 libSystem.B.dylib 内。`vendor/deskflow/cmake/Libraries.cmake` 已处理:macOS 跳过 `-lpthread`。

### `Killed: 9` (Apple Silicon 未签名)

Ad-hoc 签名未生效。手动执行:

```bash
codesign --force --deep --sign - dist/Mouser.app
xattr -dr com.apple.quarantine dist/Mouser.app
```

### PyInstaller 找不到 `deskflow-core`

确保先跑 `cmake --build build --target deskflow-core`,binary 在 `build/bin/` 下。

### Windows `Compress-Archive` 报路径过长

用 7-Zip 替代:

```powershell
7z a dist\Mouser-windows-x86_64.zip .\dist\Mouser\*
```
