# ADR 0001: Architecture — Fork Deskflow + PySide6 GUI + Subprocess IPC

Status: Accepted
Date: 2026-07-25

## Context

需要构建一个跨平台(macOS + Windows)键鼠共享软件。已有成熟开源项目:

- **Deskflow**(C++,Qt GUI,GPL-2.0):7225 commits,网络协议与 Synergy 1 / Barrier / Input Leap 兼容,支持 Win/macOS/Linux/BSD
- **Lan Mouse**(Rust,GTK GUI):较新,Wayland 优先,Windows/macOS 支持不如 Deskflow 成熟
- **Mouse without Borders**(C#):仅 Windows,不可用

用户技术栈:Python(proficient)+ PyInstaller + GitHub Actions,目标平台 macOS + Windows。

可选方案:

1. **从零实现**(Python + native binding):学习价值高,但要重新实现 TLS 协议、剪贴板、CGEvent/SendInput 集成、Synergy 兼容协议——工作量数月起步,且性能难保证
2. **Fork Deskflow,全 C++ Qt GUI**:复用最多,但用户不熟 C++,长期维护负担重
3. **Fork Deskflow,裁剪 Linux,PySide6 重写 GUI,subprocess 集成**:复用 C++ core 的成熟实现,GUI 用用户熟悉的 Python,通过 IPC 解耦
4. **Fork Lan Mouse**:Rust 学习成本高,Windows/macOS 支持不成熟

## Decision

采用方案 3:**Fork Deskflow v1.26.0+,裁剪 Linux/BSD/Wayland/libei/libportal,保留 C++ core,用 PySide6 重写 GUI,通过 subprocess + NDJSON over stdin/stdout 与 Core 通信**。

具体:

- Core 保持 C++ 二进制(`mouserd` / `mouserc`),最小改动:仅新增 IPC 通道
- GUI 用 PySide6(Python + Qt),可复用 Deskflow 的 .qss / translations / 图标
- GUI 通过 `subprocess.Popen` 启动 Core,通过 stdin/stdout 交换 JSON 行
- PyInstaller 打包,Core binary 作为 data 文件嵌入

## Consequences

- **正面**:Core 复用成熟实现(TLS / 剪贴板 / CGEvent / SendInput / Synergy 协议兼容);GUI 在用户熟悉的 Python 栈;进程隔离,Core 崩溃不影响 GUI;调试方便(可独立运行 Core);PyInstaller 打包路径清晰
- **负面 / tradeoff**:用户需维护一份 C++ fork(虽最小改动);与 Deskflow 上游存在 fork 分歧风险;PyInstaller + PySide6 包体积约 80MB;macOS 未签名需文档化 `xattr -c`;Core binary 嵌入 PyInstaller 包后调试栈跟踪复杂
- **后续约束**:v1 锁定 Deskflow v1.26.0 tag;定期 rebase 上游;IPC 消息协议需独立 schema 文件维护;不深入修改 Deskflow 内部逻辑(只动 IPC 层与平台裁剪)
