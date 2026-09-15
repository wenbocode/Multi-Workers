# Task: T-01 monitor.ts 模块 + console 命令接线 + L1 测试

> key: autopilot-monitor | type: coding | deps: 无
> 必读前置：`.agenticdoc/autopilot-monitor/spec.md`、`design.md`（§4 接口签名、§7 VC）、本文件全文

## 目标

实现 autopilot 监控面板：`/autopilot monitor [on|off]` 在 PM 窗口底部（belowEditor）常驻显示 mw serve / conductor / 跨 key running workers / pending gates 四层状态，4s 轮询，纯只读。

## 背景（你需要知道的系统事实）

- 本 repo 是 pi coding agent monorepo。扩展源码在 `packages/coding-agent/src/extensions/agent-team-loop/`，是 pi 的内置扩展（built-in），经 `mw build --install` 同步到全局 bundle（你不用管构建，T-02 做）。
- 已有同域代码（**先读再写**，风格与模式照抄）：
  - `autopilot/console.ts` — `/autopilot` 命令族（status/gates/gate/timeline/enable/disable/pause/resume），`AutopilotConsoleDeps` 已有 `ensureMwRunning` 注入缝先例；`registerAutopilotCommands(pi, projectDir, deps)` 是入口
  - `shared/mw-runner.ts` — 已有 `getMwStatus(projectDir)`（pid 文件 + `process.kill(pid, 0)` 存活判定）、`serveStaleness(projectDir)`（返回 `{stale, detail}` 或 undefined）、`readServeMeta(projectDir)`（返回 `{pid, started_at_ms, code_dir}` 或 null）——serve 行数据**直接调用，勿重造**
  - `shared/worker-store.ts` — `WorkerStore` 类，`readAll(): WorkerEntry[]`（字段 taskKey/status/dispatchedAt-ISO 字符串/taskPath）
  - `pm/ui-bridge.ts` L399+ — watch widget 渲染风格参考（英文标签 + glyph + `WATCH_LINE_MAX = 110` 截断）
  - 测试模式参考：`test/suite/autopilot-console.test.ts` 的 `fakeConsolePi()` / `fakeCmdCtx()` 辅助 + deps 注入
- 数据源（全部只读）：
  - `.mw/mw.pid`、`.mw/serve.meta`、`.mw/conductor.pid`（conductor 存活判定同款 signal-0）
  - `.agenticdoc/_autopilot/config.json`（字段 enabled/paused 布尔；**缺文件 = autopilot 从未启用**，不是错误）
  - `.agenticdoc/_autopilot/gates/*.md`（frontmatter 行式 `id:`/`kind:`/`stage:`/`status:`，只取 `status: pending`；文件个位数，行扫描足够，勿引入 YAML 库；解析失败的文件跳过）
- widget API：`ctx.ui.setWidget(id, lines, { placement: "belowEditor" })`，清除用 `setWidget(id, undefined)`。widget id 用 `"agent-team-loop-monitor"`（watch widget 是 `"agent-team-loop-watch"`，勿撞）。
- print 模式（`ctx.hasUI === false`）必须先守卫再碰任何 UI 路径（历史教训：goal-nudge 曾在 headless 撞车，commit 8a063f4d9）。

## 交付物

### 1. 新文件 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`

按 design.md §4.1 的签名实现（接口名逐字对齐，T-02/测试依赖它们）：

```typescript
export interface MonitorServe { running: boolean; pid: number | null; stale: boolean; staleDetail: string; upMs: number | null }
export interface MonitorConductor { pid: number | null; alive: boolean; enabled: boolean; paused: boolean; everEnabled: boolean }
export interface MonitorWorker { taskKey: string; elapsedMs: number }
export interface MonitorGate { id: string; kind: string; stage: number | null }
export interface MonitorSnapshot { serve: MonitorServe; conductor: MonitorConductor; workers: MonitorWorker[]; gates: MonitorGate[] }

export function readMonitorState(projectDir: string, nowMs: number): MonitorSnapshot
export function renderMonitorLines(s: MonitorSnapshot): string[]
export function startMonitor(projectDir: string, apply: (lines: string[] | undefined) => void, opts?: { intervalMs?: number; readState?: typeof readMonitorState; nowMs?: () => number }): boolean
export function stopMonitor(apply?: (lines: string[] | undefined) => void): boolean
export function isMonitorActive(): boolean
```

