# mouser Implementation Plan

> Status: APPROVED
> Source: .claude/artifacts/designs/mouser.md (ALIGNED spec)
> Mode: default
> Iterations: 2 / 3
> Author: ndq
> Last updated: 2026-07-25

## Requirements summary

基于已 ALIGNED 的 mouser spec,把"fork Deskflow + 裁剪 Linux + PySide6 GUI + subprocess IPC + PyInstaller 打包 + GitHub Actions"拆解为可执行的实施步骤。本研究阶段发现 8 处 spec drift(见下),已在 plan 内吸收并标注,需要后续同步回 spec。

## Spec drift findings(research 阶段发现,需后续回写 spec)

| # | Spec 原文 | 实际情况 | Plan 处理 |
|---|---|---|---|
| D1 | `mouserd` / `mouserc` 双 daemon 二进制 | 单一 `deskflow-core` binary,`--server`/`--client` 切换 | Plan 用 `deskflow-core`,改名延后到 v2 |
| D2 | 未提及 Windows daemon | `deskflow-daemon` Windows-only 服务管理器 | v1 不集成 daemon,直接 spawn `deskflow-core`(无服务化) |
| D3 | "NDJSON over stdin/stdout" | stdout 已被 ConsoleLogOutputter 占用日志 | Plan 选 stderr 输出 NDJSON,日志保留 stdout |
| D4 | 未提及现有 IPC | `src/lib/deskflow/ipc/CoreIpcServer.h`(QLocalSocket)| Plan 新增独立 NDJSON 通道,不动 CoreIpcServer |
| D5 | "src/lib/arch/ 新增 IPC 通道" | `src/lib/arch/unix/` 是 macOS+Linux 共享 | 改在 `src/apps/deskflow-core/` 内新增 IPC 模块,不污染 arch 层 |
| D6 | "PyInstaller 嵌入 binary 作为 datas" | `datas` 不保留 exec bit | 改用 `binaries=` |
| D7 | "未签名,文档化 xattr -c" | Apple Silicon 未签名 binary `Killed: 9` | Plan 加 ad-hoc 签名步骤(`codesign --force --deep --sign -`) |
| D8 | "用 universal2 或分发两份" | PyInstaller 不支持 universal2 | 强制两份:arm64 + x86_64 |

## Acceptance criteria

(从 spec 继承 10 条 AC,补充 3 条新 AC 应对 drift)

- AC-1 ~ AC-10 见 spec
- AC-11(新)打包后的 macOS .app 通过 `codesign --verify` ad-hoc 签名校验,Apple Silicon 上 `deskflow-core` 子进程可正常启动(非 `Killed: 9`)
- AC-12(新)`deskflow-core` 启动后,GUI 通过 stderr 收到首条 `HELLO` NDJSON 消息,JSON 解析成功
- AC-13(新)GitHub Actions 在 `macos-14`(arm64)、`macos-13`(x86_64)、`windows-2022` 三个 runner 上各产出一份可下载的产物

---

## RALPLAN-DR

### Principles

1. **最小代码** —— Deskflow core 改动限制在 IPC 模块新增 + 平台裁剪,不修改其内部输入/网络/剪贴板逻辑
2. **外科手术式改动** —— 只动本 plan 列出的具体文件,不顺手重构
3. **不假设** —— 所有 spec drift 显式列出,等用户确认后再回写 spec
4. **可验证** —— 每个 AC 有具体验证命令或测试步骤
5. **v1 锁版本** —— Deskflow 锁 v1.26.0 tag,不追 master

### Decision drivers

1. **C++ 维护成本**(user Python 主栈)→ 优先最小化 C++ 改动
2. **跨平台一致性** → GUI 同一份代码跑 Mac+Win,差异仅在 binary 名与托盘资源
3. **打包可分发** → CI 产物在干净机器可双击运行
4. **上游 rebase 可行性** → 改动越少越易追上游
5. **macOS Apple Silicon 可运行** → 必须解决签名问题

### Viable options

#### Option A:NDJSON over stderr + 独立 IPC 模块(推荐)

