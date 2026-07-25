# mouser Spec

> Status: ALIGNED
> Author: ndq
> Last updated: 2026-07-25

## Background

跨平台键鼠共享软件 mouser,基于 Deskflow(v1.26.0+)fork,目标平台 macOS + Windows。

复用 Deskflow 成熟的 C++ core(输入捕获/注入 + 网络协议 + TLS + 剪贴板),裁剪 Linux/BSD/Wayland/libei/libportal 模块以减少依赖与构建复杂度。GUI 用 PySide6 重写,通过 subprocess + JSON IPC 控制 C++ core 子进程。最终用 PyInstaller 打包为 .app / .exe 分发。

## In scope (v1)

- Fork Deskflow master(v1.26.0+ tag)
- 裁剪:
  - 移除 `src/lib/platform/` 下 Linux/BSD/X11/Wayland 相关平台模块
  - 移除 libei / libportal 依赖与对应 CMake 条件编译开关
  - 移除 `deploy/` 下 Linux/BSD 打包脚本
- 保留 C++ core:
  - macOS 平台模块(CGEvent / Quartz Event Services,Accessibility-based 输入捕获/注入)
  - Windows 平台模块(SendInput + 低级 keyboard hook)
  - 网络协议(TCP + TLS,与 Synergy 1 / Barrier / Input Leap 兼容)
  - 剪贴板同步(纯文本)
  - 单一 `deskflow-core` binary(`--server` / `--client` 参数切换模式,不沿用 `mouserd`/`mouserc` 双 binary 设计)
  - **不集成** `deskflow-daemon`(Windows-only 服务管理器,v1 直接 spawn `deskflow-core`)
- Python GUI(PySide6):
  - 系统托盘图标(连接状态可视化)
  - Server / Client 模式切换
  - 启动 / 停止 daemon 子进程
  - 配置编辑(屏幕布局、对端 host、端口)
  - 状态显示(连接 / 错误 / 日志摘要)
  - macOS Accessibility 权限引导
- 集成层:
  - Python GUI 通过 `subprocess.Popen` 启动 `deskflow-core` binary
  - NDJSON over **stderr**(每行一条 JSON;stdin 接收控制命令)
  - **不使用 stdout**(Deskflow 默认 `ConsoleLogOutputter` 占用 stdout 输出日志;见 D3)
  - 消息类型:`HELLO` / `START` / `STOP` / `STATUS` / `ERROR` / `CLIPBOARD_UPDATE` / `PING` / `PONG`
  - **不修改** Deskflow 现有 `CoreIpcServer`(`src/lib/deskflow/ipc/`,Qt QLocalSocket)—— v1 新增独立 IPC 通道
- 打包:
  - PyInstaller 打包 Python GUI + 嵌入 C++ binary 作为 **`binaries=`**(保留 exec bit,非 `datas=`)
  - macOS `.app` bundle + **ad-hoc 签名**(`codesign --force --deep --sign -`,Apple Silicon 未签名会被 `Killed: 9`)
  - macOS **双架构分发**:`macos-14`(arm64)与 `macos-13`(x86_64)各一份 DMG(PyInstaller 不支持 universal2)
  - Windows `onedir` 模式 + zip portable 包
  - GitHub Actions 三平台矩阵构建(`macos-14` / `macos-13` / `windows-2022`)

## Out of scope (v1)

- Linux / BSD / Wayland / X11 支持
- 文件拖拽传输
- 移动端 client(Android / iOS)
- 自定义快捷键手势 / 类似 Universal Control 的连续手势
- GUI 内拖拽式屏幕布局编辑器(v1 用文本/简单下拉配置)
- 多语言 i18n(v1 仅英文)
- macOS **Developer ID 签名与 notarization**(v1 仅 ad-hoc 签名,文档化 `xattr -dr com.apple.quarantine` 步骤)
- Windows **EV 代码签名**(v1 未签名,文档化 SmartScreen 提示)
- Wayland / libei / libportal 任何相关代码
- 与 Synergy 3 / Lan Mouse 协议互操作(仅兼容 Synergy 1 / Barrier / Input Leap / Deskflow)
- 远程网络(跨 Internet)场景(仅 LAN)

## Assumptions

