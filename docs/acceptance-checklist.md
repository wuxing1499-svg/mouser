# Mouser Acceptance Checklist

> Source: plan/mouser 阶段 8 step 40
> 13 acceptance criteria (AC-1 ~ AC-13). Each AC is binary verifiable.
> Tick the box `[x]` once verified. AC-11/AC-12/AC-13 added for spec drift D7/D8.

## AC-1: Mac server → Win client 鼠标跨屏

- [ ] 在 Mac 部署 `Mouser.app`,在 Windows 部署 `Mouser\Mouser.exe`
- [ ] Mac 端托盘菜单选 "Server mode";Win 端选 "Client mode"
- [ ] Mac 屏光标右滑出屏 → Win 屏出现光标,键盘输入焦点跟随
- [ ] **验证命令**:截图前后对比,光标位置在 Win 屏内

## AC-2: Win server → Mac client 鼠标跨屏

- [ ] 反向 AC-1:Win 端 Server,Mac 端 Client
- [ ] Win 屏光标右滑 → Mac 屏出现光标
- [ ] **验证命令**:截图前后对比

## AC-3: 剪贴板纯文本同步

- [ ] Mac 上 `Cmd+C` 复制 "hello mouser" → Win 上 `Ctrl+V` → 文本一致
- [ ] 反向:Win `Ctrl+C` → Mac `Cmd+V` → 文本一致
- [ ] **注**:Rich text 不在 v1 范围,只验证纯文本

## AC-4: 托盘图标状态反映连接状态

- [ ] server + client 都启动且连接成功 → 托盘图标显示 "connected" (绿)
- [ ] 关闭其中一端 → 5 秒内托盘图标变 "disconnected" (灰)
- [ ] `kill -9 deskflow-core`(Mac)或任务管理器结束进程(Win) → 5 秒内托盘变 "error" (红) + tooltip 显示原因
- [ ] **验证命令**:`date +%s; pkill -9 deskflow-core; date +%s` — 两时间戳差 < 5

## AC-5: 模式切换 (server ↔ client)

- [ ] GUI 托盘菜单点 "Switch to client" → 旧进程退出 → 新进程以 `--client` 启动
- [ ] 托盘状态 3 秒内更新为新模式
- [ ] **验证命令**:日志时间戳对比 switch 前后 daemon PID

## AC-6: macOS Accessibility 权限引导

- [ ] 未授权状态下启动 GUI → 弹出 `QMessageBox` 含文案 "系统设置 > 隐私与安全 > 辅助功能"
- [ ] **复现命令**:`tccutil reset Accessibility com.ndq.mouser` 后启动 GUI
- [ ] 授权后重启 GUI → 不再弹窗,daemon 可正常捕获键鼠

## AC-7: TLS 加密传输

- [ ] Wireshark 抓 24800 端口 TCP 流量 → "跟随 TCP Stream" 内容为乱码 (TLS),非明文 "hello"
- [ ] **验证命令**:`tshark -i lo0 -f "port 24800" -Y "tls" -V | head -50`

## AC-8: 干净机器可运行

- [ ] macOS:把 DMG 拷到未装 Python/Qt 的 Mac → 拖到 Applications → 双击 → 启动
- [ ] Windows:zip 解压后双击 `Mouser.exe` → 启动
- [ ] **Windows 备注**:若缺 VC++ Redistributable,文档提示安装 (见 README.md)

## AC-9: daemon crash 检测

- [ ] 运行中 `pkill -9 deskflow-core` (Mac) 或 任务管理器结束进程 (Win)
- [ ] GUI 在 ≤ 5 秒内托盘变红 + 弹出 "重启 daemon" 按钮
- [ ] **验证命令**:`pkill -9 deskflow-core; sleep 5; osascript -e 'tell application "System Events" to get name of every process whose name contains "Mouser"'`

## AC-10: GUI 跨平台代码一致

- [ ] `git diff gui/main.py` 在 mac 和 win 构建产物中无 `#ifdef` 平台分支
- [ ] 仅 `gui/resources/` 图标差异 (svg 资源本身无平台分支)
- [ ] **验证命令**:`grep -rn "if sys.platform\|if platform.system" gui/` — 应仅出现在 `daemon.py` 的 binary 名与 `CREATE_NO_WINDOW` 处

## AC-11: macOS ad-hoc 签名 (spec drift D7)

- [ ] `codesign --verify --verbose=4 dist/Mouser.app` 退出码 0
- [ ] 启动 GUI 后 `subprocess.Popen` 启动 `deskflow-core` 子进程不返回 `Killed: 9`
- [ ] **CI 验证**:`build-macos.yml` 中 `codesign --force --deep --sign - dist/Mouser.app` 步骤通过
- [ ] **验证命令**:
  ```bash
  codesign --verify --verbose=4 dist/Mouser.app
  echo $?  # 期望 0
  ```

## AC-12: NDJSON HELLO 消息 (spec drift D4)

- [ ] `deskflow-core` 启动后,GUI 通过 stderr 收到首条 `HELLO` NDJSON 消息
- [ ] JSON 解析成功,`type` 字段值为 `"Hello"`
- [ ] **验证命令**:
  ```bash
  echo '' | ./build/bin/Deskflow.app/Contents/MacOS/deskflow-core --client 2>ipc.log
  head -1 ipc.log | python -c "import sys,json; m=json.load(sys.stdin); assert m['type']=='Hello', m"
  ```

## AC-13: CI 三平台产物 (spec drift D8)

- [ ] GitHub Actions `build-macos.yml` 在 `macos-14` (arm64) 上产出 `Mouser-macos-arm64.dmg`
- [ ] GitHub Actions `build-macos.yml` 在 `macos-13` (x86_64) 上产出 `Mouser-macos-x86_64.dmg`
- [ ] GitHub Actions `build-windows.yml` 在 `windows-2022` 上产出 `Mouser-windows-x86_64.zip`
- [ ] 三个 artifact 均可下载且非空 (size > 0)
- [ ] **验证命令**:`gh run list --workflow=build-macos.yml --limit 1` + `gh run download <run-id>`

---

## 自动化测试覆盖映射

| AC | 自动化测试 | 备注 |
|---|---|---|
| AC-1 ~ AC-5 | 无 (需真机两台) | 手动验收 |
| AC-6 | 无 (需 macOS GUI 交互) | 手动验收 |
| AC-7 | 无 (需 Wireshark 抓包) | 手动验收 |
| AC-8 | 无 (需干净机器) | 手动验收 |
| AC-9 | `tests/test_daemon.py` (部分) | crash 检测逻辑有单测 |
| AC-10 | `tests/test_gui_smoke.py` (部分) | 跨平台 import smoke |
| AC-11 | `tests/test_ci_workflows.py::test_macos_workflow_runs_codesign` | 验证 CI 含 codesign 步骤 |
| AC-12 | `tests/test_ipc_protocol.py` | 验证 messages.json schema |
| AC-13 | `tests/test_ci_workflows.py` | 验证三平台 workflow 结构 |

## 验收结果汇总

| AC | 状态 | 验证人 | 日期 | 备注 |
|---|---|---|---|---|
| AC-1 | ☐ | | | |
| AC-2 | ☐ | | | |
| AC-3 | ☐ | | | |
| AC-4 | ☐ | | | |
| AC-5 | ☐ | | | |
| AC-6 | ☐ | | | |
| AC-7 | ☐ | | | |
| AC-8 | ☐ | | | |
| AC-9 | ☐ | | | |
| AC-10 | ☐ | | | |
| AC-11 | ☐ | | | |
| AC-12 | ☐ | | | |
| AC-13 | ☐ | | | |
