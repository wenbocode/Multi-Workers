# T-12: G3 答案面（gate-writer 闭集校验）+ G4 重臂（autoStartMonitor）

- 波次: **2** · 依赖: T-08, T-11
- 写面（独占）:
  - `.../agent-team-loop/autopilot/gate-writer.ts`（`AnswerGateOptions` `:24-48`、`ANSWER_FIELDS` `:50`、`rewriteAnswerFields` `:101-133`）
  - `.../agent-team-loop/autopilot/console.ts`（`cmdGate` `:455-495`、`autoStartMonitor` `:709-725`）
- AC: AC-009, AC-012, AC-018 · VC: VC-012, VC-023
- 基线: `10446aefb`

## 目标

让**人**能把授权动作类型写进闸门（唯一合法写入路径），并修掉"会话替换后面板永久消失"（G4 的生命周期半边）。

## 交付物

- `gate-writer.ts`：
  - `AnswerGateOptions` 增 `authorizes?: string[]`；`ANSWER_FIELDS` 增 `authorizes`；
  - `rewriteAnswerFields` **只重写已存在的行** ⇒ 依赖 `T-10` 的物化（门文件里已有 `authorizes:` 行）；
  - 闭集校验 `{retry, contract-change}`：越界值**拒绝**（fail-closed），错误信息点名合法集合。
- `console.ts`：`cmdGate` 增 `--authorizes <a,b>` 参数面（逗号分隔，空值/未给 = 不写）。
- **G4 重臂**：`autoStartMonitor`（`:709-725`）的幂等早退（`:713`，`if (isMonitorActive()) return true;`）改为"已有活动但 `ctx` 不同 ⇒ 先 `stopMonitor` 再 `startMonitor`"。
- `autopilot-monitor.test.ts:761-765` 补反向用例（现状把"幂等不重启"当正确行为）。

## 契约（不得重定义）

- 闭集逐字 `{retry, contract-change}`（与 T-04 同一集合，不得各写一份）。
- **只有人**能写 `authorizes`：worker 侧伪造由既有 `xkey-gate-guard.ts` 拦（L0，本卡不改）。
- `stopMonitor` 语义不动（非活动时不清 widget）。
- 不改 `monitor.ts`（T-08/T-13 的写面）。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-gate-presentation.test.ts`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts`

## 非空洞对照（必须附在回执里）

- 传一个不在闭集里的值（如 `install`）⇒ 必须被拒且门文件不变（摘掉校验 ⇒ 用例转红）。
- 摘掉 `autoStartMonitor` 的 ctx 变化分支 ⇒ `/new` 后面板消失的用例必须转红（VC-023）。

## 风险与注意

- `console.ts` 串行链第二段（T-08 → T-12）：开工前确认 T-08 已落，且只在 `cmdGate` / `autoStartMonitor` 两处改动，不碰 T-08 的门行呈现段。
- `rewriteAnswerFields` 的"只重写已存在行"是关键：若 `T-10` 尚未物化，人应答会静默丢掉 `authorizes`——本卡用例必须覆盖"门文件里原本没有该行"的情形并给出明确行为（拒绝 + 提示）。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-12-g3-writer-g4-rearm/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。


## PM 追记（2026-10-10 20:35，T-04 R1 的连带要求）

T-04 把 `authorizes` 落成“**冻结 40 名单之外的已识别扩展字段**”（`_JSON_LIST_FIELDS` 成员；design D-011 `[REVISED @ 2026-10-10 20:35]` 有完整理由）。TS 侧**必须**镜像同一形状，否则 `authorizes` 会在 TS 面板被当未知字段跳过（Python 可解析 / TS 不可见的新分叉）：

- `autopilot/status-model.ts` 的 `GATE_JSON_LIST_FIELDS`（单行 JSON 数组字段集）加入 `"authorizes"`；
- 未知/未识别字段检查（T-04 报告定位在约 `:811-812`）相应放宽到“`GATE_FRONTMATTER_FIELDS` **或** `GATE_JSON_LIST_FIELDS`”；
- 值校验加闭集 `{retry, contract-change}`（越界 fail-closed，与 Python `AUTHORIZES_ACTIONS` 逐字同集）；
- `GATE_FRONTMATTER_FIELDS` 的 **40 名顺序一行不改**（跨语言 parity 锁 `autopilot-gate-presentation.test.ts:206-235` 依赖它）。
- 非空洞对照：造一个带 `authorizes: ["contract-change"]` 的门文件 ⇒ TS 侧必须能解析并保留该字段；摘掉 `GATE_JSON_LIST_FIELDS` 那一项 ⇒ 对应用例必须转红。