- Deskflow v1.26.0+ master 分支稳定,网络协议与 Barrier / Synergy 1 兼容
- 用户已安装 macOS 13+(Apple Silicon)或 macOS 12+(Intel);Windows 10 v1809+
- 用户具有管理员权限安装 / 授予 Accessibility
- 两台设备在同一局域网,默认端口 24800 不被占用(占用时 GUI 提示换端口)
- Python 3.10+ 可用
- 构建机已装 Xcode + CMake(macOS)/ Visual Studio 2022 + CMake(Windows)
- PyInstaller ≥ 6.0 支持 PySide6 打包

## Solution sketch

### 代码组织

```
mouser/
├── vendor/deskflow/            # C++ Deskflow v1.26.0 submodule(裁剪后)
│   ├── src/
│   │   ├── lib/platform/       # 只保留 macOS + Windows 子目录(删 X11/Ei/Portal/XDG)
│   │   ├── lib/arch/unix/      # **保留**(macOS 共享,不能删)
│   │   ├── lib/deskflow/ipc/   # **保留不动**(CoreIpcServer,v1 不用)
│   │   └── apps/deskflow-core/ # 新增 IpcChannel 模块在此(不污染 arch 层)
│   ├── CMakeLists.txt          # 裁剪后
│   └── ...
├── gui/                        # PySide6 GUI
│   ├── main.py
│   ├── tray.py
│   ├── config.py
│   ├── ipc.py
│   └── resources/
├── ipc-protocol/               # JSON 消息 schema(共享)
│   └── messages.json
├── packaging/
│   ├── mouser.spec             # PyInstaller spec(macOS)
│   ├── mouser-win.spec         # PyInstaller spec(Windows)
│   └── icons/
├── docs/
│   └── adr/
└── .github/workflows/
    ├── build-macos.yml
    └── build-windows.yml
```

### C++ core 改动

1. 在 `src/apps/deskflow-core/` 新增 `IpcChannel` 类 + `IpcMessages.h`(NDJSON over **stderr**,不放在 `src/lib/arch/` 污染 arch 层)
2. `deskflow-core` 启动时经 stderr 发 `HELLO` 握手,运行时持续输出 `STATUS` / `ERROR` / `PONG`
3. 经 stdin 接收 `START` / `STOP` / `PING` 控制命令
4. 删除 `src/lib/platform/` 下 X11/Ei/Portal/XDG 子目录(**不删** `src/lib/arch/unix/`,macOS 共享)
5. 删除 `libei` / `libportal` / `xkbcommon` / X11 依赖与 CMake 条件编译开关(`BUILD_X11_SUPPORT` / `WINAPI_LIBEI` / `WINAPI_LIBPORTAL` / `WINAPI_XWINDOWS` 等;Deskflow master 已清理 `glib2` / `gtk3`)
6. **保留** `deskflow-core` binary 名(v1 不改名 `mouserd`,避免 CI/文档连锁修改)
7. **保留** `src/lib/deskflow/ipc/CoreIpcServer.*`(v1 不动,Option A 独立通道并行存在)

### Python GUI 流程

1. 启动 → 读配置文件 → spawn `deskflow-core` subprocess
2. stdin 发 `START`,**stderr** 监听 `STATUS` / `ERROR` → 更新托盘(stdout 留给 Deskflow 日志,可选 tail 用于诊断)
3. 用户切换模式 → 发 `STOP` → 等待退出 → spawn 新模式进程(`--server` ↔ `--client`)
4. daemon 异常退出 → `ERROR` 消息 → GUI 提示 + 提供"重启"按钮
5. 心跳:GUI 每 5s 发 `PING`,daemon 回 `PONG`,3 次未响应判定为挂起
6. Windows 上 `subprocess.Popen` 加 `CREATE_NO_WINDOW` 抑制控制台窗口

### 打包流程

1. GitHub Actions runner 上先 cmake build C++ core → 产出 `deskflow-core` binary
2. PyInstaller 把 binary 作为 **`binaries=`** 打入 Python 包(保留 exec bit,非 `datas=`)
3. 运行时用 `getattr(sys, '_MEIPASS')` 解析 binary 路径,macOS 上防御性 `chmod +x`
4. macOS: 生成 `.app` bundle + **ad-hoc 签名** `codesign --force --deep --sign -`(Apple Silicon 必需)
5. macOS: 用户首次启动需 `xattr -dr com.apple.quarantine Mouser.app`(未 notarize,文档化)
6. Windows: 生成 `onedir` 文件夹 + zip portable
7. **不尝试 universal2**:arm64 与 x86_64 分别在 `macos-14` / `macos-13` runner 上独立构建,产出两份 DMG

