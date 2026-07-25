# Mouser

跨平台键鼠共享软件,支持 macOS 与 Windows。一台键盘鼠标,控制多台电脑。

基于 [Deskflow](https://github.com/deskflow/deskflow) v1.26.0 的 C++ core,裁剪掉 Linux/X11/Wayland 部分,用 PySide6 重写 GUI,通过 NDJSON-over-stderr 子进程 IPC 通信,PyInstaller 打包。

## 特性

- **跨平台**:macOS (arm64 + x86_64) 与 Windows (x86_64)
- **TLS 加密**:网络传输默认 TLS,非明文
- **剪贴板同步**:纯文本跨机剪贴板
- **托盘 GUI**:状态图标 + 右键菜单,无主窗口
- **崩溃自愈**:daemon 无响应 5 秒内托盘变红 + 提示重启
- **可调试**:CLI 可直接运行 `deskflow-core`,NDJSON 走 stderr,日志走 stdout

## 下载安装

从 [Releases](../../releases) 下载对应平台产物:

| 平台 | 产物 | 架构 |
|---|---|---|
| macOS (Apple Silicon) | `Mouser-macos-arm64.dmg` | arm64 |
| macOS (Intel) | `Mouser-macos-x86_64.dmg` | x86_64 |
| Windows | `Mouser-windows-x86_64.zip` | x86_64 |

### macOS

1. 双击 DMG → 拖 `Mouser.app` 到 `Applications`
2. 首次启动若被 Gatekeeper 拦截,执行:
   ```bash
   xattr -dr com.apple.quarantine /Applications/Mouser.app
   ```
3. **Apple Silicon 必须**:已 ad-hoc 签名,无需额外操作
4. 首次启动会弹窗引导到 **系统设置 > 隐私与安全 > 辅助功能**,启用 `Mouser`

### Windows

1. 解压 zip 到任意目录
2. 双击 `Mouser.exe`
3. 若缺 VC++ Redistributable,从 [Microsoft 官网](https://aka.ms/vs/17/release/vc_redist.x64.exe) 安装

## 使用

1. 两台机器各部署一份 Mouser
2. 主控端(server)托盘菜单选 "Server mode"
3. 被控端(client)托盘菜单选 "Client mode"
4. 光标滑出屏幕边缘 → 自动跳到另一台机器,键盘焦点跟随

### 配置文件

配置路径由 `platformdirs` 决定:

- macOS: `~/Library/Application Support/mouser/config.json`
- Windows: `%APPDATA%\mouser\config.json`

字段:

```json
{
  "mode": "server",
  "port": 24800,
  "local_host": "",
  "screens": [
    {"host": "192.168.1.100", "position": "right"}
  ]
}
```

## 本地构建

详见 [docs/BUILD.md](docs/BUILD.md)。简要:

```bash
# macOS
brew install qt cmake ninja
pip install -r requirements-build.txt
./packaging/build.sh

# Windows
# 先安装 Qt 6.7 + VS 2022 Build Tools
pip install -r requirements-build.txt
.\packaging\build.ps1 -QtPath 'C:\Qt\6.7.3\msvc2022_64'
```

## 开发

```bash
pip install -r requirements-dev.txt
pytest                    # 单元测试 (53+ tests)
ruff check gui/ tests/    # lint
```

### 架构

```
┌─────────────┐  NDJSON/stderr  ┌──────────────────┐  TLS/TCP   ┌─────────────┐
│  Mouser GUI │ ←─────────────→ │  deskflow-core   │ ←────────→ │ deskflow-core│
│ (PySide6)   │   stdin/stderr  │  (subprocess)    │  port 24800│ (server/client)│
└─────────────┘                 └──────────────────┘            └─────────────┘
```

- `gui/`:Python GUI (PySide6),托盘 + 配置 + daemon 管理 + IPC
- `vendor/deskflow/`:Deskflow v1.26.0 submodule,裁剪到 macOS + Windows
- `vendor/deskflow/src/apps/deskflow-core/IpcChannel.*`:新增的 NDJSON IPC 模块
- `ipc-protocol/messages.json`:共享 IPC 消息 schema
- `packaging/`:PyInstaller spec + 构建脚本
- `.github/workflows/`:CI (macOS arm64/x86_64 + Windows + 测试)

详见 [docs/adr/0001-architecture-fork-deskflow-pyside6-subprocess-ipc.md](docs/adr/0001-architecture-fork-deskflow-pyside6-subprocess-ipc.md)。

## 验收

13 条验收标准见 [docs/acceptance-checklist.md](docs/acceptance-checklist.md)。

## 许可

Deskflow 上游为 GPL-2.0-only WITH LicenseRef-OpenSSL-Exception(见 `vendor/deskflow/LICENSE`)。Mouser 新增代码遵循相同许可。

## 致谢

- [Deskflow](https://github.com/deskflow/deskflow) — C++ core 上游
- [Synergy](https://github.com/DEAKSoftware/Synergy) / [Barrier](https://github.com/debauchee/barrier) — 协议兼容前辈
