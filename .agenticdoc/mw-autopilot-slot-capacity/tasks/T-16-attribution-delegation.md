# T-16: 归属判据委派（T-12 遗留缺口修补）

- 波次: **3** · 依赖: T-07（conductor.py 写面）+ T-12（已交付判据）
- 写面（独占）: `packages/multi-workers/autopilot/conductor.py`（`reconcile_orphans` 段 + `_row_belongs_to`）、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（归属判定点 `:615/:623` 邻域）、`packages/multi-workers/test_autopilot_attribution.py`（追加用例）
- AC: AC-021 · VC: VC-027, VC-028
- **来源**：T-12 回执上报的残留（PM 复算确认）
- **前置禁止**：T-07 未落地前**不得开工**（同文件写面冲突）。

## 目标

T-12 交付了**权威判据**（`mw_common.worker_origin` / `worker_owner_key` / `worker_is_conductor` / `row_belongs_to`，`mw_common.py:1620-1666`；TS 侧 `worker-store.ts` 同构），但**两个消费点仍在用旧规则**，导致三套口径没有真正统一：

1. `conductor.py::reconcile_orphans`（约 `:4308`）重建孤儿行时**不写 `origin` 列** ⇒ 该行被读侧判为 `manual`（`worker_origin` 对缺列一律归一为 `manual`），于是**conductor 自己的行不计入槽位**，面板 `slotsUsed` 少算、`manualRunning` 多算。
2. `conductor._row_belongs_to`（T-12 报为 `:2194` 邻域）仍用旧规则（前缀 OR path），未委派给权威判据。
3. `monitor.ts:615/623` 仍用旧的仅前缀规则，未委派给 TS 侧权威判据。

## 交付物

- `reconcile_orphans` 建行时写入 `origin: conductor`（与 T-12 在 `dispatch.py` 的做法一致）。
- `_row_belongs_to` 改为**一行委派**：`return mw_common.row_belongs_to(row, key)`（删掉本地前缀/path 规则，不留双实现）。
- `monitor.ts` 的归属判定改用已交付的 `workerBelongsToKey` / `workerOwnerKey`（同文件内 import，不改其它行为）。
- `test_autopilot_attribution.py` 追加两条用例：① `reconcile_orphans` 建出的行 `worker_origin == "conductor"`；② `_row_belongs_to` 与 `mw_common.row_belongs_to` 在同组 fixture 上**逐行结果一致**（等价性断言）。

## 契约（不得重定义）

- 权威判据**只允许有一份实现**：Python 在 `mw_common.py`，TS 在 `worker-store.ts`；本卡只做**委派**，不得复制逻辑。
- 缺 `origin` 列的语义**保持** `manual`（T-12 已定；fail 方向已由 T-12 卡与 VC-028 锁定），本卡不改这个方向。
- 不动 `dispatch.py`（T-12 已改）、不动 `mw_common.py` 的判据实现、不动 `gates.py`/`config.py`。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_attribution.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_e2e.py -q`
- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/agent-team-loop.test.ts`

## 非空洞对照（必须附）

- 把 `reconcile_orphans` 的 `origin: conductor` 去掉 ⇒ 新用例①必须红（且能观察到 `slotsUsed` 少算/`manualRunning` 多算的具体数字差）。
- 把 `_row_belongs_to` 换回旧前缀规则 ⇒ 用例②必须红（等价性被打破）。
- 把 `monitor.ts` 的判定换回旧规则 ⇒ TS 侧用例必须红。

## 风险与注意

- **同文件串行**：`conductor.py` 在同一时刻只能有一个写者；开工前确认 T-07 已终态并已提交其改动（`git status` 确认无未完成编辑）。
- `monitor.ts` 刚被 T-09 改过；本卡只碰归属判定点，不得顺手动呈现面。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t16-attribution-delegation/report.md`（含 `[VERIFY]` 原文与输出、等价性用例的逐行对照、三条反向对照的红/绿、残留风险）。
