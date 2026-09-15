# Spec: autopilot-monitor

> Key: autopilot-monitor
> 创建时间: 2026-09-11T17:30:00+08:00
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「构建 Agent Team 协作框架……PM Agent 管理多个 Worker Agent 并行开发」中的**可观测性缺环**——autopilot 启用后（goal-autopilot key 已交付 conductor 自治编排），用户对 mw serve / conductor / 派发出去的 worker / 阻塞中的 gate 没有单一实时视图，只能靠手动 `/mw status` + `/autopilot status` + 读文件拼凑。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心：所有功能通过 Extension API 实现（监控面板用 `ctx.ui.setWidget`）
  - GC-2: 不引入中心化调度器：协调通过文件系统（监控数据全部来自既有文件：pid/meta/config/_workers.parallel/gates，零新 RPC）
  - GC-3: Worker 进程级隔离……（本 key 纯只读展示，天然满足）
- 冲突：无。
- 预期收益：本 key 达成后，用户在 PM 窗口一条命令打开常驻底部监控面板，编排链路（serve→conductor→workers→gates）健康状态一屏可见；判定方式：AC-001~AC-007 逐条通过 + 实机演示（repo 与 JCodingAss 双项目）。
  - 收益描述：把「链路是否活着、卡在哪」的答案时间从分钟级（手动跑命令/读文件）降到 ≤1 个轮询周期（4s）。

## §1 功能概述

### 1.1 目标

autopilot 开启后，提供一条命令 `/autopilot monitor`（支持 on/off 切换），在 PM 窗口底部打开常驻监控面板，实时显示编排系统四个层级的健康与进度：

1. **mw serve**：运行状态（PID / not running）、代码新旧（fresh/stale）、uptime
2. **conductor**：存活（PID + alive/dead）、autopilot 意图（enabled / paused / 未启用）
3. **workers**：跨 key 全部 running 行（taskKey + 已运行时长），阻塞告警（pending gate）
4. **gates**：待人工决断的 pending gate（数量 + id + kind）

### 1.2 技术栈 / 语言

TypeScript（agent-team-loop 扩展内新增模块 + autopilot console 命令）；数据源为 mw（Python）已产出的文件。零 Python 侧改动。

### 1.3 核心用户场景

1. **启用后确认链路**：用户 `/autopilot enable` 后执行 `/autopilot monitor`，面板显示 serve PID + fresh、conductor PID + alive——一眼确认「承诺的 conductor 真的起来了」（goal-autopilot 阶段教训：enable 的假承诺问题）。
2. **观察派发**：conductor 派发 worker 后，面板 running 区出现新行（taskKey + 分钟数递增），用户不读任何文件即可感知进度。
3. **发现阻塞**：stage-confirm gate 产生后面板显示 pending gate，用户知道该去 `/autopilot gate gate-NNNN approve|reject`；处理完 ≤1 周期内行归零。
4. **故障即时可见**：serve 挂掉 / 代码陈旧 / conductor 死亡，面板对应行在 ≤2 个轮询周期内变红/告警文案。
5. **收起**：再次执行命令（或显式 off）清掉面板，恢复纯 watch widget 状态。

### 1.4 范围说明（不做什么）

- 不做 worker 实时 token/输出流监控（per-key 行为摘要已由 watch widget 覆盖；trace.log 深读留给后续 key）
- 不做 conductor 内部状态机细节透出（只报 alive/dead + config 意图：enabled/paused）
- 不做任何自动操作（不自动重启 serve、不自动批 gate——只显示，操作仍走既有命令）
- 不做跨窗口同步（monitor 开关是每窗口内存态，见 AC-009）

## §2 业务约束

### 2.1 平台 / 环境

- Windows（开发/主用机）+ POSIX 兼容（`process.kill(pid, 0)` 双平台语义一致，沿用 getMwStatus 既有模式）
- 生效环境：TUI 交互模式（主目标）；RPC 模式 setWidget 可用（fire-and-forget）；print 模式（`ctx.hasUI === false`）命令须安全降级（AC-006）

### 2.2 性能指标

- 轮询周期 4s（复用 `POLL_INTERVAL_MS = 4000`，与 watch widget 同节拍，避免双 interval 抖动）
- 单次轮询全部数据源读取总耗时 < 100ms（文件均为本地小文件：pid/meta/config/worker 表/gates frontmatter 个位数文件）
- widget 渲染在数据无变化时不产生视觉闪烁（幂等 setWidget）

### 2.3 安全约束

- 监控路径只读：除 widget 外不写任何文件（AC-008）；不触碰 `_workers.parallel` 写锁
- 不泄露敏感信息：面板不显示 API key/环境变量，仅进程号/文件派生状态

