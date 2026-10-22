# T-01 RQ-1: win32 控制台分配语义实证（DETACHED vs CREATE_NO_WINDOW 继承链）

- key: mw-console-storm-hardening · 第 1 批 · type: research
- type: research
- 唯一证据文件: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-win32-console-semantics-20261015.md`（其余仅 `%TEMP%` 下自建实验目录）
- 写入允许面: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-win32-console-semantics-20261015.md` + `%TEMP%/mw-csg-rq1/` 实验目录；写入禁止面: 仓库其余一切（源码/测试/配置/注册表）
- 上下文: goal.md（.agenticdoc/goal.md）「mw 后台服务常驻运行」可靠性维度 + 事故报告 §2/§7.1
- 锚点: `packages/multi-workers/mw.py:506`（cmd_start 的 DETACHED_PROCESS 组合）、`H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md:120`（§7.1 复现脚本）

## 写入允许面

- `.agenticdoc/mw-console-storm-hardening/evidence/research/design-win32-console-semantics-20261015.md`
- `%TEMP%/mw-csg-rq1/`（自建实验目录，仓库外）

## 写入禁止面

- 仓库其余一切（源码/测试/配置/注册表）
- ac_refs: AC-001, AC-005 · deps: 无
- 预计: 30-45min

## 目标

本机（WENBOZHOU-PC4，Win11，默认终端委托 = Windows Terminal）实证回答 design 的三个机制问题，为 L0（`mw.py cmd_start` 改 flag）与 L1（runner 固定 flag）提供一手证据。背景输入：`H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md`（§2 语义、§7.1 复现脚本）与 `H:\git\Multi-Workers\.agenticdoc\mw-console-storm-hardening\spec.md`（AC-001/AC-005）。

## 三个必须回答的问题

1. **Q1（L0 依据）**：控制台全无的父进程（DETACHED 启动）以 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` 拉起子进程 B——B 是否获得一个**隐藏控制台**？B 再以 `creationflags=0` 拉起孙进程 C（cmd.exe），C 是否**继承** B 的隐藏控制台（零可见窗口）？
2. **Q2（对照，事故链确认）**：DETACHED 父进程 + `creationflags=0` 裸 spawn 子进程（事故 §7.1 复现）——是否如事故所述每个子进程弹一个可见终端窗口（数量 = spawn 数）？
3. **Q3（语义边界）**：`DETACHED_PROCESS | CREATE_NO_WINDOW` 组合下 CREATE_NO_WINDOW 是否确实被忽略（子进程无控制台，而非有隐藏控制台）？给出可观测判据（如子进程内 `ctypes.windll.kernel32.GetConsoleWindow()` 返回值 / `GetConsoleProcessList`）。

## 硬契约（方法约束）

- 实验脚本全部写到 `%TEMP%/mw-csg-rq1/`（自建），**禁止**写仓库内任何文件（本任务唯一仓库写面 = 上述 evidence 文件）；实验进程短命（每个 cmd `exit` 即退），实验完删除 `%TEMP%` 现场可保留但需在 evidence 里列清单。
- **禁止**改注册表（`HKCU\Console\%%Startup` 委托键绝对不碰）；禁止安装任何包——只用 Python stdlib（`ctypes` user32/kernel32 做窗口枚举：`EnumWindows` + `IsWindowVisible` + `GetWindowThreadProcessId`，owner PID 归属到 `WindowsTerminal.exe`/`OpenConsole.exe`/`conhost.exe`）。
- 每个问题至少跑 **2 轮**取一致结果；窗口观测轮询 ≤250ms、观测窗 ≥15s（覆盖 Q2 的 10 连发）；`python -X utf8` 跑实验脚本避免编码噪声。
- 进程树证据：`wmic`/`Get-CimInstance Win32_Process` 快照留 parent-pid 链。
- 临时脚本用 write 工具或 Python 写盘（UTF-8 显式编码），禁止 PowerShell 读改写管线（P-001）。
- **输出卫生（首跑 OOM 教训，硬性）**：winwatch/长观测只写文件，bash 命令只输出 tail/汇总（每条命令 stdout ≤ 30 行）；禁止把轮询全量输出、进度流、重复心跳回显到会话；禁止用 `Get-Content` 不带 `-Tail` 读大文件。证据原始行进 evidence 文件，不进会话。

## 步骤

1. 写窗口差分观测器（`%TEMP%/mw-csg-rq1/winwatch.py`）：250ms 轮询 EnumWindows，输出时间戳 + 新增可见顶层窗口 (hwnd, owner_pid, owner_exe, title)。
2. 写三组实验脚本（detached 派发器各自独立进程组）：
   - E1（Q1）: DETACHED 父 → B(`CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`) → B 内循环 spawn 10 个 `cmd /c exit`（flags=0）
   - E2（Q2）: DETACHED 父 → 直接循环 spawn 10 个 `cmd /c exit`（flags=0）（即事故 §7.1）
   - E3（Q3）: DETACHED 父 → B(`DETACHED|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW`)，B 内打印 `GetConsoleWindow()`/`GetConsoleProcessList()` 自检并落盘
   - 另加 E0 对照：普通有控制台父进程 spawn `cmd /c exit`（flags=0）→ 应零弹窗（继承）
3. 并行运行 E1..E3 各配一个 winwatch 实例（或错峰串行，保证观测窗不重叠即可），记录每轮新增窗口数与 owner PID 归属。
4. 结论表：问题 → 判据 → 实测值 → 是否支持 design 假设（Q1 支持则 L0 改法成立；Q2 复现则事故链在本机成立；Q3 判据写明）。

## 验收命令

```bash
# evidence 文件存在且含三轮 [VERIFY] 行
grep -c "VERIFY" .agenticdoc/mw-console-storm-hardening/evidence/research/design-win32-console-semantics-20261015.md
```

## 证据格式（写进 evidence 文件末尾）

```
[VERIFY] RQ1-Q1: rounds=2 windows=0 b_console_hidden=yes|no c_inherited=yes|no
[VERIFY] RQ1-Q2: rounds=2 spawned=10 windows_visible=<n> owner=<WindowsTerminal|conhost|...>
[VERIFY] RQ1-Q3: b_conhwnd=0|nonzero conlist_len=<n> nowindow_flag_ignored=yes|no
```

## 非空判定

Q1 得 windows=0 但 `b_console_hidden=no`（即 B 无控制台、孙代也不弹窗）→ 必须**显式写出**这一语义差异及其对 L0 论证的影响（哪种机制在兜底），不得含糊带过。

## 交付

唯一 evidence 文件（实验脚本路径清单 + 每轮原始观测 tail + 结论表 + [VERIFY] 行）+ 原始输出粘贴。
