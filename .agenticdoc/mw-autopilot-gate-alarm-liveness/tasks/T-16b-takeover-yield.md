# T-16b — 人工接管不得因合成 claim 而被迫 `force`（R-1 收口）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-014, AC-002
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t16-synthetic-claim/report.md` `## 残留与未验证` **R-1**；
      `design.md` §2 D9（与人工 `switch_key` 的移交与冲突）；`spec.md` D-012/D-013

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（派发不得以"有人接管"为前置 —— 但**人也必须随时能接管**；若自动接管把人工入口变难，等于用一个新阻塞换掉旧阻塞）。
- **实测缺口（T-16 自报 R-1，属真实产品缺口，非假阳性）**：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 的 `claimState` 把**任何外部 host 的 claim 判为 `held-live`** ⇒ T-16 引入的合成 claim `autopilot@<host>:<pid>` 会让**人工非强制 `switch_key` 被拒绝**（必须 `force=true`）。conductor 侧行为是对的（**主动让位、不再抢回**），坏的是**接管侧的判定**。
- 已落可复用的解析能力（**必须复用，不得另写一套**）：T-16 已在 `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts` 落地**合成 claim 的解析**与"live synthetic claim 作为 owner evidence"的判定；T-17/T-17b 无关。
- 注意区分：`ui-bridge.ts::claimState` 的判据是"**谁持有**"，不是"**能否覆盖**"。合成 claim 与人工 claim 的**可让位性**不同，这正是本卡要修的语义。

- 已核实锚点（本 key 已落，可复核）：`packages/multi-workers/autopilot/conductor.py:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC`、`:236 synthetic_claim_owner`、`:263 _synthetic_claim_stale`（该函数内 `:275` 调 `mw_common.parse_synthetic_claim`）；`packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts` 的合成 claim 解析（T-16 交付，本卡必须复用）。

## 要求

1. **让位语义**：`claimState` 必须区分"**人工（外部 host）claim**"与"**本机 conductor 合成 claim（`autopilot@...`）**"：后者是**可让位**的，人工非强制接管**必须成功**，且不得要求 `force=true`。
2. **不得越界放宽**：真正由**其他 live 窗口**持有的 claim **仍然必须**需要 `force`（这条不得被顺手放宽 —— 否则会破坏"跨窗口读写守卫"的既有保障）。测试必须同时覆盖两侧。
3. **留痕**：让位发生时按 T-16 已落的既有 trace 形态留痕（复用既有名称，不新造事件；不得引入新事件名）。
4. **一致性**：判定必须**复用** `index-store.ts` 的合成 claim 解析（单一真相），不得在 `ui-bridge.ts` 里重现字符串前缀判断而两边漂移。
5. **回归测试**：① 合成 claim 存在 ⇒ 人工非强制接管成功；② 其他 live 人工窗口持有 ⇒ 仍需 `force`；③ 合成 claim + 接管后 conductor 不抢回（可与 T-16 测试呼应，但不重复实现）；④ 解析复用断言（合成判定只有一处实现）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`（**仅当**需要导出既有合成判定给 `claimState` 用）
- 新增：`packages/coding-agent/test/suite/mwgal-t16b-takeover-yield.test.ts`
- 既有 TS 测试中因本卡行为必须更新的期望（逐条说明；不得改弱断言）

## 写入禁止面

- `packages/multi-workers/**`（T-14b 之外的 Python 面本卡不碰）
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`、`status-model.ts`
- `shared/change-ledger.ts`、`worker/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t16b-takeover-yield.test.ts test/suite/index-store.test.ts`

## 改动历史

（填写：`claimState` 的判据演化、为何"可让位性"与"持有者身份"必须分开、复用点、被否决的替代方案（例如"让人工一律 force"为何不可接受）。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