## Edge cases & risks

| Category | Notes |
|---|---|
| Boundary conditions | 网络断开时按键未释放 → daemon 自带 keepalive,超时释放所有键(Deskflow 现有逻辑保留) |
| Boundary conditions | 屏幕分辨率 / DPI 不一致 → Deskflow 已处理,保留逻辑 |
| Boundary conditions | 多屏布局复杂(4 屏网格) → v1 只支持线性布局(left / right / top / bottom) |
| Boundary conditions | 剪贴板含图片 / 富文本 → v1 仅同步纯文本,其他类型丢弃并日志记录 |
| Failure modes | macOS Accessibility 未授权 → daemon 启动失败,GUI 弹引导到 系统设置 > 隐私与安全 > 辅助功能 |
| Failure modes | macOS Sequoia Local Network 权限未开 → daemon 连接失败,GUI 弹引导 |
| Failure modes | Windows SmartScreen 拦截未签名 exe → 文档化,后续考虑签名 |
| Failure modes | 端口 24800 冲突 → GUI 检测并提示换端口 |
| Failure modes | daemon crash → GUI 5s 内检测,托盘变红,提供"重启 daemon" |
| Risks | Apple Silicon 未签名 binary `Killed: 9` → CI 强制 `codesign --force --deep --sign -` ad-hoc 签名(AC-11 验证) |
| Risks | C++ 编译环境复杂,CI 构建慢 → 用 ccache + actions cache |
| Risks | Deskflow 上游大改导致 fork 难合并 → v1 锁定 v1.26.0 tag,定期 rebase |
| Risks | PyInstaller + PySide6 包体积大(~80-100MB) → 排除 Qt WebEngine / Qt Quick / Qt3D 等不必要模块 |
| Risks | macOS Apple Silicon / Intel 双架构 → PyInstaller 不支持 universal2,分别 `macos-14`(arm64)+ `macos-13`(x86_64)各一份 DMG |
| Risks | `deskflow-core` stderr 被 Deskflow 其他代码污染 → IpcChannel 启动时显式 `setvbuf` + 每次 `sendMessage` 后 `fflush` |
| Risks | C++ 维护成本与 user Python 主栈不匹配 → 限定只改 IPC 层,不深入 Deskflow 内部逻辑 |
| Mitigation | 每个风险都有降级方案(文档化手动步骤或 fallback 行为) |

## Acceptance criteria

- AC-1 在 macOS(server) 与 Windows(client) 上分别部署 mouser → 鼠标从 macOS 屏幕右边缘滑出 → 在 Windows 屏幕左边缘出现 → 键盘输入焦点跟随鼠标 → 关闭 GUI → 鼠标回到 macOS
- AC-2 反向:Windows(server) → macOS(client) 同样工作
- AC-3 在 macOS 上复制文本 → 在 Windows 上 Cmd+V 粘贴出同样文本;反向亦然(纯文本)
- AC-4 GUI 系统托盘图标在连接成功时显示绿色,断开时显示灰色,错误时显示红色带 tooltip 错误摘要
- AC-5 从 GUI 切换 server ↔ client 模式 → 旧进程退出 → 新进程以新模式启动 → 3 秒内状态更新
- AC-6 在未授予 Accessibility 权限的 macOS 上启动 → GUI 弹出引导,指引到 系统设置 > 隐私与安全 > 辅助功能 开启
- AC-7 网络抓包(Wireshark)确认 client ↔ server 之间流量为 TLS 加密(非明文)
- AC-8 PyInstaller 打包后产物在干净 macOS 13+ 与 Windows 10 v1809+ 上可双击运行,无需用户额外装 Python / Qt(Windows 上 VC++ Redistributable 仍需,文档化)
- AC-9 `kill -9` daemon 进程 → GUI 在 5 秒内检测并更新托盘为"已断开",提供"重启 daemon"按钮
- AC-10 同一份 GUI 代码在 macOS 和 Windows 上都能跑(无平台硬编码),仅有托盘图标资源差异
- AC-11 打包后的 macOS `.app` 通过 `codesign --verify` ad-hoc 签名校验,Apple Silicon 上 `deskflow-core` 子进程可正常启动(非 `Killed: 9`)
- AC-12 `deskflow-core` 启动后,GUI 经 stderr 收到首条 `HELLO` NDJSON 消息,`jq .type` 返回 `"Hello"`
- AC-13 GitHub Actions 在 `macos-14` / `macos-13` / `windows-2022` 三个 runner 上各产出可下载的非空产物