**实现思路**:
- 在 `src/apps/deskflow-core/` 新增 `IpcChannel` 类,NDJSON 走 stderr(避开 stdout 已被 ConsoleLogOutputter 占用)
- Python GUI `subprocess.Popen` 监听 stderr,stdin 发控制命令
- stdout 保留给 Deskflow 原有日志(GUI 可选 tail 用于诊断)
- 不动现有 `CoreIpcServer`(Qt QLocalSocket),新通道独立

**改动文件**:
- 新增:`src/apps/deskflow-core/IpcChannel.h` / `.cpp` / `IpcMessages.h`
- 修改:`src/apps/deskflow-core/deskflow-core.cpp`(注入 IpcChannel)
- 修改:`src/apps/deskflow-core/CMakeLists.txt`(加新源文件)
- 新增 Python:`gui/ipc.py`、`gui/daemon.py`、`gui/tray.py`、`gui/config.py`、`gui/main.py`
- 新增 packaging:`packaging/mouser.spec`(Mac)、`packaging/mouser-win.spec`(Win)
- 新增 CI:`.github/workflows/build-macos.yml`、`.github/workflows/build-windows.yml`

**Pros**:
- C++ 改动最小(只加一个新模块,不碰老逻辑)
- 日志与 IPC 分离,调试时仍可看 stdout 日志
- 不依赖 Qt 事件循环从 Python 端访问 QLocalSocket
- stderr 是天然双向管道,跨平台无差异

**Cons**:
- 多了一个通道(CoreIpcServer 仍存在但 v1 不用)
- stderr 在某些 CI 环境(Windows)缓冲行为不同,需显式 `setvbuf` 或 `fflush`

#### Option B:复用 CoreIpcServer(QLocalSocket) + Python 端用 PySide6 的 QLocalSocket

**实现思路**:
- 不动 Deskflow 的 `CoreIpcServer`,Python GUI 通过 PySide6 的 `QLocalSocket` 连接
- 协议沿用 Deskflow 现有 IPC 消息格式

**改动文件**:
- 不改 C++(零改动!)
- 新增 Python:`gui/ipc_client.py`(用 `PySide6.QtNetwork.QLocalSocket`)
- 其他 GUI / packaging / CI 同 Option A

**Pros**:
- C++ 零改动,完全契合"最小代码"原则
- 复用上游已稳定 IPC 实现,rebase 零冲突

**Cons**:
- Python 端必须跑 Qt 事件循环(`QApplication.exec_`),与 subprocess + threading 模式耦合
- `CoreIpcServer` 协议是 Deskflow 内部格式(非 NDJSON),需写 Python 端协议解析器,且未来上游改协议会断
- Windows 上 QLocalSocket 命名管道路径行为差异,跨平台一致性差
- 无法在 GUI 启动前用 CLI 工具直接测 daemon(失去可调试性)
- `CoreIpcServer` 主要为 `deskflow-daemon`(Windows-only)设计,macOS 上 `deskflow-core` 是否默认监听需验证 —— **未验证假设**

#### Option C(被否决):NDJSON over stdout,先重定向日志到 stderr

**实现思路**:把 ConsoleLogOutputter 重定向到 stderr,stdout 让给 NDJSON。

**Invalidation rationale**:
- 改动 Deskflow 日志基础设施(`src/lib/base/Log.cpp` 的默认 outputter),违反"不深入内部逻辑"约束
- Deskflow 大量代码用 `LOG_PRINT` 等宏直接走默认 outputter,改默认行为可能引发未知副作用
- 上游 rebase 冲突面大
- 比 Option A 的"只加新模块"成本高

### Favored option:**Option A**

---

## Implementation steps

### 阶段 0:仓库初始化(无 C++ 改动)

1. `git init` 在 `/Users/ndq/Documents/trae/mouser` — 建立仓库
2. 创建 `.gitignore`(忽略 `build/`、`dist/`、`vendor/deskflow/`、`__pycache__`、`.venv/`、`*.spec.user`)
3. 创建 `requirements-build.txt`(`pyside6==6.7.3`、`pyinstaller==6.11.1`)
4. 创建 `requirements-dev.txt`(加 `pytest`、`ruff`)
5. Fork Deskflow:在 `vendor/deskflow/` 下 `git subtree add` 或 submodule(`git submodule add https://github.com/deskflow/deskflow.git vendor/deskflow`)+ checkout `v1.26.0` tag

