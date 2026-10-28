# T-08: 修 T-07 首轮真跑暴露的三处结算缺陷（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」）。
- 缺陷来源：T-07 首轮真实 e2e（`workers/cdr-t07b-e2e-budget/`，5 条 claims / 13 次工具调用 / 7 次被 read-scope 拒绝 / `exit=2` / 101s）。三处都是**实数证据**，不是推测：
  1. `carried-from` 精度 0%：`trace.log` 的 `[FLOW] recovery-gap missing=- selfcheck=pending claims=C-02|C-01|C-03`，而 `claimCoverage` 在真实 `report.md` 上只报出 `claim:C-02:verdict-finding` 一条。C-01/C-03 判 `closed` 且引真实源码，仅因其文件 mtime 早于 task.md 就被判"复用上轮裁决"。
  2. 预算少 6 倍：`trace.log` 5 次 `rule=cap-file ... (5/5 calls already allowed)`，worker 5 次读取后彻底饥饿，C-04/C-05 只能 `unverified: budget`。
  3. `fetches=12` 而 `fileCap=5`：计数发生在 guard 之前，把 7 次被拒调用也算进去了。
- 设计依据：`design.md` §4（D-007 预算）、§5（G2）、D-008；本轮新增 D-014（见 `key-decision.md`）。
- 关键锚点（行号以函数名为准，漂移了就按名字重新定位）：
  - `shared/dispatch-card.ts:573-579` `CLAIM_BUDGET`；`:1034` `claimBudgetCaps`；`:985` `claimsGaps`。
  - `worker/worker-mode.ts:1034` `claimSettlementGaps`；`:1076-1100` 的 mtime 块；`:3366-3367` read-scope 的**放行**分支（`allowedCalls++` / `bytesRead +=`）；`:3627` `readCount++`（在 `tool_execution_start`，早于 guard）；`:4097`/`:4338` `traceReads`；`:4443` `claimCounts(..., readCount)`。
  - `worker/read-scope.ts:100` 起的 `normalizeForCompare`（已导出，`shared/write-surface.ts:39` 在用）。
  - `autopilot/dispatch.py:474-490` 常量区、`:711` `claim_budget_caps`。
- `CLAIM_BUDGET.perClaim = 6` 目前是**死代码**（注释写"planning weight"，无人使用）；`5 × 6 = 30 = callCap`，与常数严丝合缝。

## 要求

1. **① `carried-from` 换判据**：`claimSettlementGaps` 删掉 `taskMtimeMs` 参数与 `1076-1100` 的 mtime 比较块，改为 `readTargets?: string[]`（本轮**放行**的读/搜目标，项目相对路径，比较前统一 `normalizeForCompare`/win32 小写）。规则：`closed`/`partial` 行、`CARRIED_FROM_RE` 未命中、且该行 `证据` 里**所有** `path:line` 的文件都不在 `readTargets` 中 → `claim:<id>:carried-from`。`readTargets` 未传或 `claims` 为空 → 返回 `[]`（保持纯函数可测）。
2. **① 接线**：`worker-mode.ts` 新增 `allowedReadTargets: Set<string>`，在 `3366` 的**允许分支**里 `allowedReadTargets.add(normalizeForCompare(projectRoot, rawPath))`（`normalizeForCompare` 从 `./read-scope.ts` 导入）。`finishSuccess` 与 `settleOrSelfCheck` 两处调用点把 `[...allowedReadTargets]` 传进去，并删除 `taskMtimeMs` 的取用（`taskMtimeMs` 若不再被别处使用，一并删除，不要留死变量）。
3. **② 预算补回 `perClaim`**：`claimBudgetCaps` 改为 `fileCap = Math.min(CLAIM_BUDGET.callCap, CLAIM_BUDGET.perClaim * claims.length)`；`byteCap` 公式不变。**不要**改 `Σ预算`（manual×2）的含义，也不要动 `CLAIM_BUDGET_SUM_MAX = 40` 与 `claims:budget-sum` 门禁。
4. **② Python 镜像**：`autopilot/dispatch.py` 的 `claim_budget_caps` 同改，常量放进 `474-490` 常量区（`CLAIM_PER_CLAIM = 6` / `CLAIM_CALL_CAP = 30`），TS/Python 两侧必须同值同式。
5. **③ `fetches` 只计放行**：新增 `allowedReads = 0`，在 `3366` 允许分支 `allowedReads++`；`traceReads`（`:4097`/`:4338` 调用点）、`[CLAIMS]` 行的 `fetches=`、`run.json.claims.fetches`（`:4443`）全部改用 `allowedReads`。**`readCount` 保持原样**（checkpoint 的 `reads:`、重复读检测、看门狗启发式仍用它），不得顺手改口径。
6. **测试（必须真跑）**：
   - `claim-bypass.test.ts`：B-7 两例改写为"引用了本轮没读过的文件 → gap" / "引用本轮读过的文件 → 无 gap"（删除 `staleFiles`/`utimesSync` 夹具，改为传 `readTargets`）；新增一例"被 read-scope 拒绝的调用不计入 `fetches`"。
   - `claim-block.test.ts`：`claimBudgetCaps` 新公式（1 条 → 6/65536、5 条 → 30/327680、8 条 → 30/393216）。
   - `claim-coverage.test.ts`：若断言了 `Σ取数 vs fileCap` 的边界值，按新 fileCap 调整。
   - `test_claim_dispatch.py` / `test_claim_parity.py`：新公式 + 一组新 parity 用例（5 条 → 30、1 条 → 6、0 条 → 0），反恒真验证保持通过。
