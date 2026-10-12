# T-05: TS 镜像三件套（事件集 / `GateView.ageMs` / 三个配置键）

- 波次: **0** · 依赖: —
- 写面（独占）:
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（事件集段 `:962-988`、`GateView` `:1238`、配置镜像 `:105/:108/:147`）
- AC: AC-001, AC-007, AC-008, AC-015 · VC: VC-011
- 基线: `10446aefb`

## 目标

让 TS 侧的词汇表、字段镜像与 Python 侧**逐项一致**，并把"pending 时长"暴露到 `/autopilot status` 的 `GateView` 上（G2 的可见面之一）。

## 交付物

1. **事件集**：`EVENT_TYPES` 增 3 个名字（与 `T-03` 逐字相同：`l3-aborted` / `gate-reminder` / `contract-refused`）。
2. **`GateView.ageMs`**：把门行已有的 `createdAt`（`GateRecord.createdAt`，`:654`）换算成 `ageMs = now - createdAt`（`createdAt` 不可得 ⇒ `ageMs: null`，**不得**回退到 `expires_at`——历史 v1 门全缺）。
3. **配置镜像**：`DEFAULT_CONFIG` 镜像 **17 → 20** 键（T-18 三键 14→17 已落地；本卡另加 T-02 的三键），取值与值域逐项同 `T-02`（含 `gate_reminder_max` 的 1..2）。
4. `blocked_on_human` 真值表：与 Python 侧同口径——"待答门存在 **且** 非终态 worker 行数 == 0"（**不是** `running`）。

## 契约（不得重定义）

- 3 个事件名、3 个键名、`ageMs` 语义由本卡定义，`T-14` 只做锁刷新，不得改写。
- 不得在此卡引入 `tickStale` 之外的第二个 staleness 概念（`tickStale` 是 TS-only，Python 侧 0 命中，保持现状）。
- 只加字段，不改既有字段的类型与语义。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-event-parity.test.ts test/suite/autopilot-status-parity.test.ts`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts`

## 非空洞对照（必须附在回执里）

- 摘掉一个事件名 ⇒ `autopilot-event-parity.test.ts` 的集合相等断言必须转红。
- 把某个配置键的默认值改一位 ⇒ parity / console 锁必须转红。

## 风险与注意

- `autopilot-console.test.ts:374-378` 对 gates 行做**精确 `toEqual`**：本卡加字段后该断言**必然红**，属预期；把新的期望值写进回执，由 `T-14` 统一刷新（或本卡就地最小更新并点名）。
- `status-model.ts` 是单卡独占文件（三段同文件），不要拆派并行。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-05-ts-mirror/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
