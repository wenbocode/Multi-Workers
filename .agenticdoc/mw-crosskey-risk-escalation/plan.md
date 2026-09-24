# Plan: mw-crosskey-risk-escalation

> Key: mw-crosskey-risk-escalation
> 日期: 2026-09-23
> 上游: `spec.md`（AC-001~004）+ `design.md`（D-101~D-104、VC-001~004）

## 1. 并行性分析

| 单元 | 可并行？ | 共享资源 / 冲突面 | 结论 |
|------|----------|-------------------|------|
| 实现 D-101 过滤放宽（`pm/pm-orchestrator.ts`） | 否（与测试同文件面：改一处逻辑 + 同文件测试用例断言其行为） | `pm-orchestrator.ts` 单文件 + `test/extensions/agent-team-loop.test.ts` 单文件 | **串行 1 个 worker**：逻辑与测试耦合紧（TDD 红→绿），同文件同时只允许一个写者 |
| 新增 3 个 monitor 用例 | 否（同上，与实现同一任务内） | 同上 | 合并为 T-1 |
| 文档（CHANGELOG + `_pitfalls.md` 可选） | 是（与 T-1 无文件冲突） | `packages/coding-agent/CHANGELOG.md`、`.agenticdoc/_pitfalls.md` | 可并行，但内容依赖 T-1 的行为落定 → 由 PM 在 T-1 后直执（T-2） |
| 独立验证（VC 复现 + 变异） | 否（依赖 T-1 完成） | 只读 + 临时脚本 | T-3（波次 2） |
| 构建 / 提交 / 推送 | 否（依赖全部完成） | `dist/**`、git | 收口由 PM 执行 |

**结论**：本 key 是典型的"单点逻辑 + 同文件测试"，并行收益为负（拆成两个 worker 会在同一文件上互相等待），因此采用 **1 个 coding worker + PM 直执文档 + 1 个独立验证 worker** 的三段式。

## 2. 波次

| 波次 | 任务 | 执行者 | 交付 | 依赖 |
|------|------|--------|------|------|
| W1 | T-1 过滤放宽 + 3 个新用例（TDD） | worker `mwcre-t1-crosskey-escalation`（type: coding） | `pm/pm-orchestrator.ts` + `test/extensions/agent-team-loop.test.ts` | — |
| W1 | T-2 CHANGELOG 条目 | PM 直执 | `packages/coding-agent/CHANGELOG.md` | T-1（文案取决于最终行为） |
| W2 | T-3 独立验证（VC-001~004 复现 + 2 变异反例 + sha256） | worker `mwcre-t3-verify`（type: coding） | `evidence/verify-independent-2026-09-23.md` | T-1 |
| 收口 | 质量门禁 + 构建 + 提交 + 推送 | PM | `quality-report.md`、`achieved.md`、`evidence/quality-gate-report-*.md` | T-1/T-2/T-3 |

## 3. 文件所有权（同一时刻唯一写者）

| 文件 | W1 | W2 | PM |
|------|----|----|----|
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | T-1（唯一写者） | 只读（变异窗口内临时改，结束前逐字节复原） | 只读（复核 diff） |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | T-1（唯一写者；只允许**追加** 3 个新用例） | 只读 | 只读 |
| `packages/coding-agent/CHANGELOG.md` | — | — | T-2 |
| `.agenticdoc/mw-crosskey-risk-escalation/**` | 只写 `workers/<task>/` 运行时文件 | 只写 `evidence/verify-independent-2026-09-23.md` | 其余文档 |
| `dist/**` | 禁止 | 禁止 | 收口时 `mw build --install` |

## 4. 验证策略

| AC | VC | 命令 / 方式 | 通过判据 |
|----|----|-------------|----------|
| AC-001 | VC-001 | 新用例（fake timers，跨 key 已派发 + risk=high） | 恰好 1 条 alert、含 owner key、`triggerTurn=true` |
| AC-002 | VC-002 | 新用例（跨 key 未派发，含 `undefined` 与显式空 Set 两形态）+ 既有 "never wake this window" 用例 | 0 条 alert |
| AC-003 | VC-003 | 新用例（跨 key 已派发 + risk=low；高风险第二 tick） | low=0、high=1、dup=0 |
| AC-004 | VC-004 | 既有 2 个 AC-004 用例 + alert 文本包含式断言 | 全绿、文本片段不变 |
| 回归 | — | `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts`；`npm run check` | 0 failed；EXIT=0 |

## 5. 风险与缓解

- R-1：新用例若用真实时钟会 flaky → 强制 `vi.useFakeTimers()` + `finally vi.useRealTimers()`（既有体裁）。
- R-2：改动 `.agenticdoc` 沙箱之外的路径 → 所有夹具走 `mkdtemp()` 沙箱并在用例末清理。
- R-3：误改既有 AC-004 用例 → 任务书明确"只允许追加"，PM 复核 diff 时逐 hunk 确认既有用例零改动。

## 6. 完成定义（DoD）

1. T-1 的 3 个新用例在最终代码上全绿，且既有 2 个 AC-004 用例零改动通过；
2. `npm run check` EXIT=0；
3. T-3 独立验证 0 FAIL，变异反例"改坏即红 + sha256 复原"；
4. `quality-report.md` + `achieved.md` + `evidence/quality-gate-report-*.md` 齐备，`advance_phase done` 通过；
5. `mw build --install` 后 bundle 含新逻辑（异地 owner 文案可 grep），并按约定提交（代码/文档 + dist 两个 commit）并推送。
