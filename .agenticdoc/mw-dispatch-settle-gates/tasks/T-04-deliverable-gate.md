# T-04 — AC-006：结算期三级通道产物判据 + 折 `exitCode` + `no-product` 告警

- key: `mw-dispatch-settle-gates`｜AC: **AC-006**｜VC: **VC-025…VC-029**｜波次 **2**｜链 2（依赖 T-03 对 `worker-mode.ts` 的编辑）
- 角色: coding
- **唯一允许改的路径**：① 新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/deliverable-evidence.ts`；② `worker/worker-mode.ts`（`finishSuccess`/`markOutcome`/`recordEnd` 三处）；③ `pm/pm-orchestrator.ts`（**仅**告警域：`DispatchAlarmKind` 值域、`describeDispatchAlarm`、扫描处调用 `recordDispatchAlarm`）；④ 新建 `packages/coding-agent/test/suite/mwds-t04-deliverable.test.ts`；⑤ 自身目录 `report.md`
- 上游：`plan.md §4` 契约 **C5/C6**；`design.md` DD-05/DD-07/§4.4；证据 `evidence/research/design-settle-read-20261010.md`

## 必须实现
1. **新模块 `shared/deliverable-evidence.ts`（C5）**：纯函数
   `hasDeliverableEvidence(taskDir, outputText): {delivered: boolean, channel: "report"|"output"|"artifact"|"none", detail: string}`
   三级通道：① `report.md`/`report-<slug>.md` 非空；② 否则 `output.md` 非空且**所有**块非占位（占位符集见 C7/新模块口径，15 个）且命中任一：行首或内联机器行（如 `[VERIFY]`/`VERDICT=`/`TASKS=`/`[CHECKPOINT]`）、`run.json.artifacts` 含 `output.md` 以外的产物、正文引用的 `evidence/**.md` 实存；③ 否则 `{delivered:false, channel:"none"}`。
   **不得**复用或修改 `hasProductEvidence()`（`pm-orchestrator.ts:487-492`，语义 = "跑过"）。
2. **结算折码（worker-mode.ts）**：在 `finishSuccess()`（约 `:1350`）内、`writeOutputGuarded(...)`（约 `:1354`）之前判定，结果折进 `exitCode`：`delivered ? 0 : 2`；`markOutcome`（约 `:786`）加 `2 → needs-clarification`；`recordEnd`（约 `:1075`）放宽为 `0|1|2`。`run.json.status` 与 `## Questions` 语义保持自洽（NC 时 `[END] exit=2`）。
3. **告警（C6）**：`DispatchAlarmKind` 值域（约 `:387-397`）加 `"no-product"`；`describeDispatchAlarm`（约 `:409-435`）加 case；PM 扫描处（`agent_settled` 路径）在观测到"刚结算的 run 为 `needs-clarification` 且三级通道 `none`"时调 `recordDispatchAlarm(...)`（约 `:439`），**必须用 `meta.trueAgenticdocRoot`**（不是 `<key>/workers` 那个 `agenticdocRoot`）。
4. **并存约束**：`hasProductEvidence` 的实现与调用点逐字不动；补一条**判别性**用例：任务目录只有 `trace.log`（无 report/无机器行）⇒ 旧守卫仍必须拒绝扫描。

## 反向用例（必须真跑）
- **(a) 语料回放（硬判据）**：对全部 30 个真实 worker 目录跑三级通道 ⇒ `delivered=28 / none=2（正确 NC：`mwg-qg-review-20261010` 空交付、`mwg-t08b-g2-surfaces` 硬杀）/ 假阳性 0`。
- (b) `report.md` 存在但 0 字节 ⇒ 不得算交付（落到下一通道）。
- (c) 只有占位符 `output.md` ⇒ `none`。
- (d) 只有机器行 `output.md`（无 report）⇒ `output`（合规 4 例形态）。
- (e) `delivered=false` ⇒ `exitCode=2` + `run.json.status=needs-clarification` + 一条 `no-product` 告警（断言 `auto-decisions.jsonl` 新行含 `kind":"no-product"`）。
- (f) `delivered=true` ⇒ `exitCode=0`（不得回归成 2）。
- (g) 判别性：`trace.log`-only 目录 ⇒ `hasProductEvidence` 仍拒绝扫描。

## 对照协议（`plan.md §5`）
A 摘除三级通道判定（恒 `delivered=true`）⇒ (a)(e) 转红；B 反转默认（恒 NC）⇒ (f)(a) 转红；C 把 `hasProductEvidence` 收窄为"有 report" ⇒ (g) 转红（证明并存必要性）。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-025: corpus_dirs=30 delivered=28 none=2 false_positives=0
[VERIFY] VC-026: delivered_exit=0 undelivered_exit=2
[VERIFY] VC-027: markOutcome_2=needs-clarification recordEnd_range=0|1|2
[VERIFY] VC-028: alarm_kind=no-product root=trueAgenticdocRoot
[VERIFY] VC-029: hasProductEvidence_unchanged=true trace_only_still_refuses=true
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t04-deliverable.test.ts`

## 禁止
不改 `output-writer.ts`（T-06 负责段落）；不改 `worker-store.ts`/`run-store.ts`（只读引用）；不改 `shared/output-sections.ts`（T-05 负责）；不改大测试文件 `test/extensions/agent-team-loop.test.ts`；不 build；不 commit；不跑全量套件 / `npm run check`。
