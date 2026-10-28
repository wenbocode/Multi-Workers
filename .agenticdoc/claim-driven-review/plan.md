# Plan: claim-driven-review

> 输入：`design.md`（D-001…D-008 已定，D-005/D-006 用户已确认）
> 并行约束：同一文件同一时刻只有一个 worker；写面按文件边界切分（cards 的 `## 写入允许面` 即派发面）
> 验证命令：`npm run check`（全部错误/警告/info 清零）+ 定向下表各测试；实现全绿后 `npm run build`（`dist/` 为 tracked 产物）

## 1. 相位与批次

| 批次 | 任务 | 依赖 | 可并行理由 |
|---|---|---|---|
| B1 | T-01（L1 契约）、T-03（Python 派发）、T-05（度量） | 无 | 三者写面完全不相交 |
| B2 | T-02（PM 派发/渲染）、T-04a（L3 只读面） | T-01 的导出签名 | 写面不相交（`pm/ui-bridge.ts` vs `worker/output-*.ts`） |
| B2.5 | T-04b（worker 接线） | T-04a；且必须等另一窗口的 `ds-w8-decision-type` 先结束（它在改 `worker/worker-mode.ts`） | 排他：同一文件只能一个写者 |
| B3 | T-06（平价锁 + 文档 + CHANGELOG） | T-01、T-03 | 只写测试与文档 |
| B4 | T-07（端到端验收：20-claim 卡 → 4×5 + merge，advisory 与 enforce 各一轮） | B1–B3 | PM 直执（需真实派发与回读） |

> 并发冲突（2026-10-21 17:25 实测）：另一窗口的 `ds-w8-decision-type` 正在改写 `worker/worker-mode.ts`、`pm/triage-client.ts`、`pm/pm-orchestrator.ts`、`pm/decision-tool.ts`。因此 T-02（`pm/ui-bridge.ts`）与 T-04b 暂缓，T-04 已拆为 T-04a（安全）+ T-04b（等窗口）。

## 2. 任务拆分

### T-01 L1 契约层（`shared/dispatch-card.ts`）

- 导出：`CLAIM_TYPES`、`UNVERIFIED_REASONS`、`CLAIM_GATE_DEFAULT`、`CLAIM_BUDGET`、`parseClaimsBlock()`、`claimsGaps()`、`claimBudgetCaps()`。
- 判据：`claimsGaps` 返回 `claim:<id>:<要素名>` / `claims:<rule>` 形态；`manual` 记 2 且条数 ≤ `min(4, ceil(n/3))`；`cmd` 类 `定位` 必须是 `evidence/claims/*#<id>`；同义反复相似度 <0.90；fence 内表格不计；`cmd: TBD(...)` 放行。
- 测试：`test/suite/claim-block.test.ts`（解析容忍 + 七种缺失形态）。
- 验收：`node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-block.test.ts` → 0 fail；`npm run check` 该文件 0 诊断。

### T-02 PM 派发层（`pm/ui-bridge.ts`）

- `readDispatchCard` 的 `missing` 聚合追加 `claimsGaps`；新拒绝码 `dispatch-claims`；`DispatchCardGate` 扩 `{claims, caps}`。
- `writeDispatchTaskMd` 新增 `mergeReadScope`（写 `read_scope:` / `l2_read_file_cap:` / `l2_read_byte_cap:`），并把 claims 块原样注入 `mw-dispatch-card: v1` 标记区；两个调用点透传 caps。
- 灰度：`MW_CLAIM_GATE=enforce` 才进 `missing`；advisory 仅当卡含 claims 时向回执追加一行。
- 测试：`test/suite/dispatch-claims-render.test.ts` + `dispatch-card-injection.test.ts` 追加 7 条零副作用用例。
- 验收：新测试 0 fail；`triage-dispatch.test.ts` 与 `dispatch-card-injection.test.ts` 既有断言不改而全绿。

