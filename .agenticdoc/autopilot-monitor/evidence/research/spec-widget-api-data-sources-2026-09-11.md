# Research: pi 底部 widget API 与监控数据源（spec）

## 决策问题

§1 范围/§2 约束：pi 扩展是否支持常驻底部监控面板；mw/conductor/workers/gates 状态能否全部从文件只读获取，无需新增 RPC。

## 调研方法与出处

- 读 `packages/coding-agent/docs/extensions.md`（"Widgets, Status, and Footer" 节，约 L2551-2600）
- 读现有实现 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（WATCH_WIDGET_KEY）、`pm/pm-orchestrator.ts`（startWorkerPollLoop L488-560）、`shared/mw-runner.ts`（getMwStatus L82-96、serveStaleness/readServeMeta 为本 key 前置提交 5fa74a900 引入）
- 读 `packages/multi-workers/autopilot/conductor.py`（conductor_pid_file L62：`.mw/conductor.pid`）、`autopilot/config.py`（enabled/paused 布尔，缺文件 = 从未启用）、`autopilot/gates.py`（L182：frontmatter `status: pending`）
- 实机观察 JCodingAss 项目 gates/gate-0001.md frontmatter 结构

## 发现

1. **widget API 存在且够用**：`ctx.ui.setWidget(id, lines, { placement: "belowEditor" })` 支持字符串数组、自定义组件、`undefined` 清除。文档确认 `setWidget` 在 TUI 和 RPC 模式均可用（fire-and-forget 类）；print 模式（`ctx.hasUI === false`）须跳过。
2. **现有先例**：watch widget（id `agent-team-loop-watch`，belowEditor）已由 `startWorkerPollLoop`（4s 间隔，`POLL_INTERVAL_MS = 4000`）驱动，证明「interval + setWidget 增量刷新」模式在 TUI 稳定运行。多 widget 并存（不同 id）文档未明确布局叠放顺序——**待 design 阶段实机验证**，风险低（最坏两块面板上下叠放）。
3. **数据源全部文件化，零新 RPC**：
   - serve：`.mw/mw.pid`（getMwStatus：pid + `process.kill(pid, 0)` 存活判定）+ `.mw/serve.meta`（started_at_ms → uptime；serveStaleness → fresh/stale，含无 meta 的 pid-mtime 回退）
   - conductor：`.mw/conductor.pid`（同款 signal-0 存活判定；陈旧 pid 文件由 serve/conductor 退出路径清理，异常残留会被存活判定判死）
   - autopilot 意图：`.agenticdoc/_autopilot/config.json`（enabled/paused；缺文件 = 从未启用）
   - workers：`_workers.parallel`（running 行含 taskKey/dispatchedAt，跨 key 全量）
   - gates：`.agenticdoc/_autopilot/gates/*.md` frontmatter `status: pending`（数量级：个位数）
4. **归属地**：`/autopilot status` 已存在于 autopilot console（console.ts），监控命令与其同域；conductor/gates 是 autopilot 侧概念，mw serve 是其依赖。`/autopilot monitor` 为自然入口。

## 结论 → 决策映射

- 结论 1+2 → §2 约束「不修改 pi 核心，仅 Extension API」「4s 轮询（复用已验证模式）」；§4 风险「双 widget 叠放待验证」
- 结论 3 → §1 范围「纯只读文件数据源，不新增 serve RPC」，AC-008
- 结论 4 → 命令落点 `/autopilot monitor`（console.ts），渲染逻辑独立模块（design 决定复用或独立 interval）
