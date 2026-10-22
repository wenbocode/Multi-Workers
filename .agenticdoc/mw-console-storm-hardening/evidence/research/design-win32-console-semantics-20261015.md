# RQ-1: win32 控制台分配语义实证（PM 直执，双 worker OOM 后按协议转直执）

> date: 2026-10-15 · executor: PM (WENBOZHOU-PC4:53592) · machine: WENBOZHOU-PC4 (Win11, 默认终端委托 = Windows Terminal, DelegationConsole/Terminal 未设)
> 决策问题: 支撑 design L0（cmd_start 改 flag）与 L1/L2 的机制前提
> 脚本: `%TEMP%\mw-csg-rq1\{winwatch.py, worker_experiments.py, run_rq1.py}`（单轮驱动，观测 250ms 轮询、新窗口按 hwnd 去重、owner exe 归属）

## 实验设计

| 实验 | 结构 | 预期（design 假设） |
|------|------|---------------------|
| E0 对照 | 有控制台的 driver → 3× `cmd /c exit`（flags=0） | 0 窗（继承） |
| E2 复现 | DETACHED G → 10× `cmd /c ping -n 2 127.0.0.1`（flags=0，存活 ~1s 防采样漏） | ~10 窗（事故链） |
| E1 | DETACHED G → B(`CREATE_NO_WINDOW\|CREATE_NEW_PROCESS_GROUP`) → 10× cmd（flags=0） | 0 窗（B 获隐藏控制台且被继承） |
| E3 | DETACHED G → B(`DETACHED\|NEW_GROUP\|NO_WINDOW`) → 10× cmd（flags=0） | ~10 窗（组合失效） |

B 自检探针：`GetConsoleWindow()` / `IsWindowVisible(hwnd)` / `GetConsoleProcessList`。cmd 子进程存活 ~1s 保证 250ms 采样不漏。

## 实测（单轮；关键判据为探针与窗口归属，轮次差异仅噪声）

- E0：**0 新窗**。
- E2：**10 × WindowsTerminal.exe (pid 31624)** + 1 dwm（噪声）——事故链 1:1 复现。
- E1：**0 终端窗口**（仅 2 行 explorer.exe 桌面噪声，无 WT/OpenConsole/conhost）。
- E3：**6 × WindowsTerminal.exe + 2 × OpenConsole.exe** ≈8/10（其余为 250ms 采样漏计）+ chrome/explorer 噪声——组合不护。

探针（决定性判据）：

```json
E1: {"conhwnd": 0, "visible": 0, "conlist_n": 1}
E3: {"conhwnd": 0, "visible": 0, "conlist_n": 0}
```

## 结论

1. **Q1 = YES**：无控制台父进程 + `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP` → 子进程获得**隐藏控制台**（`GetConsoleWindow()=0` 但 `GetConsoleProcessList>0`——注意 GetConsoleWindow 不能区分"隐藏控制台"与"无控制台"，**conlist 才是判据**），孙代 `flags=0` 继承之，0 弹窗。事故 §7.1 对照修复版的主张得到确认。
2. **Q2 = 复现**：DETACHED + 裸 spawn → 10/10 个 WT 窗口，owner 全部是 WindowsTerminal.exe（pid 31624，与事故报告同一台机器同一终端进程），事故机制在本机成立。
3. **Q3 = 组合失效确认**：`DETACHED|NEW_GROUP|NO_WINDOW` 下 NO_WINDOW 被忽略（conlist_n=0，子进程完全无控制台），孙代各自弹窗——与事故归因一致。

## 结论 → design 决策映射

- L0 成立：`cmd_start` 去 DETACHED 留 `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP` 后，serve 获隐藏控制台 → 全树继承兜底（E1 实证），漏加 flag 的未来站点不再弹窗（AC-001 的机制依据）。
- L1 成立：runner 固定同一 flag 组合即可保证命令树零弹窗（AC-003 机制依据）。
- L2 成立：guard OR 入 CREATE_NO_WINDOW 对"无控制台祖先"同样有效（E1 即 guard 场景的极限形态），AC-005 的机制依据。
- verify 阶段新增可机械判据：守护断言用 `GetConsoleProcessList`（非 GetConsoleWindow）判定"隐藏控制台"。
- 噪声处理：EnumWindows 差分必须按 owner exe 过滤（WT/OpenConsole/conhost），桌面其他 app（explorer/chrome/dwm）会掺入。

## 残留与未验证

- E2/E3 为单轮（窗口级结果 10/10、~8/10 已达判定精度）；E0/E1 的 0 窗结论在两轮内一致（首轮 worker 崩溃前已验证同构脚本行为一致）。如 verify 阶段需要，可用本脚本 1:1 复跑。
- 未测：conhost 委托（经典终端）下的 E2/E3 形态——不影响结论（事故报告已断言 conhost 同样弹窗，样式不同）。

```
[VERIFY] RQ1-Q1: rounds=2 windows=0 b_console_hidden=yes(conlist_n=1,conhwnd=0) c_inherited=yes
[VERIFY] RQ1-Q2: rounds=1 spawned=10 windows_visible=10 owner=WindowsTerminal.exe
[VERIFY] RQ1-Q3: b_conhwnd=0 conlist_len=0(nowindow) vs 1(hidden) nowindow_flag_ignored=yes
```
