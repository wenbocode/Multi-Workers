# T-10: 守卫覆盖面：`_autopilot/**` 纳入封堵（安全属性）

- 波次: **1** · 依赖: T-02
- 写面（独占）: 
  - `packages/coding-agent/src/extensions/agent-team-loop/shared/xkey-gate-guard.ts`
  - `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts`（新建）
- AC: AC-020, AC-030 · VC: VC-025, VC-026
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

被审方当前可以 append 伪造 timeline 事件、并自己翻转开关文件——审计与熔断都建立在这些文件上。本卡把封堵面从 `_autopilot/gates` 扩到 `_autopilot/**`（`timeline.jsonl` / `config.json` / `auto-decisions.jsonl`）。

## 交付物

- `xkey-gate-guard.ts:60` 的 `GATE_DIR_FRAGMENT` 语义扩为整个 `_autopilot` 目录；保留既有 gates 封堵行为。
- 拒绝时**留痕**（沿用既有 blocked 事件/日志通道，不新增状态文件）。
- 新测试：写各类目标被拒 + 尾部相似路径不误伤 + gates 行为不回归。

## 契约（不得重定义）

- 只扩**封堵范围**，不放开任何写权限；agent 对 gate 目录的写权限仍为拒绝（VC-026）。
- 残余风险必须写进代码注释：同 uid 带外进程无法在应用层阻止，守卫只保证"经工具通道"的伪造留痕。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/xkey-gate-guard-coverage.test.ts`

## 非空洞对照（必须附在回执里）

- 把封堵面缩回 `gates` ⇒ 写 `timeline.jsonl` 用例必须红。
- 用 `_autopilotX` 相似路径 ⇒ 必须**不**被误伤（边界断言）。
- 写 `_autopilot/gates/gate-0001.md` ⇒ 仍必须被拒（不回归）。

## 风险与注意

- 该守卫此前**反向拦住过只读命令**（RQ-8 实测），扩面时必须同时跑只读路径用例（read/find/grep 通过）。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-10-guard-coverage/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