实现要点：
- `readMonitorState` 纯只读纯函数（除 fs 读外无副作用）。serve.upMs：优先 serve.meta.started_at_ms，无 meta 用 mw.pid 文件 mtime，都没有 null。conductor：pid 文件缺失 → pid=null/alive=false；config.json 缺失/损坏 → everEnabled=false（其余默认）。workers：仅 status==="running"，`elapsedMs = nowMs - Date.parse(dispatchedAt)`，Date.parse NaN 的行剔除。gates：目录不存在 → 空数组。
- `renderMonitorLines` 固定段结构（空态也要有行，避免面板高度跳动闪烁）：首行 `[autopilot monitor]`，然后 serve 行 / conductor 行 / workers 区（区头 + 每 running 一行）/ gates 行。参考样式（可微调但保持信息量）：
  ```
  [autopilot monitor]
  serve: PID 27572 fresh, up 2h 3m
  conductor: PID 99000 alive | autopilot enabled, not paused
  workers: 2 running (all keys)
    · ap-x-t01  3m
  gates: 1 pending - gate-0002 (stage-confirm) -> /autopilot gate gate-0002 approve|reject
  ```
  边界文案：serve not running → `serve: not running -> /mw restart`；stale → `serve: PID N STALE CODE (detail) -> /mw restart`；conductor 死 → `conductor: dead (pid N stale)`；未启用 → `conductor: not enabled (/autopilot enable)`；0 running → `workers: 0 running`；0 pending → `gates: 0 pending`。行宽超 110 截断加 `…`。
- `startMonitor`：幂等（已 active 直接返回 true）。立即渲染首帧（**不等首个 tick**），然后 setInterval(intervalMs ?? 4000) 每 tick 重读重渲。interval/active 状态存模块级变量。读取异常（如瞬时文件锁）→ try/catch 静默跳过该 tick（面板保持上帧，不抛错）。
- `stopMonitor`：幂等（未 active 返回 false）。clearInterval + 调 apply(undefined) 清面板。
- `apply` 回调由 console.ts 提供（包 ctx.ui.setWidget），monitor.ts 自身不持有 pi 依赖——这是测试缝。

### 2. 修改 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`

- switch 加 `case "monitor"`：参数 on/off/无参（toggle）。`ctx.hasUI === false` → 通知降级文案（含 "no visual UI"）并 return，**不启动轮询不抛错**。
- hasUI 为 true：构造 `apply = (lines) => ctx.ui.setWidget("agent-team-loop-monitor", lines, { placement: "belowEditor" })`；on/toggle-off 调 startMonitor/stopMonitor；开启后通知一行确认（含 4s 轮询与 off 方法提示）。
- USAGE 字符串补 `monitor [on|off]`。
- `AutopilotConsoleDeps` 追加可选 `readMonitorState?: typeof readMonitorState`、`monitorIntervalMs?: number`，透传给 startMonitor（测试缝，照 ensureMwRunning 先例）。**不改既有字段签名**。

### 3. 测试 `packages/coding-agent/test/suite/autopilot-monitor.test.ts`（新文件）

用 fake timers（`vi.useFakeTimers()`）+ tmp 目录夹具。每个 VC 一条测试，断言输出对齐 design §7：

- VC-001：serve 夹具（mw.pid 写测试进程自身 pid + serve.meta）→ startMonitor 后**同步**（0 tick）apply 收到首帧且 serve 行含 pid 与 fresh/stale
- VC-002：conductor.pid 写一个已死 pid（如 4194304 以上未占用大数，signal-0 抛 ESRCH）→ 首帧即 dead；再测活 pid（process.pid）场景 alive
- VC-003：_workers.parallel 写 2 行 running（dispatchedAt = now-90s，不同 key）+ 1 行 done → workers 区 2 行、分钟=2、done 不出现
- VC-004：gates 写 1 个 pending → 行含 id+kind；改为 approved 后推 1 tick → 归零
- VC-005：开→off → apply(undefined) 收到且推 2 tick 无新调用
- VC-006：fakeCmdCtx 的 hasUI=false → monitor on 返回降级提示、isMonitorActive() 仍 false、无异常
- VC-007：无 mw.pid → serve 行含 "not running" 与 "/mw restart"，其余行照常
- VC-008：开 3 tick，前后对 .mw/ 与 _autopilot/ 全文件内容 sha1 对比不变
- VC-011：两个独立 fake pi/模块实例（或 vi.resetModules 后二次 import）各自 start/stop，状态互不影响（进程内单例语义按模块实例隔离验证）

夹具注意：`_workers.parallel` 行格式 `| taskKey | status | cli | provider | taskPath | dispatchedAt | updatedAt | model |`（首行表头 `#` 开头注释可选，参考 worker-store.ts 解析器）；测试完 `vi.useRealTimers()` + 清 interval（afterEach stopMonitor）。

## 硬约束

- 只用可擦除 TS 语法（无 enum/namespace/parameter properties/import =）；tab 缩进；顶层 import（禁 inline import()）；biome 风格与邻文件一致
- **纯只读**：monitor.ts 与 console.ts 的 monitor 路径禁止任何 fs 写 API（VC-009 依赖）
- 不 commit、不跑 npm run check（PM 收尾跑）；不改 .agenticdoc 下任何文件（你的 progress/trace 由 worker 框架自管）
- edit 工具若报 oldText 找不到但文本确实存在：用临时 python 脚本 count+replace 兜底（已知工具偶发问题）

## 完成判据（progress.md 里逐条记录证据）

1. `npx tsgo --noEmit`（repo 根）零错
2. `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts` 全绿
3. `node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/extensions/agent-team-loop.test.ts` 无回归
4. 逐 VC 在 progress.md 记 `[VERIFY] VC-00X: key=value` 实测输出
