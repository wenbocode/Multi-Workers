# Research: 控制台窗口风暴事故归因与修复输入（spec）

> date: 2026-10-15
> 决策问题: 支撑 spec §1 范围（L0-L3 四层修复）、§2 约束（不改注册表/不散改测试文件）、§4 风险

## 调研方法与出处

- 完整事故报告: `H:\MWWorkeSpace\fix\.agenticdoc\incidents\20261015-console-window-storm.md`（status: attribution-complete，当日实时观测，`[OBSERVED]`/`[INFERRED]` 已分级）
- 本机（WENBOZHOU-PC4，Win11，默认终端委托 = Windows Terminal）为事故影响机器，复现/实证可直接进行

## 发现（事故报告核心事实摘录）

1. 根因链：DETACHED 父进程（无控制台）+ 测试代码 `creationflags=0` 裸 spawn `git`/`cmd`/`python` → 每个控制台子进程被分配全新控制台 → Win11 默认委托 WT 时每个新控制台渲染为可见窗口。速率实测：12 秒 95 个新控制台进程、10 秒 14 个新可见窗口，持续 1h51m。
2. Win32 flag 语义（MSDN，事故 §2）：`DETACHED_PROCESS`（根本没有控制台）与 `CREATE_NO_WINDOW`（有控制台但不显示窗口）互斥；组合使用时 DETACHED 静默生效、CREATE_NO_WINDOW 被忽略 → 写组合的人以为"子进程树无窗口"，实际只是"本进程无窗口"，后代各自弹窗。
3. 对照修复（事故 §7.1）：父进程改用仅 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` → 零窗口（子进程获得隐藏控制台，后代继承之）。
4. 事故 §8 修复建议（本 spec 的需求输入）：
   - A（FeatureMigrator 侧单点）：改 `_p5_launch.py` 两处 spawn——移交该项目，不入本 key。
   - B1（框架）：标准 detached-runner 唯一入口，固定 `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`，禁止 DETACHED_PROCESS，落盘心跳/marker。
   - B2（框架）：测试面兜底——runner 注入 conftest/sitecustomize，win32 上给 `subprocess.run/Popen` 统一补 `CREATE_NO_WINDOW`（未显式指定 console 语义时）。
   - B3（框架）：互斥坑写入框架文档 + lint/评审提示。
   - C（不推荐，约束）：不改默认终端委托注册表；不在每个测试文件散改 creationflags。
5. 排除项（§6）：mw 服务派发 worker 频率低 2 个数量级、无可归因可见窗口——本次修复不针对 launcher 现有 flag 用法（已正确）。

## 结论 → 决策映射

- 事故 §8-B1/B2/B3 → spec §1.1 目标四层（L1/L2/L3）与 §1.3 场景 B/C/D。
- 事故 §8-C → spec §1.4 范围排除 + §2 约束。
- 事故 §7.1 对照修复 → spec §3 AC-001 的机制依据与 §4 风险 RQ-1 的实证方法（最小复现脚本已有）。
- 事故 §9 → 移交项（FeatureMigrator triage），不入本 key。
