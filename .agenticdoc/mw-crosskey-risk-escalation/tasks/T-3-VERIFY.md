# T-3 独立验证（VC-001~004 + 变异反例）

- 波次: W2
- 执行者: worker `mwcre-t3-verify`（type: coding）
- 依赖: T-1（实现已落盘、PM 复核通过后派发）
- 上游: `spec.md` AC-001~004、`design.md` §7 VC 表、`tasks/T-1-CROSSKEY-ESCALATION.md`

## 1. 目标

不复用 T-1 的断言结论，**自己构造夹具与探针**复现 VC-001~004，并对 2 处关键判据做变异反例（改坏即红 + 复原后 sha256 逐字节相同）。

## 2. 交付物

- `.agenticdoc/mw-crosskey-risk-escalation/evidence/verify-independent-2026-09-23.md`
- 本任务的 `output.md`（含 `[VERIFY]` 行与命令原始输出片段）

## 3. VC 复现要求

| VC | 独立复现要点 |
|----|--------------|
| VC-001 | 自建临时 `.agenticdoc` 根 + `_workers.parallel`（或 `WorkerStore`）running 行 + `trace.log` `[CHECKPOINT] … risk=high`；watch 一个**不同于 owner** 的 key，`dispatchedTaskKeys` 含该 task；驱动真实 `startWorkerPollLoop`（fake timers 或自建 pi 桩），断言 1 条 alert、含 owner key、`triggerTurn=true` |
| VC-002 | 同一夹具分别以 `dispatchedTaskKeys: undefined` 与 `new Set()` 运行 → 0 条；并**独立重跑**既有 "diverging workers owned by other keys never wake this window" 用例 |
| VC-003 | 跨 key 已派发的两个 task（low / high）→ low 0 条、high 恰 1 条、第二 tick 不重复 |
| VC-004 | 既有 2 个 AC-004 用例通过 + alert 文本包含式断言不变。**必须给出机械证据证明 watched key 路径文本逐字节不变**：用 `git show HEAD:…pm-orchestrator.ts` 取改造前模板，把两者在同一夹具下求值并逐字节比较（T-1 曾用一次性临时用例做过，该临时文件已删除且不在套件里——你必须重做一遍并把比较脚本与输出留在报告里，不得只凭"既有用例全绿"推得） |

## 4. 变异反例（必须各做一次，结束时逐字节复原并给 sha256）

| 变异 | 目标 | 期望 |
|------|------|------|
| M-1 | 把过滤条件改回 `ownerKey !== watch.key → continue`（去掉 `owned` 支） | VC-001 红（异地高风险不再投递） |
| M-2 | 去掉 `owned` 与 owner 过滤（全局广播） | VC-002 红（别键/未派发也投递）与既有反例用例红 |
| M-3 | 把 `?? false` 改成 `?? true`（`dispatchedTaskKeys` 未定义时视作已派发） | VC-002 红（`undefined` 形态下误投递） |

每个变异的证据：`H0`（sha256）→ 变异 → 探针/用例红 → 从备份整文件复原 → `H1 == H0` → 复绿。

## 5. 回归

1. `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts` → 0 failed（报告计数）
2. `cd H:/git/Multi-Workers && npm run check` → EXIT=0
3. `git status --short` 起止逐行相同（证明零残留）

## 6. 范围

- 只写 `evidence/verify-independent-2026-09-23.md`；临时脚本放系统临时目录（`os.tmpdir()`）。
- 不 commit、不跑 `mw build`、不改 `dist/**`、不改 Python、不改既有测试文件。
