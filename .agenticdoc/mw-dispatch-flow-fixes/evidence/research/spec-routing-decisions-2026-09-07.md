# Research: 路由语义决策（spec）

## 决策问题

§1.1 目标③、§2.4 集成依赖、AC-006/007/009：路由默认值语义（凭证 fallback vs 全局默认 pi）、显式 cli 的缺凭证行为、与 mw-dispatch-reliability 的检测复用边界。

## 调研方法与出处

- 代码：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:282-287`（pickWorkerRoute）、`:311-360`（dispatchNewTasks 扫描 + docs gate）、`pm/ui-bridge.ts:427-545`（dispatch_worker 工具，显式 cli 参数默认 "pi"）
- 邻 key 状态：`.agenticdoc/mw-dispatch-reliability/design.md`（D-001/D-002/D-005）、`pm-state.md`（T-01..T-15 全部完成）、`packages/multi-workers/mw_common.py`（route_precheck / resolve_credential 已交付，30505 bytes）
- 测试：`packages/coding-agent/test/extensions/agent-team-loop.test.ts` dispatchNewTasks 扫描用例（全部 `type: coding`，无 review→claude 映射断言）
- 用户决策：2026-09-07 需求澄清对话（本窗口）

## 发现

1. **两条派发路径都会产生 `type: review` 任务**：① dispatch_worker 工具显式 cli 参数（默认 pi，cli=claude 时写 `type: review` 且队列行 cli=claude）；② dispatchNewTasks 扫描路径 pickWorkerRoute 内容路由（`type: review|research` → claude 硬编码，不感知凭证）
2. **mw-dispatch-reliability 已交付 D-001 隔离语义**：spawn 时缺凭证 → 该任务 per-task failed + 原因写 worker.log，服务与同批任务存活（L1/L2 证据：evidence/runs/l2-claude-isolation-rerun.txt）
3. **可用性检测已单一来源化**：mw_common.route_precheck / resolve_credential 被 serve 启动预检与 doctor 共用
4. **既有 vitest 不依赖 review→claude 映射**：扫描用例全用 type: coding，移除映射无测试破坏
5. ga-spec-review-1 的实际卡点：pickWorkerRoute 把 `type: review` 硬路由 claude + 环境无 ANTHROPIC_API_KEY/AUTH_TOKEN → spawn 失败，人工改派 pi/timi 才完成

## 结论 → 决策映射

- 用户决策「全局默认 pi」（弃凭证 fallback 方案）→ AC-006 改写（默认路由 pi/timi，与凭证无关）、AC-007 改写（显式 cli=claude 才走 claude，type 字段不再触发）、AC-008 第三项更新（默认 pi 无人工干预）
- 用户决策「显式 claude 缺凭证不降级」→ AC-009 新增（沿用 D-001 隔离语义作回归保护）；`type: codex → codex` 内容路由保留（显式类型语义，同理由不降级）→ §1.4 范围说明
- 用户决策「认可复用边界表述」→ §2.4：检测唯一来源 mw_common、本 key 不写第二套；全局默认方案下默认路由是静态决策，无运行时可用性判定链
- 发现 4 → §4 风险：移除映射需新增默认 pi 正向断言（既有测试无覆盖）
