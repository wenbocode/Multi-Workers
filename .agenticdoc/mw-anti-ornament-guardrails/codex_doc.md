# mw-anti-ornament-guardrails · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-anti-ornament-guardrails
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

收敛 Multi-Workers 与 AgenticTask 在中间开发卡片上的激励偏差，剥离非产品需求的自定义证据一致性对账脚本，把破坏性负例与源码生命周期及状态诚实性复核前移到重型真机留证之前，对齐 `.agenticdoc/goal.md` 的高效并行协作目标。完成后，PM 协议、项目协作模板、`coding`/`repair` Worker 运行期提示及设计/评审工作流统一约束异步句柄生命周期、失效解绑、身份重验与底层不可用时禁报 `ready`，且不新增表单或终态硬门禁。

## 范围

- 控制工作区与目标工作区均为 `E:/gitlite/Multi-Workers`（含 `.agents/skills/agentic-task` 与本地 `.claude/skills` 镜像）。
- 允许修改：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`packages/coding-agent/test/extensions/agent-team-loop.test.ts`、`AGENTS.md`、`packages/multi-workers/templates/AGENTS.md`、`packages/multi-workers/docs/plan-closure.md`、`packages/multi-workers/docs/dual-toolchain-practice-guide.md`、`packages/multi-workers/test_init_agents_guide.py`，以及 AgenticTask 的 `workflow-system-design` 与 `workflow-review` 规范及镜像。
- 边界：不改 `appendKeyGoal`、`plan_closure.py`、`scope_review.py` 的机器接口与 schema；不未经明确授权执行 `git commit` / `push` 或覆盖全局 `mw` / `pi` 运行包。

## 验收标准

- AC-001: `PARALLEL_PROTOCOL`、`AGENTS.md` 与 `packages/multi-workers/templates/AGENTS.md` 明确区分中间实现卡（编译与最小正反例，含取消、失效解绑、身份重验、底层不可用非 ready 负例）与竖切收口真机留证，明确防伪归宿主工具并前移源码不变量复核；既有协议与模板测试及新增断言全部通过。
- AC-002: `worker-mode.ts` 对 `coding` 与 `repair` 角色幂等注入静态 `CODING_INVARIANT_GUARDRAIL`（不超过 360 字符），对 `research`、`review`、`decide_prepare` 不注入，且保持 `appendKeyGoal` 返回契约不变；相关 Vitest 测试全部通过。
- AC-003: `packages/multi-workers/docs/plan-closure.md`、`packages/multi-workers/docs/dual-toolchain-practice-guide.md` 及 AgenticTask 的 `workflow-system-design`、`workflow-review`（含全部镜像副本）补齐状态充要负例与 C++/UE 生命周期审查维度，移除逐节点 `[FLOW] StepN:` 强制日志检查，各镜像副本逐字节一致。
- AC-004: 定向 Vitest / Pytest 测试与代码静态检查全部零错误通过，验收证据与最终源码快照一致。

## 关键决策

- 保持零新增表单、零新增 JSON 字段、零新增 settle 红判，防止反粉饰规则退化为新的填表仪式。
- `CODING_INVARIANT_GUARDRAIL` 独立挂载在 `worker-mode.ts` 的 `before_agent_start` 钩子，不改动 `shared/key-goal.ts::appendKeyGoal`，避免破坏跨套件冻结契约（P-018）。
- 本次只落工作区源码、本地技能镜像与验证证据，全局包安装与 git 提交留待用户明确指令。

## 执行与验收

- AC-001 / AC-002（自验通过）：`evidence/codex-pm/self/1795535586716347600-biq_21cu/result.json`（`PARALLEL_PROTOCOL`、`CODING_INVARIANT_GUARDRAIL`、`replan-context`、`dispatch-card-injection`、`mw-key-spec-goal`、`mw-spec-goal-command` 定向 Vitest 全部通过）。
- AC-001 / AC-003（自验通过）：`evidence/codex-pm/self/1795535613780909300-uvfotgfa/result.json`（`packages/multi-workers/test_init_agents_guide.py` 19/19 通过）与 `evidence/codex-pm/self/1795535647846712900-_drlc0u_/result.json`（AgenticTask `workflow-system-design`、`workflow-review` 全部镜像逐字节一致，无残留 `[FLOW] Step` 强制埋点条款）。
- AC-004（自验通过）：`evidence/codex-pm/self/1795535848872808200-68m0wc5s/result.json`（标准管道包装下根目录 `npm.cmd run check` 退出码 0；此前裸文件句柄重定向触发 Windows 沙箱下 Biome 退出期 `0xC0000005`，源码快照未变）。

## 接续须知

- 使用 `python packages/multi-workers/codex_pm.py status --project . --key mw-anti-ornament-guardrails` 查看结案状态；结案摘要与遗留去向见 `achieved.md`。待用户明确确认后，再执行 `mw build --install` 更新全局运行版本、提交 Multi-Workers 与 AgenticTask 仓库改动并同步至 Gaze / RenderPerformance 工作区。