### 阶段 1:C++ core 裁剪

6. 编辑 `vendor/deskflow/CMakeLists.txt`:
   - 删除 `REQUIRED_LIBEI_VERSION` / `REQUIRED_LIBPORTAL_VERSION` 常量(line ~50)
   - 删除 `if(UNIX AND NOT APPLE)` 块中 libei/libportal/xkbcommon `find_package` / `pkg_check_modules`(line ~80-120)
   - 删除 `BUILD_X11_SUPPORT` option(默认 OFF 即可,但显式删除更干净)
7. 编辑 `vendor/deskflow/src/lib/platform/CMakeLists.txt`:
   - 删除 `if(UNIX AND NOT APPLE)` 整块(libei/libportal/X11 sources)
   - 删除 `if(BUILD_X11_SUPPORT)` 块
   - 删除 `if(LIBEI_FOUND)` / `if(LIBPORTAL_FOUND)` 嵌套块
   - 删除 `target_compile_definitions(platform PUBLIC WINAPI_LIBEI WINAPI_LIBPORTAL ...)`
8. 删除文件(直接 `rm`,CMake 不再引用):
   - `vendor/deskflow/src/lib/platform/XWindows*` (15 个文件)
   - `vendor/deskflow/src/lib/platform/Ei*` (8 个文件)
   - `vendor/deskflow/src/lib/platform/Portal*` (3 个文件)
   - `vendor/deskflow/src/lib/platform/XDG*` (3 个文件)
   - `vendor/deskflow/src/lib/platform/XWindowsConfig.h.in`
9. 编辑 `vendor/deskflow/cmake/Libraries.cmake`:
   - 删除 `configure_xorg_libs()` macro 定义与调用
   - 删除所有 `HAVE_X11_*` / `HAVE_Xtst` / `HAVE_Xext` / `HAVE_Xinerama` / `HAVE_Xrandr` / `HAVE_Xi` / `HAVE_ICE` / `HAVE_SM` check
10. 编辑 `vendor/deskflow/deploy/CMakeLists.txt`:
    - 删除 `add_subdirectory(linux)` 行
11. `rm -rf vendor/deskflow/deploy/linux/`
12. **保留** `vendor/deskflow/src/lib/arch/unix/`(macOS 共享,不能删)
13. **保留** `vendor/deskflow/src/lib/deskflow/ipc/CoreIpcServer.*`(Option A 不动它)

### 阶段 2:C++ core NDJSON IPC 模块(Option A)

14. 新增 `vendor/deskflow/src/apps/deskflow-core/IpcMessages.h`:
    - 定义 `enum class IpcMessageType { Hello, Start, Stop, Status, Error, ClipboardUpdate, Ping, Pong }`
    - 定义 `struct IpcMessage { IpcMessageType type; QVariantMap payload; }`
    - 提供 `QByteArray serialize(const IpcMessage&)` 与 `std::optional<IpcMessage> deserialize(const QByteArray&)`(用 `QJsonDocument`)
15. 新增 `vendor/deskflow/src/apps/deskflow-core/IpcChannel.h` / `.cpp`:
    - 类 `IpcChannel : public QObject`,`Q_OBJECT`
    - 信号:`messageReceived(IpcMessage)`
    - 槽:`sendMessage(IpcMessage)`
    - 实现:`QSocketNotifier` 监听 `fileno(stderr)` 读;写用 `fprintf(stderr, "%s\n", json)` + `fflush(stderr)`
    - 用 `QTextStream(stderr)` 行缓冲模式
    - 启动时自动发 `Hello` 消息
16. 修改 `vendor/deskflow/src/apps/deskflow-core/deskflow-core.cpp`:
    - `#include "IpcChannel.h"`
    - `main()` 中在 `CoreApp` 创建后、`exec()` 前注入 `IpcChannel channel(&app)`
    - 连接 `IpcChannel::messageReceived` 到 lambda 处理 `Start`/`Stop`/`Ping`
    - 处理 `Stop` → 调 `QCoreApplication::quit()`
17. 修改 `vendor/deskflow/src/apps/deskflow-core/CMakeLists.txt`:
    - `target_sources(deskflow-core PRIVATE IpcChannel.h IpcChannel.cpp IpcMessages.h)`

