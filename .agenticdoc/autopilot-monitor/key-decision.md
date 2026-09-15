# KDR: autopilot-monitor

## R（需求）

- 技术栈: TypeScript（agent-team-loop 扩展）+ 既有 Python mw 文件产物（零 Python 改动）
- 边界: 只读监控面板（serve/conductor/workers/gates 四层），不做自动操作、不做 worker 输出流监控、不跨窗口同步
- 关键约束: 纯文件数据源零新 RPC（GC-2）；仅 Extension API 不改 pi 核心（GC-1）；print 模式安全降级；4s 轮询节拍与 watch widget 一致
- 命令: `/autopilot monitor [on|off]`（无参 = 切换），落点 autopilot console
- 决策记录:
  - 命令归属 `/autopilot` 而非 `/mw`：conductor/gates 是 autopilot 域概念，且 console 已有 status/gates/timeline 命令族 [AI 推荐，用户未指定]
  - 数据源全部只读文件（调研：evidence/research/spec-widget-api-data-sources-2026-09-11.md）

## A（架构）

- D001 轮询归属：独立 interval 命令驱动，否复用 watch 循环（key-scoped 语义不符，避免跨模块耦合）
- D002 模块落点：autopilot/monitor.ts 新文件 + console.ts 入口，否塞 console/ui-bridge（单一职责+deps 可测）
- D003 widget id：独立 id 并存，否合并 watch 单渲染（两套开关语义不同；叠放风险 L2 验证，fallback 合并）
- D004 gates 解析：frontmatter 行扫描，否复用 gate-writer（绑写路径）
- D005 UI 降级：hasUI 守卫+提示（goal-nudge 8a063f4d9 惯例）
- D006 命令 UX：无参 toggle + 首帧即时，否仅显状态（一键打开）
- D007 时钟：nowMs deps 注入（可测性）

## I（实施）← PM 执行中追加
