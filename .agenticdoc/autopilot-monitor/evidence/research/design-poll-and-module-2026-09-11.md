# Research: 轮询归属、模块落点与数据 schema（design）

## 决策问题

§1 架构选型 D-001（独立 interval vs 复用 startWorkerPollLoop）、D-002（模块落点）、D-004（gates 解析方式）：现有代码结构与 schema 是否支持低耦合实现。

## 调研方法与出处

- 读 `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` L488-560（startWorkerPollLoop：`POLL_INTERVAL_MS = 4000`，L514 `if (watch.key)` 才渲染 watch widget）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` L399-430（renderWatchLines：key-scoped 过滤 `ownerKeyOf(e, agenticdocRoot) === key`；WATCH_LINE_MAX=110 截断风格）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts` L7-46（WorkerEntry：taskKey/status/dispatchedAt ISO 字符串）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts` L71-95（registerAutopilotCommands(pi, projectDir, deps)：命令族 + deps 注入模式；ensureMwRunning seam 先例）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`（写路径 answer 流程；frontmatter 含 id:/kind:/status: 行）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（getMwStatus/serveStaleness/readServeMeta 公开可复用）

## 发现

1. **watch 轮询是 key-scoped**：L514 `if (watch.key)` 才调 applyWatchWidget——monitor 是 system-scoped（serve/conductor/gates 与 watched key 无关），复用该循环需在 pm-orchestrator 引入 monitor 状态共享（console.ts 设 → pm-orchestrator 读），且 watch.key 为空时 monitor 仍须独立工作。
2. **console.ts 已有成熟的 deps 注入 seam**（ensureMwRunning 测试缝，autopilot-console.test.ts 的 fakeConsolePi/fakeCmdCtx 直接可用），monitor 命令照搬该模式即可测。
3. **WorkerEntry.dispatchedAt 是 ISO 字符串**，elapsed = now - Date.parse(dispatchedAt)，分钟向上取整即可（AC-003）。
4. **gate frontmatter 是行式 key: value**（id:/kind:/stage:/status:），轻量行扫描足够（个位数文件），无需 YAML 库；gate-writer 的解析绑在写路径（answer 流程），不复用。
5. **serve uptime**：serve.meta.started_at_ms（epoch ms）；无 meta 时 serveStaleness 的回退源是 mw.pid 的 mtime——同样可用于 uptime 近似。
6. **watch widget 行宽 110 截断**、英文标签 + glyph 风格，monitor 沿用（D-006 文案风格）。

## 结论 → 决策映射

- 发现 1 → D-001 选独立 interval（命令驱动 lifecycle），否决复用 watch 循环（key-scoped 语义不符 + 跨模块状态共享耦合）
- 发现 2+3+4 → D-002 新文件 autopilot/monitor.ts（采集/渲染/interval 三段纯函数化 + deps 注入），console.ts 只加命令入口
- 发现 5 → serve/conductor 的 uptime 与存活判定全部复用 mw-runner 公开函数 + conductor.pid 同款 signal-0 模式
- 发现 6 → 渲染风格与 watch widget 一致（D-006）
