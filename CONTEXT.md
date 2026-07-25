# Context

## Glossary

| Term | Meaning | Notes |
|---|---|---|
| Mouser | 本产品名 | 跨平台键鼠共享软件 |
| Core | C++ daemon 二进制 | Forked from Deskflow v1.26.0+,裁剪到 macOS+Windows |
| GUI | Python(PySide6)前端 | 通过 subprocess + JSON IPC 控制 Core |
| Daemon | Core 运行时实例 | 模式为 server 或 client,原 Deskflow 术语 |
| Server | 主控端 | 捕获本地键鼠输入,通过网络发给 client |
| Client | 被控端 | 接收网络事件,注入为本地系统输入 |
| IPC | GUI ↔ Daemon 通信通道 | NDJSON over stdin/stdout |
| Deskflow | 上游开源项目 | github.com/deskflow/deskflow,GPL-2.0 |
| Synergy 1 / Barrier / Input Leap | 协议兼容的项目 | mouser core 与它们网络层兼容 |
| TLS | 传输层加密 | Deskflow 默认开启,mouser 保留 |
| Accessibility | macOS 辅助功能权限 | Core 启动必需,GUI 引导用户授予 |
| SendInput | Windows 输入注入 API | Core 在 Windows 端使用 |
| CGEvent | macOS Quartz Event Services | Core 在 macOS 端使用,通过 CGEventTap 捕获 |
| libei / libportal | Linux Wayland 输入库 | mouser 已移除依赖,Out of scope |
