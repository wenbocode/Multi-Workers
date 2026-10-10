# PM State: mw-ack-verify-stdout

## 1. Snapshot
- Key: mw-ack-verify-stdout
- Next Action: 实现与验证已完成（AC-1 / AC-2 / VC-1 均有原始输出为证，见 `evidence/verify-run-20261010.md`）。
  剩余动作：① 用户决定是否提交（当前为未提交工作树状态）；② 37 处同类埋点是否另立 key。
- Started: 2026-10-10 15:20
- Updated: 2026-10-10 15:32

## 2. Task Status
*(trivial-fix fast path：单文件单调用点，未派 worker，PM 直执)*

| 项 | 状态 | 证据 |
|---|---|---|
| ack 测试埋点改直写 stdout | 完成 | `evidence/verify-run-20261010.md`（before 0 行 / after 1 行，5/5 绿） |
| biome / tsgo / 全量 check | 完成 | `npm run check` 全绿 + 单文件 biome 0 告警 |
| `.gitignore` 增 `.tmp/` | 完成 | `git status` 中 `.tmp/` 不再列为 untracked |

## 3. Evidence Ledger

| ID | 内容 | 位置 |
|---|---|---|
| E-1 | 修改前 stdout 抓取（无 VC-004 行） | `evidence/ack-test-stdout-before-20261010.txt` |
| E-2 | 修改后 stdout 抓取（含 VC-004 行） | `evidence/ack-test-stdout-after-20261010.txt` |
| E-3 | before/after 对照 + check 结果 + 同类残留枚举 | `evidence/verify-run-20261010.md` |

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions
- D-001（2026-10-10）：**新建 key**（不并入 `mw-widget-terminal-lifecycle`）。理由：该 key 已 DONE、AC 锁定，且本条交付物是「IN-2 覆盖式丢失的修复重建」，属独立交付面；依赖面指向 `mw-widget-terminal-lifecycle`（AC-004/VC-004 的原始归属）。
- D-002（2026-10-10）：**只修被丢失的那一处**，不扩散到另外 37 处同类埋点。理由：用户口径是「要重做」丢失的修复；扩散会触碰 8 个已提交测试文件（跨 key 写面），应另立 key 或并入 `mw-gate-verdict-hardening` 的证据通道议题。
- D-003（2026-10-10）：**不做 dist / CHANGELOG**。理由：只改测试文件，不进 dist，无用户可见行为变化。
- D-004（2026-10-10）：诚实边界——本条为**重推导**而非字节级复原。丢失版本在 git 中不可恢复（无 stash / 无 dangling blob 对应；JSONL 检索无法唯一定位），故只声明「行为等价由实测支撑」，不声明等同。
- D-005（2026-10-10）：用户附带项——`.gitignore` 增加 `.tmp/`（单行配置，PM 直执）。

## 6. Turn End Records
*(empty)*

## 7. Process Log
- 15:2x：读取记录与 patch 中的轮次 2/轮次 3 原文，确认缺陷机制（vitest `silent: "passed-only"` 吞 `console.log`）。
- 15:25:19：修改前基线运行（HEAD 版）→ 5/5 绿、stdout 无 `VC-004`（负向对照）。
- 15:25:27：应用修改（`verify()` 助手 + 埋点切换）→ 5/5 绿、stdout 出现唯一 `VC-004` 行。
- 15:2x：`npm run check` 全绿；单文件 biome 0 告警；`.gitignore` 加 `.tmp/`。