### 阶段 3:本地构建验证 C++ 改动

18. macOS:`cmake -S vendor/deskflow -B build/deskflow -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=$(brew --prefix qt)` + `cmake --build build/deskflow`
19. 验证产物 `build/deskflow/src/apps/deskflow-core/deskflow-core` 存在且可执行
20. 手动测试:`./deskflow-core --help` → stdout 显示帮助(证明日志仍走 stdout)
21. 手动测试:`echo '{"type":"Ping"}' | ./deskflow-core --client` → stderr 应输出 `{"type":"Hello",...}` 然后 `{"type":"Pong",...}`(证明 IPC 通)

### 阶段 4:Python GUI 骨架

22. 新增 `gui/__init__.py`
23. 新增 `gui/ipc.py`:
    - `class IpcMessage(TypedDict)` 定义消息类型
    - `class DaemonIpc`:`subprocess.Popen` 封装,`send_msg()` 写 stdin,`read_msgs()` generator 读 stderr
    - `bundled_binary(name)` 函数:用 `getattr(sys, '_MEIPASS', None)` 解析 binary 路径,macOS 上 `chmod +x` 防御
    - `spawn_deskflow(mode, config)`:Windows 加 `CREATE_NO_WINDOW`,`text=True` UTF-8,`bufsize=1`
24. 新增 `gui/config.py`:
    - `@dataclass class ScreenConfig`:`host: str`、`position: Literal["left","right","top","bottom"]`
    - `@dataclass class MouserConfig`:`mode: Literal["server","client"]`、`port: int = 24800`、`screens: list[ScreenConfig]`、`local_host: str`
    - `load_config()` / `save_config()` 读写 `~/.config/mouser/config.json`(macOS `~/Library/Application Support/mouser/config.json`,Windows `%APPDATA%/mouser/config.json`,用 `platformdirs` 库)
    - JSON 格式(决策:JSON 比 TOML 易与 Deskflow 现有 JSON 用法一致)
25. 新增 `gui/daemon.py`:
    - `class DaemonManager(QObject)`:`Q_OBJECT`
    - 信号:`statusChanged(str)`、`errorOccurred(str)`
    - 槽:`start()`、`stop()`、`restart()`、`switchMode(str)`
    - 内部:持有 `DaemonIpc`,启动 `QTimer` 5s 发 `Ping`,3 次未收到 `Pong` 判挂起
    - 监听 `IpcMessage` 类型为 `Status`/`Error`/`ClipboardUpdate` 时 emit 信号
26. 新增 `gui/tray.py`:
    - `class TrayController(QObject)`:`Q_OBJECT`
    - 信号:`startRequested()`、`stopRequested()`、`switchModeRequested(str)`、`quitRequested()`
    - 用 `QSystemTrayIcon` + `QMenu`,3 个图标资源(`resources/icon-idle.png`、`icon-active.png`、`icon-error.png`)
    - tooltip 显示最近 status / error
27. 新增 `gui/main.py`:
    - `QApplication` 初始化,`QSystemTrayIcon` 可用性检查
    - macOS Accessibility 权限检查(用 `pyobjc` `ApplicationServices.APIEnabled()` 或调用 `osascript`)
    - 未授权时弹 `QMessageBox` 引导到 系统设置 > 隐私与安全 > 辅助功能
    - 装配 `DaemonManager` + `TrayController`,连接信号槽
    - 不显示主窗口,v1 仅托盘模式
28. 新增 `gui/resources/`:3 个托盘图标(可用简单 PNG,16x16 / 32x32 / 64x64 三档)

### 阶段 5:IPC 消息 schema(共享)

29. 新增 `ipc-protocol/messages.json`:
    ```json
    {
      "version": "1.0",
      "messages": {
        "Hello": {"fields": {"version": "string", "pid": "int"}},
        "Start": {"fields": {"mode": "server|client", "config": "object"}},
        "Stop": {"fields": {}},
        "Status": {"fields": {"state": "connected|disconnected|connecting", "detail": "string"}},
        "Error": {"fields": {"code": "string", "message": "string"}},
        "ClipboardUpdate": {"fields": {"text": "string"}},
        "Ping": {"fields": {}},
        "Pong": {"fields": {}}
      }
    }
    ```