### T-03 Python 派发层（`autopilot/dispatch.py`）

- `dispatch_card`（569-601）返回 `claims`；`_read_scope_caps`（224-270）接 claims，值 `min(30, Σ预算)` / `min(393216, 65536×n)`，项目层显式值优先；`1492` 下移到 `1495` 之后；`synthesized_card` 路径退化不写 caps 行。
- 测试：`test_claim_dispatch.py`（caps 值、行序、synthesized 退化、`requires_read_scope` 不受影响）。
- 验收：`python -m pytest test_claim_dispatch.py -q` → 0 fail；既有 `test_autopilot_readcap_injection.py` 全绿（VC-007/VC-008 字节不变）。

### T-04 L3 结算层（已拆：T-04a + T-04b）

#### T-04a 只读面（`worker/output-sections.ts`、`worker/output-writer.ts`）

- `parseVerdictTable` / `claimCoverage`（11 类判据）；`TerminalGaps.claimGaps`（可选，默认 `[]`）+ `ok` 折叠；`## Questions` 首行点名。
- 验收：`test/suite/claim-coverage.test.ts` 与 `dispatch-recovery-terminal.test.ts` 均 0 fail。

#### T-04b worker 接线（`worker/worker-mode.ts`）

- `TaskMeta.claims` 解析、`readTerminalGaps` 透传、self-check 共用 `selfCheckSent`、独立 `[CLAIMS]` 行、AC-008 结算侧三条。
- 前置：等 `ds-w8-decision-type` 结束（文件排他）。

### T-05 度量层（`autopilot/usage.py`、`autopilot/status-model.ts`）

- 解析 `[CLAIMS]` 行与 `runs.jsonl` 的 `session_id`；`tokens_per_closed_claim`（不可归因 → `n/a`）；`run.json` 加 `claims` 子对象；`KeyRounds` 旁加 claims 视图。
- 测试：`test_claim_metrics.py`（解析、`n/a` 分支、缺行不推断）。
- 验收：`python -m pytest test_claim_metrics.py -q` → 0 fail；`status-model` 面板在 110 列内不截断既有字段。

### T-06 平价锁 + 文档

- 新增 `test_claim_parity.py`：`CLAIM_TYPES` / `UNVERIFIED_REASONS` / `CLAIM_GATE_DEFAULT` / `CLAIM_BUDGET` TS↔Python 逐字。
- 更新 `packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md` 的 `[Unreleased]`；README 派发卡小节加 claims 块与 `cmd` 预执行规则。
- 验收：`python -m pytest test_claim_parity.py -q` → 0 fail；`npm run check` exit 0。

### T-07 端到端验收（PM 直执）

- 构造一张 20-claim 卡 → 拆 4 个取证单元 + 1 个 merge；advisory 与 `MW_CLAIM_GATE=enforce` 各跑一轮。
- 判据：全部 `exit=0`；merge 产物含 20 行裁决；`[CLAIMS]` 行五元组齐全；enforce 下故意缺一行 → `exit 2` 且 `## Questions` 首行点名该 claim。

## 3. 风险与止损

- `dispatch.py:1492` 的顺序改错会让 conductor 的 caps 永远取上一版卡的预算 → T-03 必须有一条"同一次派发内 caps 随卡变"的用例。
- `worker-mode.ts` 的 `TaskMeta` 改动会影响 `parseTaskMd` 的既有形状断言（`autopilot-read-scope.test.ts:323-383`）→ 新增字段必须可选、缺省不变。
- `dist/` 是 tracked 产物：T-01…T-06 合并后必须 `npm run build`，否则 P3 灰度试点跑的是旧 bundle。
- 全量回归红线（任一红即停）：T-17 平价锁、`test_mwoc_s2_sections.py`、`autopilot-read-scope.test.ts:601-625`（零拦截）、`dispatch-card-injection.test.ts:344-483`。
