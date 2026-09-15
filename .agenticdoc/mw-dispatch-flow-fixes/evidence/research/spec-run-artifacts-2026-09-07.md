# Research: ga-spec-review-1 运行事实验证（spec）

## 决策问题

三个缺陷的观测证据与代码定位入口（支撑本 key 全部 AC）。

## 调研方法与出处

- 运行样本：`.agenticdoc/agent-team-loop/workers/ga-spec-review-1/`（task.md / trace.log / worker.log / output.md）
- 队列行：`.agenticdoc/_workers.parallel` 末行 ga-spec-review-1
- 日志：`.mw/mw.log`（route 可用性预检）、`.mw/launcher.log`（claude spawn 失败记录）
- 代码入口：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（dispatchNewTasks / startWorkerPollLoop / restoreWatch）、`pm/ui-bridge.ts`（registerWorkerTools，dispatch_worker 工具注册处）、`worker/worker-mode.ts`、`worker/output-writer.ts`（trace 写入）

## 发现

1. **owner key 错位**：派发时 `_index.md` active = goal-autopilot，但 task.md 落在 `agent-team-loop/workers/ga-spec-review-1/`。dispatch_worker 工具声明"Default: the active key"，实际解析结果与窗口 watch 状态一致（本窗口 session 恢复的 watch 指向 agent-team-loop）。根因待定位：registerWorkerTools 的 key 解析与 watch 状态/active 指针的关系
2. **无进度心跳**：trace.log 在 11:20:44Z → 11:27:16Z 之间约 7 分钟无条目（长 LLM 生成期），期间无任何活性信号；唯一保护是 30 分钟看门狗。trace 条目目前仅在 tool_call 时由 worker 写入
3. **路由降级缺失**：mw.log 显示 `route claude: missing (env ANTHROPIC_API_KEY unset)` / `route claude-cli: missing (env ANTHROPIC_AUTH_TOKEN unset)`；launcher.log 有 9+ 次 claude spawn failed。本次 review 任务靠人工选择 pi/timi 才成功——pickWorkerRoute 按 `type: review → claude` 硬路由，不感知路由可用性

## 结论 → 决策映射

- 发现 1 → AC-001/002（owner = 窗口激活 key；watch 与激活同步）
- 发现 2 → AC-003~005（结构化进度条目 + 活性判定 + additive）
- 发现 3 → AC-006/007（无凭证环境降级 pi；有凭证环境保留原路由语义）