30. 文档:`ipc-protocol/README.md` 描述协议、版本兼容规则

### 阶段 6:PyInstaller 打包

31. 新增 `packaging/mouser.spec`(macOS):
    - `binaries=[(os.path.join(ROOT, 'vendor/deskflow/bin/deskflow-core'), 'bin')]`
    - `datas=[('gui/resources', 'resources'), ('ipc-protocol/messages.json', 'ipc-protocol')]`
    - `excludes=[...]`(参考研究子任务的完整 excludes 列表,排除 QtWebEngine/QtQuick/Qt3D 等)
    - `BUNDLE(name='Mouser.app', icon='packaging/icons/mouser.icns', bundle_identifier='com.ndq.mouser')`
32. 新增 `packaging/mouser-win.spec`(Windows):
    - 同上但 binary 名带 `.exe`,无 `BUNDLE`,只 `COLLECT` 生成 onedir
33. 新增 `packaging/icons/mouser.icns` 和 `mouser.ico`(从图标资源生成)
34. 新增 `packaging/build.sh` / `packaging/build.ps1`:
    - 先 `cmake --build` C++ core 到 `vendor/deskflow/bin/`
    - 再 `pyinstaller --noconfirm --clean packaging/mouser.spec`

### 阶段 7:GitHub Actions CI

35. 新增 `.github/workflows/build-macos.yml`:
    - matrix:`macos-14`(arm64)、`macos-13`(x86_64)
    - 步骤:checkout submodules → setup Python 3.12 → brew install qt cmake ninja ccache → cmake build C++ → pip install → pyinstaller → codesign `--force --deep --sign -` → hdiutil create DMG → upload-artifact
36. 新增 `.github/workflows/build-windows.yml`:
    - matrix:`windows-2022`
    - 步骤:checkout → setup Python → install Qt 6.7(via `jurplel/install-qt-action` v4)→ setup MSVC → cmake build → pip install → pyinstaller → Compress-Archive → upload-artifact
37. 新增 `.github/workflows/test.yml`:
    - Python lint(`ruff check gui/`)、单元测试(`pytest tests/`)

### 阶段 8:测试与验收

38. 新增 `tests/test_ipc.py`:用 mock subprocess 测 `DaemonIpc.send_msg` / `read_msgs` 解析
39. 新增 `tests/test_config.py`:测 `MouserConfig` 序列化/反序列化、跨平台路径
40. 手动验收 AC-1 ~ AC-13(见 Verification steps)

### 阶段 9:文档

41. 新增 `README.md`:简介、安装、macOS `xattr -dr com.apple.quarantine Mouser.app` 提示、Accessibility 引导
42. 新增 `docs/BUILD.md`:本地构建步骤(mac + win)

---

## Workspace setup

- Working directory `/Users/ndq/Documents/trae/mouser` 当前为空(greenfield)
- Run `git init` 作为步骤 1
- 当前无 main / master 分支,无需 worktree
- 后续若需在 fork 上做实验性改动,可 `git worktree add -b codex/experiment ../mouser-experiment`

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Deskflow v1.26.0 在最新 macOS 26 上构建失败 | 锁 v1.26.0 tag;若失败,回退到最近能编译的 tag,记录在 ADR |
| `deskflow-core` 启动时 stderr 与 stdout 行为不一致(Windows 缓冲) | IpcChannel.cpp 显式 `setvbuf(stderr, nullptr, _IONBF, 0)` + 每次 `sendMessage` 后 `fflush(stderr)` |
| Apple Silicon 上未签名 binary `Killed: 9` | CI 强制 `codesign --force --deep --sign -` ad-hoc 签名;AC-11 验证 |
| PySide6 + C++ binary 打包后体积 > 150MB | 用研究子任务的 excludes 列表;目标 ≤ 100MB;若超出移除 QtSvg/QtNetwork(若 GUI 不用 SSL) |
| `deskflow-core --server` 需要 Accessibility 权限,首次启动失败 | GUI 启动时主动检查并引导用户授权,AC-6 验证 |
| macOS Sequoia Local Network 权限弹窗 | 文档化提示;若 daemon 连接失败,GUI 弹引导到 系统设置 > 隐私与安全 > 本地网络 |
| Deskflow 上游 master 大改导致 fork 难 rebase | v1 锁 tag;所有改动集中在 `src/apps/deskflow-core/IpcChannel.*` 与 CMake 裁剪,rebase 时手动 cherry-pick |
| PyInstaller 6+ `_internal/` 布局变化导致 `bundled_binary` 找不到 | 用 `getattr(sys, '_MEIPASS')` 而非硬编码路径,跨布局自适应 |
| Windows Defender 误报 PyInstaller 产物 | 文档化;后续考虑 EV 代码签名证书(v2) |
| `subprocess.Popen` 在 GUI 退出时孤儿进程 | `DaemonManager.stop()` 在 `QApplication.aboutToQuit` 时强制 `terminate()` + `kill()` |
| stderr 仍可能被 Deskflow 其他代码污染(若有 `fprintf(stderr, ...)` 直写) | 阶段 3 步骤 21 手动测试验证;若污染,在 IpcChannel 启动时重定向 stderr 文件描述符到独立 pipe |
| 用户在同一台机器上既想当 server 又想当 client(自测场景) | v1 不支持同进程多模式;文档建议用两台机器或 VM |

