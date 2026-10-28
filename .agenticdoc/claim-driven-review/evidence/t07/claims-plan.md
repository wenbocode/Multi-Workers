# T-07 端到端验收：20 条断言集（4 张卡 × 5 条）

- Key: claim-driven-review
- 用途：`plan.md` B4 / T-07 的夹具来源。4 张 review 卡各 5 条断言（`perClaim=6`、`callCap=30` 的实测标定上限就是 5 条/worker），merge 后合成 20 行裁决表。
- 审查对象：本 key 自己刚落的代码（可自证伪、无需外部依赖）。这是刻意的：断言必须能被"读一个文件 + 数一个符号"判定，否则测的是模型发挥而不是门禁。
- 类型分布对齐 RQ-3 实测（21% cmd / 27% grep / 28% struct / 25% manual），但 **manual 只放 4 条**（`min(4, ceil(20/3)) = 4` 的卡面上限）。

## 卡侧七列格式（卡内 `<!-- mw-claims: v1 -->` 块）

`| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |`

- `定位`：`path:line` 或 `path:line-line`（相对项目根），`cmd` 类必须为 `evidence/claims/<file>#<claim-id>`。
- `判据`：`grep:<pattern>` / `shape:<what>` / `cmd:<verb…>` / `manual:<who>`；**允许 `cmd: TBD(<name>)`**（RQ-3：21 个 cmd 命题里 11 个卡内无可执行串）。
- `预算`：整数（取数次数）；`manual` 类固定记 2。

## A 卡（grep 类，5 条）：常量与导出面

| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
|---|---|---|---|---|---|---|
| C-A1 | grep | `CLAIM_BUDGET` 的五个键在 TS 侧齐备 | 缺任一键或多出键 | `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:563-570` | `grep:perClaim\|callCap\|hardCap\|claimByteCap\|byteCapMax` | 2 |
| C-A2 | grep | 默认门禁是 advisory 而非 enforce | 默认值为 enforce | `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:555` | `grep:CLAIM_GATE_DEFAULT = "advisory"` | 2 |
| C-A3 | grep | Python 侧有同义的 claims 解析入口 | 无 `parse_claims_block` | `packages/multi-workers/autopilot/dispatch.py:651` | `grep:def parse_claims_block` | 2 |
| C-A4 | grep | caps 计算在 `dispatch_card(...)` 之后取当次卡 | 仍用上一版卡的 claims | `packages/multi-workers/autopilot/dispatch.py:2077-2087` | `grep:card_backed` | 3 |
| C-A5 | grep | `MW_CLAIM_GATE` 在 Python 侧只读一次 | 出现 2 处以上读取点 | `packages/multi-workers/autopilot/dispatch.py:732-749` | `grep:MW_CLAIM_GATE` | 2 |

## B 卡（struct 类，5 条）：结算层形状

| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
|---|---|---|---|---|---|---|
| C-B1 | struct | `TerminalGaps` 增加的是可选字段，既有构造点无需改 | `claimGaps` 为必填 | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:82-92` | `shape:optional field` | 2 |
| C-B2 | struct | `ok` 折叠包含 claims 判据 | `ok` 只含既有三项 | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:449-455` | `shape:boolean conjunction` | 2 |
| C-B3 | struct | `claimCoverage` 输出的每个 token 都点名具体 claim id | 存在无 id 的 claim 级 token | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:625` | `shape:token format` | 3 |
| C-B4 | struct | 裁决表七列与卡侧七列不混用 | 用同一套列名 | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:259-290` | `shape:column names` | 2 |
| C-B5 | struct | `## Questions` 首行在无缺口时逐字不变 | 无缺口时也追加文案 | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts:558-560` | `shape:no-op when empty` | 2 |

## C 卡（cmd 类，5 条）：PM 预执行证据

> `cmd` 类断言的执行权在 PM（D-005，review 角色无 bash）。派发前 PM 执行下列命令，把输出落到 `evidence/claims/<file>`，卡的 `定位` 列指该文件。

| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
|---|---|---|---|---|---|---|
| C-C1 | cmd | `claim-block` 与 `claim-coverage` 两组测试全绿 | 任一 fail | `evidence/claims/t07-tests.txt#C-C1` | `cmd: TBD(vitest)` | 1 |
| C-C2 | cmd | `test_claim_dispatch.py` 9 条全绿 | 任一 fail | `evidence/claims/t07-tests.txt#C-C2` | `cmd: TBD(pytest)` | 1 |
| C-C3 | cmd | `test_claim_parity.py` 6 条全绿（TS↔PY 零漂移） | 任一 fail | `evidence/claims/t07-tests.txt#C-C3` | `cmd: TBD(pytest)` | 1 |
| C-C4 | cmd | `test_claim_metrics.py` 11 条全绿 | 任一 fail | `evidence/claims/t07-tests.txt#C-C4` | `cmd: TBD(pytest)` | 1 |
| C-C5 | cmd | `tsgo --noEmit` 退出码为 0 | 非 0 | `evidence/claims/t07-tests.txt#C-C5` | `cmd: TBD(tsgo)` | 1 |

## D 卡（manual + 跨层，5 条）：需要人判的部分

| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
|---|---|---|---|---|---|---|
| C-D1 | manual | 两份 README 的 claims 小节与实现一致 | 文档描述与代码行为不符 | `packages/coding-agent/README.md:459-518` | `manual:PM` | 2 |
| C-D2 | manual | CHANGELOG 只落在 `## [Unreleased]` | 触碰已发布版本段 | `packages/coding-agent/CHANGELOG.md:89` | `manual:PM` | 2 |
| C-D3 | grep | 平价锁在两侧读取点都存在 | 只有一侧有读取表达式 | `packages/multi-workers/test_claim_parity.py:1-281` | `grep:MW_CLAIM_GATE` | 3 |
| C-D4 | grep | `[CLAIMS]` 是独立 trace 行，未扩 `[END]` | `[END]` 正则被改 | `packages/coding-agent/src/extensions/agent-team-loop/shared/heartbeat.ts:93` | `grep:\[END\]` | 2 |
| C-D5 | manual | `fetches` 口径与 `allowedCalls` 的差异已写明 | 两者被当成等价 | `packages/multi-workers/README.md:480-504` | `manual:PM` | 2 |

## 预算与度量预期

- 每卡 `Σ预算 = 12`（`fileCap = min(30, 12) = 12`，`byteCap = min(393216, 65536×5) = 327680`）。
- manual 双倍记账：D 卡 3 条 manual → `fileCap = min(30, 2+3+2×3) = 11`。
- 20 条断言、4 个 worker：若 merge 后 `unverified ≤ 40%` 且 `closed ≥ 12`，则 `tokens_per_closed_claim` 有意义；实际值由 `usage.py::claims_metrics` 从 session join 算出（RQ-1：仅少数 run 可精确 join，故预期会出现 `n/a`，这也是被验收的行为之一）。

## 刻意不放进夹具的东西

- 任何需要"读 20 个文件才能判"的断言 —— 那正是要消灭的成本形态。
- 任何自证路径（`output.md` / `report*.md` / `task.md`）作为唯一证据 —— B-1 会拒。
- `struct` 父行的子行（`C-B1.2` 之类）—— T-04a 明确了子行只允许挂在 struct 父行下，本次先不铺开，避免把"未实现"当成"通过"。
