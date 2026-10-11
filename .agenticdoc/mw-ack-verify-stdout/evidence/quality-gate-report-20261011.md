# Quality Gate Report: mw-ack-verify-stdout

**时间**: 2026-10-11 17:45 +08:00
**触发**: 手动（PM 收口 `advance_phase … done` 前的质检门）
**范围**: 本 key 全量（trivial-fix fast path）
**执行形态**: PM 直执（未派 review worker；`guard`/只读核查 + 复核命令均为本地实跑）

## 前置说明（本 key 与标准 QG 的差异）

本 key 走 mini-spec 快径，**无 `design.md` / `evidence-requirement.md` / `tasks/`**，因此标准 QG 的
前置门禁（AC→VC 映射、ac_fingerprint、baseline 目录）不适用。按 `workflow-quality-gate.md` Step 2 的
机械生成口径，问题清单由 `mini-spec.md` 的 **AC-1 / AC-2 / VC-1** 生成（等价于 spec AC + VC 两类来源），
另加 1 条交叉问题（提交/工作树一致性）。

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-1 | 默认 vitest 配置（`silent: "passed-only"`）下，真实 stdout 含 `[VERIFY] VC-004: acked=mw-widget-terminal-lifecycle/t-01-ack-store, persisted=yes`，且 5/5 绿、退出码 0 | ✅ 充分 | `evidence/qg-target-test-20261011.txt`（2026-10-11 17:42:07 复跑，`Tests 5 passed (5)`、`exit=0`）+ `evidence/ack-test-stdout-after-20261010.txt` | 两次独立运行（10-10 15:25 / 10-11 17:42）结果一致 |
| Q-AC-2 | 埋点不再走 `console`（文件内 `console.log` = 0）；`biome check` 0 告警；`tsgo --noEmit` 无本文件告警 | ✅ 充分 | `evidence/verify-run-20261010.md`（计数 0、`Checked 1 file … No fixes applied`、`npm run check` 全绿）；本次补充复核 HEAD 版 `console.log` 计数 = 0、marker 行为 `process.stdout.write` | 全量 `npm run check` 未在本次复跑：工作树被其他窗口的未提交 WIP（`mw_common.py`/`mw.py`/`launcher.py`/`pm-orchestrator.ts`/`worker-store.ts`）占用，复跑会被无关改动污染；本 key 的写面（单测试文件）自 10-10 提交后未再变化 |
| Q-VC-1 | 负向对照成立：同一命令、同一 cwd，改前 stdout 无 VC-004 行、改后有 | ✅ 充分 | `evidence/ack-test-stdout-before-20261010.txt`（0 行）/ `…-after-…txt`（1 行）+ `verify-run-20261010.md` 对照表 | 证明该埋点确实不可达，而非"本来就该有" |
| Q-X-1（交叉派生） | 交付已入库且工作树无残留修改（收口不得留中间态） | ✅ 充分 | `git status --porcelain <file>` 空；`git log -1 -- <file>` = `1a2144163`；`git show HEAD:<file>` 含 `verify()` + `process.stdout.write`、`console.log` 计数 0 | 收口前实测 |

## 汇总

- **总问题数**: 4
- **通过（充分）**: 4（100%）
- **有条件通过（不足）**: 0
- **未通过（无证据）**: 0

**质检结论**: ✅ 通过

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|------|------|---------|---------|
| —（无） | — | — | — |

## 二次印证结论

- 检查 1（spec 中每个约束是否都被覆盖）：mini-spec 无性能/安全/平台类约束 → N/A。
- 检查 2（design Function Flow 每个节点是否有 Q）：快径无 design.md → N/A。
- 检查 3（Coverage Matrix 异常路径行）：唯一异常路径 = "埋点不可达/被缓冲吞掉"，由 Q-VC-1 的负向对照覆盖。
- 检查 4（task 的 vc_refs 空绑定）：无 tasks/（PM 直执）→ N/A。

**结论：无遗漏问题。**

## 范围外（已登记，不在本次质检判定内）

同类埋点 **37 处 / 8 个文件**（`console.log("[VERIFY] …")` + `silent: "passed-only"`）——按 D-002
不在本 key 修复，去向已写入 `achieved.md`「遗留」第 1 条。它们不影响本 key 的 4 条问题判定。