---

## Verification steps

- **AC-1**(Mac server → Win client 鼠标跨屏):在两台机器部署 DMG/zip,启动 GUI 选 server 模式(Mac)/ client 模式(Win),Mac 屏右滑 → Win 屏出现,键盘输入 → 焦点跟随。截图前后对比。
- **AC-2**(Win server → Mac client):反向同上。
- **AC-3**(剪贴板纯文本):Mac 上 Cmd+C 复制 "hello mouser" → Win 上 Cmd+V → 文本一致;反向亦然。Rich text 不在 v1 范围。
- **AC-4**(托盘图标状态):server+client 连接成功时托盘绿;关一端 5s 内托盘变灰;`kill -9` daemon 5s 内托盘变红带 tooltip。
- **AC-5**(模式切换):GUI 菜单点 "Switch to client" → 旧进程退出 → 新进程以 `--client` 启动 → 托盘状态 3s 内更新(用秒表或日志时间戳)。
- **AC-6**(Accessibility 引导):在未授权 Mac 上 `tccutil reset Accessibility com.ndq.mouser` 后启动 → GUI 弹出 QMessageBox 含 "系统设置 > 隐私与安全 > 辅助功能" 文案。
- **AC-7**(TLS 加密):Wireshark 抓 24800 端口 TCP 流量 → 跟随 TCP Stream → 内容为乱码(TLS),非明文 "hello"。
- **AC-8**(干净机器运行):把 DMG 拷到未装 Python/Qt 的 Mac → 拖到 Applications → 双击 → 启动;Windows 同理(zip 解压后双击 Mouser.exe)。Windows 上若缺 VC++ Redistributable,文档提示安装。
- **AC-9**(daemon crash 检测):运行中 `pkill -9 deskflow-core` → GUI 在 ≤ 5s 内托盘变红 + 弹"重启 daemon"按钮。
- **AC-10**(GUI 跨平台一致):`git diff gui/main.py` 在 mac 和 win 构建产物中无 #ifdef 平台分支,仅 `gui/resources/` 图标差异。
- **AC-11**(ad-hoc 签名):`codesign --verify --verbose=4 dist/Mouser.app` 退出码 0;启动 GUI 后 `subprocess.Popen` 启动 `deskflow-core` 不返回 `Killed: 9`。
- **AC-12**(NDJSON HELLO):`echo '' | ./deskflow-core --client 2>ipc.log`;`head -1 ipc.log` 是合法 JSON,`jq .type ipc.log` 返回 `"Hello"`。
- **AC-13**(CI 三平台产物):GitHub Actions 三次 run 各产出 artifact(`Mouser-macos-arm64.dmg`、`Mouser-macos-x86_64.dmg`、`Mouser-windows-x86_64.zip`),均可下载且非空。

---

## ADR

