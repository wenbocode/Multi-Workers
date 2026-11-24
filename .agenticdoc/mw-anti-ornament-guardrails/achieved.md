# mw-anti-ornament-guardrails · 交付记录

## 系统行为变化

- PM 常驻协议（`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` 的 `PARALLEL_PROTOCOL`）与项目协作模板（`AGENTS.md`、`packages/multi-workers/templates/AGENTS.md`）明确区分中间实现卡与竖切收口卡：中间 `coding` 卡只验编译通过、最小正例与破坏性负例（中途取消、失效解绑、身份归属重验、底层不可用禁报 `ready`），防伪留证收归宿主工具，非 `spec_goal` 产品禁止要求自写证据一致性脚本；PM 先复核实际 diff 的生命周期与状态诚实性不变量，通过后只在竖切收口跑一次重型真机留证。
- Worker 运行期（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`）对 `coding` 与 `repair` 角色幂等注入静态 `CODING_INVARIANT_GUARDRAIL`（不改动 `appendKeyGoal` 返回契约，`research`、`review`、`decide_prepare` 角色零变化），硬性约束四项工程底线：禁造非交付证据对账脚本、异步任务未完成禁提前释放句柄、失效路径不解引用旧视图且完整撤销 delegate/track 并复核窗口归属、底层/`raw` 不可用严禁报 `ready`。
- SDD 计划裁剪与 dual 工具链指南（`packages/multi-workers/docs/plan-closure.md`、`packages/multi-workers/docs/dual-toolchain-practice-guide.md`）及 AgenticTask 设计/评审规范（`workflow-system-design`、`workflow-review` 及其 `references/`、`core/`、`claude/skills/`、`.claude/skills/` 镜像）补齐状态充要负例与 C++/UE 生命周期审查维度，移除逐节点 `[FLOW] StepN:` 强制日志埋点检查。

## 验收证据

- AC-001 / AC-002（自验）：`evidence/codex-pm/self/1795535586716347600-biq_21cu/result.json`（`agent-team-loop.test.ts`、`replan-context.test.ts`、`dispatch-card-injection.test.ts`、`mw-key-spec-goal.test.ts`、`mw-spec-goal-command.test.ts` 定向用例全部通过）。
- AC-001 / AC-003（自验）：`evidence/codex-pm/self/1795535613780909300-uvfotgfa/result.json`（`test_init_agents_guide.py` 19 passed）与 `evidence/codex-pm/self/1795535647846712900-_drlc0u_/result.json`（AgenticTask 镜像逐字节一致）。
- AC-004（自验）：`evidence/codex-pm/self/1795535848872808200-68m0wc5s/result.json`（全仓 `npm.cmd run check` 零错误零警告通过）。

## 遗留

- Multi-Workers 与 AgenticTask 仓库的 `git commit` / `push`、用户级全局 `mw` / `pi` 运行版本更新（`mw build --install`），以及向 Gaze、RenderPerformance 等外部工作区同步最新 `AGENTS.md` 与 AgenticTask 技能，按项目规则待用户明确授权后执行。
- 后续在 Gaze 返工卡与 RenderPerformance 竖切试点中跟踪自建证据一致性脚本归零与重型真机留证零作废两项对照指标。