7. **文档**：`packages/coding-agent/README.md` 的 claims 段落同步三处：`fileCap = min(30, 6×n)`；`grep`/`find`/`ls` 与 `read` **共用**调用配额（只有字节不计）——把上一轮写错的"unrestricted"改掉；`carried-from` 判据是"本轮未读过该文件"；`[CLAIMS] fetches` = 放行的读类调用数。`packages/multi-workers/README.md` 若有同句一并改。
8. 不改任何既有行为：无 claims 块的 worker 路径逐字节不变；`npm run check` 必须只报已知基线红（`mwoc-matrix-t07`、`mwoc-w2`、`mwoc-w3`）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/multi-workers/autopilot/dispatch.py`
- `packages/coding-agent/test/suite/claim-block.test.ts`
- `packages/coding-agent/test/suite/claim-bypass.test.ts`
- `packages/coding-agent/test/suite/claim-coverage.test.ts`
- `packages/multi-workers/test/test_claim_dispatch.py`
- `packages/multi-workers/test/test_claim_parity.py`
- `packages/coding-agent/README.md`
- `packages/multi-workers/README.md`

## 写入禁止面

- `pm/**`（`ui-bridge.ts` 有本窗口未提交改动）、`worker/output-sections.ts`、`worker/output-writer.ts`、`worker/read-scope.ts`、`dist/**`、`.agenticdoc/**`、任何 `CHANGELOG.md`、`packages/ai/**`
- 不得运行 `npm run build`（`dist/` 是 tracked 产物，由 PM 构建）

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/claim-block.test.ts test/suite/claim-bypass.test.ts test/suite/claim-coverage.test.ts test/suite/dispatch-claims-render.test.ts test/suite/dispatch-card-injection.test.ts test/suite/triage-dispatch.test.ts test/suite/dispatch-recovery-terminal.test.ts

cd ../multi-workers
python -m pytest test/test_claim_dispatch.py test/test_claim_parity.py test/test_claim_metrics.py -q

cd ../..
npm run check
```

## 改动历史

- 2026-10-22 创建（T-07 首轮 e2e 三处缺陷，D-014）
- 2026-10-22 PM 修正：卡内 Python 验收路径写错（`test/test_claim_*.py` → 实际是 `packages/multi-workers/test_claim_*.py`），worker 因此被 write-scope 拒绝改 Python 测试；这两支测试由 PM 直接改完（27 passed，新增 `test_claim_budget_caps_formula_parity`）。

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段必须给：① 新旧判据对照（同一行的 `carried-from` 结论为什么变了）、② `claimBudgetCaps` 三组输入输出、③ 一支"被拒调用不计入 fetches"的用例输出、④ 四支测试的通过数、⑤ `npm run check` 的 rc 与诊断清单（基线红要逐条点名）。