- **Decision**: Fork Deskflow v1.26.0,裁剪 Linux/BSD/X11/Wayland/libei/libportal,保留 macOS+Windows 平台模块与 C++ core,新增独立 NDJSON-over-stderr IPC 模块(Option A),用 PySide6 重写 GUI,PyInstaller `binaries=` 嵌入 deskflow-core,GitHub Actions 三平台矩阵构建。
- **Drivers**(决定性):
  1. C++ 维护成本(user Python 主栈)→ 选最小 C++ 改动方案
  2. macOS Apple Silicon 签名硬约束 → 必须加 codesign 步骤
  3. 跨平台一致性 → NDJSON over stderr 跨 Mac/Win 行为一致
  4. 上游 rebase 可行性 → 改动集中在 IpcChannel 新模块,CMake 裁剪可 cherry-pick
- **Alternatives considered**:
  - Option A(NDJSON over stderr)**: chosen** — 最小 C++ 改动,日志与 IPC 解耦,可 CLI 调试
  - Option B(复用 CoreIpcServer + Python QLocalSocket)**: rejected** — Python 端需 Qt 事件循环深度耦合,CoreIpcServer 协议非公开 NDJSON,跨平台一致性差,无法 CLI 调试,且 macOS 上 CoreIpcServer 默认监听行为未验证
  - Option C(NDJSON over stdout + 重定向日志)**: rejected** — 改动 Deskflow `Log.cpp` 默认 outputter,违反"不深入内部逻辑"原则,rebase 冲突面大
- **Why chosen**: Option A 在"最小 C++ 改动 / 跨平台一致 / 可调试 / rebase 友好"四个维度同时占优,tradeoff 仅是多一个 IPC 通道(CoreIpcServer 保留不用),v1 可接受。
- **Consequences**:
  - 正面:C++ 改动 ≤ 4 个新文件 + 2 处 CMake 修改;GUI 完全在 Python 栈;CLI 可独立测 daemon;CI 路径清晰
  - 负面:多一个未用通道(CoreIpcServer),后续若想统一需 v2 迁移;stderr 缓冲行为需显式 `setvbuf`/`fflush`;8 处 spec drift 需回写 spec
  - 跨模块影响:无(新模块独立)
  - 性能:NDJSON 序列化用 QJsonDocument,消息频率 < 10 Hz,无性能瓶颈
  - 维护:C++ 部分仅 IpcChannel 一个模块,user Python 栈可完全掌控 GUI/IPC/打包/CI
- **Follow-ups**(本次不做,进 backlog):
  - 回写 8 处 spec drift 到 `.claude/artifacts/designs/mouser.md`
  - v2:统一 CoreIpcServer 与新 NDJSON 通道(或废弃 CoreIpcServer)
  - v2:macOS Developer ID 签名 + notarization
  - v2:Windows EV 代码签名
  - v2:`deskflow-core` 改名 `mouser-core`
  - v2:多屏网格布局(非仅 left/right/top/bottom)
  - v2:GUI 内嵌"测试连接"按钮
  - 长期:定期 rebase Deskflow 上游(每季度)

---

## Review trail

### Iteration 1

- **Planner draft v1**: 提出 3 个 option(A: NDJSON over stderr / B: 复用 CoreIpcServer / C: NDJSON over stdout 重定向日志),favored A。C++ 改动限于 IpcChannel 新模块 + CMake 裁剪。
- **Architect challenge v1**: Steelman Option B — "C++ 零改动完美契合最小代码原则,且复用上游稳定实现"。Tradeoff tension: "最小 C++ 改动" vs "Python 端 Qt 事件循环耦合度" —— 若 Python GUI 已用 PySide6 则耦合不是问题,但失去 CLI 调试能力是真实损失。Synthesis: 不融合,因 A/B 在调试性上本质冲突。
- **Critic verdict v1**: REJECT
  - 拒收原因:
    1. Option B 的 "macOS 上 CoreIpcServer 默认监听行为未验证" 是未消除假设(baseline "不假设"违反)
    2. AC-12 缺失 —— 没有 AC 验证 NDJSON 通道本身可用
    3. AC-13 缺失 —— 没有 AC 验证 CI 三平台产物
    4. 风险表中缺 "stderr 被 Deskflow 其他代码污染" 风险
    5. 实施步骤未 cite deskflow-core.cpp 具体行号(虽是外部仓库,但应给出函数名锚点)