## Open questions

(无重大阻塞;以下为 dev-plan 阶段细化项)

- IPC 消息字段细节 → dev-plan 定义完整 JSON schema(**已交付**,见 `ipc-protocol/messages.json` 计划)
- 屏幕布局配置文件格式(JSON vs TOML)→ dev-plan 决定:**JSON**(与 Deskflow 现有 JSON 用法一致)
- 是否需要 GUI 内嵌"测试连接"按钮 → v2
- C++ binary 改名 → dev-plan 决定:**v1 保留 `deskflow-core`**(避免 CI/文档连锁修改),v2 再改名 `mouser-core`

## Core entities (ontology)

| Entity | Type | Key fields | Relationship |
|---|---|---|---|
| Mouser | Product | - | 包含 Core + GUI |
| Core | C++ binary | `deskflow-core`(`--server`/`--client`) | Forked from Deskflow v1.26.0, runs as subprocess |
| GUI | Python app | `main.py`, `tray.py` | PySide6, spawns Core |
| Daemon | Process | mode(`--server`/`--client`), host, port | Core 实例,server 或 client |
| IPC | Channel | stdin/stderr NDJSON | GUI ↔ Daemon 通信(stderr 输出消息,stdin 接命令) |
| Config | File | screens, mode, host, port | GUI 读写,Core 启动时读 |
| Screen | Layout node | position, host | 配置项 |
| TrayIcon | UI element | status | GUI 子组件 |

## Interview metadata

- Mode: default
- Waves: 5
- Final ambiguity: 12.15%
- Status: PASSED
- Spec drift applied: 2026-07-25(8 处,源自 dev-plan research 阶段;详见 `.claude/artifacts/plans/mouser.md` "Spec drift findings" 段)
  - D1: `mouserd`/`mouserc` 双 binary → 单一 `deskflow-core`(`--server`/`--client`)
  - D2: 未提及 Windows daemon → `deskflow-daemon` Windows-only,v1 不集成
  - D3: NDJSON over stdin/stdout → 改用 stderr(stdout 被 ConsoleLogOutputter 占用)
  - D4: 未提及现有 IPC → `CoreIpcServer` 保留不动,v1 新增独立通道
  - D5: `src/lib/arch/` 新增 IPC → 改在 `src/apps/deskflow-core/` 新增(不污染 arch 层)
  - D6: PyInstaller `datas=` → 改用 `binaries=`(保留 exec bit)
  - D7: 未签名 + `xattr -c` → ad-hoc 签名(`codesign --force --deep --sign -`,Apple Silicon 必需)
  - D8: universal2 或分发两份 → 强制两份(arm64 `macos-14` + x86_64 `macos-13`)

### Clarity breakdown

| Dimension | Score | Weight | Weighted |
|---|---|---|---|
| Goal | 0.95 | 0.43 | 0.4085 |
| Scope | 0.85 | 0.28 | 0.238 |
| AC | 0.80 | 0.29 | 0.232 |
| Total | | | 0.8785 |
| Ambiguity | | | 12.15% |

### Ontology convergence

- Wave 1: Project, Target=Mac+Win (3 entities)
- Wave 2: + Approach=fork Deskflow, Lang=C++ (5 entities)
- Wave 3: Lang→Core=C++ (renamed), + Removed=Linux/BSD/Wayland, + GUI=? (6 entities)
- Wave 4: + Integration=Subprocess+JSON IPC (7 entities)
- Wave 5: All 7 stable; expanded for spec writing (Daemon, IPC, Config, Screen, TrayIcon derived)
