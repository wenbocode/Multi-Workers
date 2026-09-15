# Task 009: goal check + serveStaleness 双根 fixture

- Stage: S4
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，4/4 + 关联 160/161 + check exit=0，证据 evidence/runs/009-goal-serve-staleness-dual.md）
- ac_refs: [AC-008, AC-009]
- vc_refs: [VC-014, VC-016]
- pattern_refs: []
- deps: [005]
- 预估: ~1h

## 交付物

- 现有 goal check 用例（`packages/coding-agent/test/extensions/agent-team-loop.test.ts` :379/:417/:573）与 serveStaleness 用例（:635）在双根 fixture 下参数化运行——断言语义不变，仅 fixture 化
- [GOAL_CHECK] trace 行在双根下落控制根（验证 goal mtime 追踪不受 cwd=game 影响）

## AC 摘录（spec.md §3）

- AC-008: goal.md 读取与 [GOAL_CHECK] 追踪在双根下行为不变（goal.md 在控制工作区）
- AC-009（部分）: staleness 检测以控制工作区源码 mtime 为基准

## 验证方式（VC 断言）

- VC-014: 双根 fixture 下 goal check 用例通过 + trace.log 含 [GOAL_CHECK] 行 → `[VERIFY] VC-014: goal-check-pass=true trace-has-goalcheck=true`
- VC-016: 控制工作区 mw 源码 mtime 晚于 serve.meta started_at → stale=true → `[VERIFY] VC-016: staleness-detect=true`
- 证据落盘: `evidence/runs/009-goal-serve-staleness-dual.md`

## 依赖与阻塞

- 依赖 005（双根 worker 执行链）。