- **修复**:补 AC-11/12/13,补 stderr 污染风险,补 deskflow-core.cpp 改动锚点("在 `main()` 中 `CoreApp` 创建后注入"),补 Option B 未验证假设的明确标注。

### Iteration 2

- **Planner draft v2**: 修复 v1 全部 5 项问题。新增 3 条 AC,补 1 条风险,补 C++ 改动锚点。Option B 显式标 "macOS CoreIpcServer 监听行为未验证" 作为 reject 理由之一(而非隐藏)。
- **Architect challenge v2**: 无新 tension。确认 stderr 缓冲风险已在 mitigation 中覆盖(`setvbuf` + `fflush`)。
- **Critic verdict v2**: APPROVED with reservations

### Final iterations: 2 / 3

---

## Critic verdict (final)

| 维度 | 状态 | 备注 |
|---|---|---|
| Principle consistency | ✓ | Option A 与"最小代码""不深入内部逻辑"原则一致 |
| Alternative exploration | ✓ | A/B/C 三 option 真候选,C 被否有显式 rationale |
| Risk mitigation clarity | ✓ | 12 条 risk 均有具体 mitigation(命令/步骤) |
| AC testability | ✓ | 13 条 AC 均二值可验证,有具体命令 |
| Verification concreteness | ✓ | 每条 AC 有命令/步骤/截图/抓包等可执行验证 |
| File/line coverage | ✓ | 42 个实施步骤中 ≥ 85% cite 具体文件路径(Deskflow 内部文件因是外部 submodule,以函数名/类名锚点替代行号) |

### Verdict: **APPROVED**

### Reservations(必填)

1. **Option B 的 "macOS CoreIpcServer 默认监听行为未验证" 仍是 plan-level 假设** —— 虽 Option B 已 rejected,但若 Option A 在实施阶段发现 `deskflow-core` 的 stderr 被某全局 Qt 日志 hook 拦截,需 fallback 到 Option B 或 Option C,届时该假设必须先验证。建议阶段 3 步骤 21 优先验证此项。

2. **阶段 1 步骤 6-11 的 CMake 裁剪无单元测试覆盖** —— 裁剪后能否编译靠阶段 3 手动 cmake build 验证。若裁剪过度(误删 macOS 依赖)或不足(残留 Linux 引用),失败模式是编译错误而非测试红。Mitigation 是阶段 3 强制本地构建,但无自动化回归。建议 v2 加 CI 上的"C++ 裁剪烟雾测试"job。

3. **`deskflow-core` 在 macOS 上的 Accessibility 权限模型未在 plan 内验证** —— spec AC-6 假设 GUI 能弹引导,但 `deskflow-core` 作为 subprocess 启动时,权限是继承 GUI 进程还是需独立授予未验证。若需独立授予,GUI 弹窗引导文案需调整(指向 `deskflow-core` 而非 `Mouser.app`)。建议阶段 4 步骤 27 实施时优先验证此项。

4. **打包体积估算 ~100MB 是基于研究子任务的理论值** —— 实际 PyInstaller + PySide6 + deskflow-core(可能 20-40MB)可能超 120MB。Plan 未设体积上限 AC。若分发渠道(GitHub Release)有 200MB 单文件限制,当前安全;若用户期望 ≤ 50MB 需 v2 优化。

---

## Open questions(留给 dev-tdd 阶段)

- IpcChannel.cpp 是否需要支持消息分片(>64KB 的 ClipboardUpdate)?NDJSON 单行通常 < 64KB,但大文本剪贴板可能超 —— 倾向不分片,超长截断 + 日志
- Config 文件迁移:若用户从旧版本升级,config schema 变化如何处理?v1 不考虑(首次发布),v2 加 `version` 字段
- `deskflow-core` 的 `--server` / `--client` 参数确切名称需在阶段 3 步骤 20 `--help` 输出后确认(研究子任务未抓 help 输出)
- Windows 上 `deskflow-core` 是否需要 `deskflow-daemon` 配合?v1 假设不需要(直接 spawn),但 Deskflow Windows 设计可能依赖 daemon 做服务化 —— 需阶段 3 Windows 构建后验证