### 2.4 集成依赖

- 依赖 5fa74a900 引入的 `serveStaleness`/`readServeMeta`/`getMwStatus`（mw-runner.ts）
- 依赖 mw（Python）侧既有产物：`.mw/mw.pid`、`.mw/serve.meta`、`.mw/conductor.pid`、`.agenticdoc/_autopilot/config.json`、`gates/*.md`
- 依赖 pi Extension API `ctx.ui.setWidget(id, lines, { placement: "belowEditor" })`

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-11T17:30:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 mw serve 运行（mw.pid 存在且进程存活）的项目目录下执行 `/autopilot monitor on`，≤1 个轮询周期（4s）内底部出现监控面板，serve 行包含 PID 与 fresh/stale 判定（有 serve.meta 用 meta，无则 pid-mtime 回退） |
| AC-002 | 在 conductor.pid 存在且进程存活且 config enabled=true 时，面板 conductor 行显示 PID + alive + enabled；将 conductor 进程终止后，≤2 个轮询周期内该行变为 dead（含 PID 陈旧信息） |
| AC-003 | 在 `_workers.parallel` 含 ≥1 行 running（任意 key）时，面板 workers 区显示每个 running 行的 taskKey 与自 dispatchedAt 起的运行分钟数（向上取整）；非 running 行不出现 |
| AC-004 | 在 `.agenticdoc/_autopilot/gates/` 下存在 frontmatter `status: pending` 的 gate 文件时，面板 gates 行显示 pending 数量及各 gate id（+kind）；所有 gate 离开 pending 后 ≤1 个轮询周期内该行归零或消失 |
| AC-005 | 在监控开启状态下执行 `/autopilot monitor off`（或无参再切一次），面板在 ≤1 个轮询周期内被清除（`setWidget(id, undefined)`），后续轮询不重建 |
| AC-006 | 在 print 模式（`pi -p`，ctx.hasUI === false）下执行 `/autopilot monitor on`，命令返回降级提示文本（说明无可视 UI）且不启动轮询、不抛异常、退出码 0 |
| AC-007 | 在 mw serve 未运行时打开监控，serve 行显示 not running 及恢复指引文案（含 `/mw restart`），面板其余行照常渲染，命令不抛错 |
| AC-008 | 监控开启期间连续 3 个轮询周期，`.agenticdoc/` 与 `.mw/` 下除 mtime 外无任何文件内容变化（纯只读），关闭窗口后无残留 interval/进程副作用 |
| AC-009 | monitor 开关状态为单窗口内存态：窗口 A 开启不影响窗口 B 的面板状态，且不写入 config.json / 任何持久文件 |

## §4 风险与未决项

- 风险：双 widget 并存（watch + monitor，不同 id）的叠放顺序与占高未经实机验证（文档未明确多 widget 布局规则）——design 阶段在 tmux/实窗验证，若叠放不可接受则合并渲染为单 widget 两段式。
- 风险：conductor.pid 异常残留（serve 被强杀未走清理）→ 存活判定会显示 dead + 提示，可接受（不做自动清理，保持只读承诺）。
- 待确认（design 决定）：轮询复用 `startWorkerPollLoop` 的 interval 还是独立 interval（归属/生命周期权衡）；monitor 渲染模块的落点（autopilot/monitor.ts vs pm/ui-bridge.ts）。
- 待确认：面板行文案中英文选择（现有 watch widget 为英文 + 中文混合告警，倾向行首英文标签 + 状态词，与 /autopilot status 输出风格一致）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `getMwStatus` / `serveStaleness` / `readServeMeta`（mw-runner.ts，5fa74a900）：serve 行数据直接调用，勿重造
- watch widget 全套模式（ui-bridge.ts `WATCH_WIDGET_KEY` + `startWorkerPollLoop` 4s 轮询 + `applyWatchWidget`）：监控面板复用同一渲染/节拍模式
- gates frontmatter 解析、config.json 布尔字段（enabled/paused）读取：与 Python 侧 schema 对齐（gates.py L182、config.py L13-14）
- 测试手法：autopilot-console.test.ts 的 fakeConsolePi/fakeCmdCtx + deps 注入模式（monitor 命令同款可测）

### 需规避坑点

- 含字面量 `goal.md` 的只读命令会被写门禁误拦：读该文件用 rg
- PowerShell 下含引号/中文的命令行参数易碎：验证脚本走临时文件 + `python -X utf8`
- edit 工具对特定文件偶发 oldText 匹配失败（文本实测存在）：python 脚本 count+replace 兜底，整批原子
- print 模式 UI 语义：`ctx.hasUI === false` 必须先判再碰 widget/notify 路径（goal-nudge 修复 8a063f4d9 的同款教训）
