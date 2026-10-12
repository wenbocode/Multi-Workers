# SPEC 阶段调研 RQ-4：`/mw restart` 后 autopilot monitor 面板冻结（观测面撒谎）的根因锚定

> 关联记录（只读）：`H:\git\E2Feature\.agenticdoc\_autopilot\reflect\monitor-frozen-after-mw-restart.md`（2026-10-09，status: open）。
> 本卡为只读调研：未修改任何代码或其它文件。全部事实带 `文件:行号`；行号以本卡执行时刻的工作树（HEAD `10446aefb`）为准。
> 运行时差异：E2 窗口实际加载的是全局安装的打包产物 `~/.pi/agent/extensions/agent-team-loop.js`（mtime 2026-10-09 11:07:35，对应提交 `5c1149f1b`）。本卡对该 bundle 的 monitor/worker-store/mw-runner 段落与 HEAD 源码逐段比对，**逻辑一致**（见 §3.1.4）。

---

## 1. 决策问题

RQ-4 要钉死的问题：`/mw restart`（2026-10-09 15:21:13 本地）之后，面板显示新 serve/conductor PID（看着活着）、`workers: 0 running`（同刻 `_workers.parallel` 实有 running 行）、`gates: 0 pending`（正确），且**不报错、不自证过期**。需要判定是哪一段代码造成的，以及 G4（快照年龄戳 / 重臂）应落在哪些行。

判定口径（本卡的"可回答 / 不可回答"边界）：
- **可回答**：循环本体能否静默停止、有哪些静默失败/不重绘路径、每个路径的 file:line 与判据；`/mw restart` 的确定语义；beat 文件是否被面板读（二选一）；PID 段是否逐 tick 重读；快照自证字段的有无与可复用的先例；重臂挂点；测试面；G2/G4 行号重叠。
- **不可回答（须明确声明）**：2026-10-09 那次冻结**具体触发语句**。面板帧内没有任何"采集时刻"戳（§3.5），冻结帧与活帧在留存证据上不可区分；下面把可排除项与剩余候选写清楚，并把"能区分它们的那一个字段"作为 G4 的验收点。

### 1.1 先修正记录里的一处判定（重要）

reflect 记录写"面板内容与冻结在 15:21:13 逐项吻合"。**该推断证据不足，真实冻结窗口宽得多**：

- serve/conductor 段是**逐 tick 重读**的（§3.4），所以"显示新 PID"只能证明 **≥1 次成功 tick 发生在 15:21:13 之后**，不能把冻结时刻钉到 15:21:13。
- 面板显示 `workers: 0 running` 在 **任何** 位于 [15:21:13, 16:37:22] 的 tick 上都成立：16:37:22 才是第一条 running 行落盘时刻（第二行 16:39:16；用户 16:39:12 已报告 0）。`gates: 0 pending` 自 15:01 起一直正确。
- 结论：冻结起始 ∈ [15:21:13, 16:37:22]，跨度 4,569 s ≈ 1,142 个 4 s tick。**验收判据必须是"≤2 个刷新周期内跟随变化"，不能写成"重启时点"**（否则 VC 无法机械验收）。
- 同时确认：用户 16:27:48 的首次报告（"conductor monitor 中没有任务在跑"）本身**不构成冻结证据**——那时真实 running=0（PM 会话 15:19:33 自查 running=2，之后 -a1 随重启死亡、-004 直到 16:37 才派）。冻结的硬证据只有 16:39:12 那次（1 行 running 已存在 110 s 而面板仍 0）。

---

## 2. 调研方法与出处

1. 全文读 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`（855 行）与 `autopilot/console.ts`、`pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`（monitor/`/mw` 相关段）、`shared/mw-runner.ts`、`shared/worker-store.ts`、`shared/dispatch-models.ts`、`index.ts`。
2. 追 pi 宿主侧：`core/extensions/runner.ts`、`core/extensions/loader.ts`、`core/agent-session.ts`、`core/agent-session-runtime.ts`、`modes/interactive/interactive-mode.ts`、`packages/tui/src/{tui.ts,components/text.ts,tui-main-screen.ts}`。
3. 追 Python 侧：`packages/multi-workers/mw.py`、`mw_common.py`、`launcher.py`、`autopilot/conductor.py`。
4. 只读现场证据（E2Feature）：`.mw/*`（含 CreationTime / LastWriteTime）、`.agenticdoc/_workers.parallel`、`.agenticdoc/_autopilot/{config.json,gates/,timeline.jsonl*,reflect/}`、`~/.pi/agent/extensions/agent-team-loop.js`、`~/.pi/agent/sessions/--H--git-E2Feature--/*.jsonl`。
5. 机械复核（不是手算）：用 HEAD 的 dist 产物直接调用面板同一条读路径 `new WorkerStore("H:/git/E2Feature/.agenticdoc").readAll()`（dist `shared/worker-store.js`，node v24.19.0）：实测 `parsed=593 / running=2 / runnable=2`（与面板 `monitor.ts:355-359` 的过滤条件一致；复跑：`parsed=621 / running=2 / runnable=2`，行数随 worker 收敛增长，解析路径仍健康）⇒ **数据面健康、解析路径健康；`workers: 0 running` 只可能是"帧没重算"**。
6. 全仓 grep `launcher-beat`（src / dist / 全局 bundle / py）见 §3.3。

---

## 3. 发现

### 3.1 刷新循环本体与全部静默停止/不重绘路径

**本体（全部行号已核）**

| 项 | 位置 |
|---|---|
| widget id / 周期 / 行宽 | `monitor.ts:55`（`agent-team-loop-monitor`）、`:58`（`MONITOR_INTERVAL_MS = 4000`）、`:61`（110 列） |
| 模块级单例状态 | `monitor.ts:805-806`（`monitorTimer` / `monitorApply`） |
| 活动判定 | `monitor.ts:808-810` |
| 启动 + tick | `monitor.ts:820-838`：`:825` 幂等早退；`:827-833` tick 闭包（`:829-832` 是 `try { apply(renderMonitorLines(readState(projectDir, nowMs()))) } catch {}`）；`:835` 同步首帧；`:836` 记 apply；`:837` `setInterval(render, opts?.intervalMs ?? MONITOR_INTERVAL_MS)` |
| 停止 | `monitor.ts:847-853`：`:848` 非活动返回 false；`:849` `clearInterval`；`:851-852` 清 apply 并 `apply(undefined)` |
| 唯一生产调用点 | `console.ts:653-684`（`/autopilot monitor`）：`:666-668` 构造 `apply`（`ctx.ui.setWidget`）；`:669-677` `off` 或裸 `monitor` 且活动 → `stopMonitor(apply)`；`:679` `on` → `startMonitor` |
| 自动开面板 | `console.ts:710-725`（`:714` `if (isMonitorActive()) return true`；`:717-723` `startMonitor`），由 PM 的 `session_start` 钩子调用：`pm-orchestrator.ts:799` |

每 tick 调用链：`render` → `readMonitorState`（`monitor.ts:287-386`）→ `renderMonitorLines`（`:672-796`）→ `apply` → `ctx.ui.setWidget` → pi `setExtensionWidget`（`interactive-mode.ts:2092-2133`）→ `renderWidgets`（`:2185-2188`）→ `ui.requestRender()`。

**可疑点清单（每条给判据；"能否静默停止/不重绘"= 该点触发时是否出现记录里的现象）**

- **S1 — `monitor.ts:829-832` 的裸 catch（唯一"吞掉一切"点）**。任何 tick 内异常都只丢掉这一帧，无计数、无日志、无年龄戳 ⇒ 面板停在上一帧且**永不自证**。判据：帧内容停更、进程存活、无任何错误输出。⇒ 只要 S1 在，现象的**不可见性**就是必然的；这是本 RQ 必须收紧的点，也是 G4"快照年龄"的直接理由。
- **S2 — `monitor.ts:825` 幂等早退 + 模块级单例 + 宿主重激活**。扩展工厂函数在进程内被复用（`loader.ts:412-441`：`moduleCache:false` 只影响模板编译，`:436-440` 把**同一个 factory** 放进 `extensionCache`，重载时复用 ⇒ 工厂闭包里的模块级 `monitorTimer` 跨会话存活），而 `/new`、`/resume`、`/fork`、`/import`、`/reload` 会重建 runtime 并重跑 `activate()`（`agent-session.ts:2584` 新建 `ExtensionRunner`；`interactive-mode.ts:518-520` → `:2146-2164` 会**清空全部扩展 widget**，`:2160` 调用 `clearExtensionWidgets`；`agent-session.ts:850-853` 在 dispose 时 `runner.invalidate`，`runner.ts:552-556` 之后任何 `ctx.ui` 取值都抛）。此时 `autoStartMonitor`（`console.ts:714`）认为"已活动"直接返回 true ⇒ **面板不会被重挂**；旧 tick 的 `ctx.ui` 抛错被 S1 吞掉。判据：发生会话替换/`/reload`。本型事故里**不成立**（见 §3.2 证据：10-09 无任何 `session_start`/`model_select` 写入痕迹）。注意伴随事实：`/reload` 不 invalidate 旧 runner（`agent-session.ts:2607-2629` 只新建 runner，未 dispose 旧 runner），且 uiContext 对象是宿主共享的（`interactive-mode.ts:2344`），所以 `/reload` 之后旧 tick 仍能写盘、面板会在 1 tick 内自愈——**S2 只在 new/resume/fork/import 路径上致命**（面板被清空后不再回来）。
- **S3 — tick 内未受保护的读（唯一"真会抛"的语句）**。逐条核过 tick 的每个读点，除下列两处外全部有 try/catch 或安全退化（`readConfig` `status-model.ts:249-267`、`readRoadmap` `:570-575`、gates 扫描 `monitor.ts:363-380`、conductor 段 `:311-330`、`readServeMeta` `mw-runner.ts:207-216`、`serveStaleness` `:272-289`、`mwCodeNewestMtimeMs` `:224-257`、`defaultIndexPhases` `monitor.ts:566-573`、`readTimelineTail` `:396-443`）：
  1. `mw-runner.ts:85` `fs.readFileSync(pidPath)`（`getMwStatus`，被 `monitor.ts:289` 在 tick 最开头调用）；
  2. `worker-store.ts:119` `fs.readFileSync(this.filePath)`（`readAll`，被 `monitor.ts:355` 调用）。
  另有一处半保护：`monitor.ts:438-439` `finally { fs.closeSync(fd) }` 的抛出会穿出 `readTimelineTail`（finally 内不在 catch 覆盖内）。
  判据：Windows 共享/替换竞态的 `EPERM/EBUSY/ENOENT`。**注意本型事故里文件面是健康的**（面板那一帧成功读到 PID；16:39 实测同路径解析出 2 running；两侧写者都是 tmp+replace：`worker-store.ts:134-136`、`mw_common.py:1704-1709`，Node 读者带 FILE_SHARE_DELETE），因此 S3 要成立必须是一次**长期持续**的读失败，留存证据无法证实也无法排除。⇒ 这是"每一个 tick 都抛"的候选之一。
- **S4 — apply 内部抛错（`ctx.ui` / `setExtensionWidget`）**。`ctx.ui` 取值先过 `runner.assertActive()`（`runner.ts:552-556`），抛点在 `setExtensionWidget` **改动 widget map 之前**（`interactive-mode.ts:2104-2105` 只是删旧项）⇒ 抛错时 widget 保留旧内容、面板"可见但冻结"，与现象完全一致。但该抛错需要 runner 被 invalidate（只有会话 dispose 会触发，`agent-session.ts:850`），而 dispose 前必走 `resetExtensionUI`（`interactive-mode.ts:518-520`、`:2160`）把 widget 清掉 ⇒ **S4 单独出现时面板应消失而不是冻结**；只有"invalidate 发生但 widget 未被清"才成立，而该组合在 10-09 无痕迹（见 §3.2）。
- **S5 — widget 归属被第三方替换/提前 dispose**。`MONITOR_WIDGET_ID` 只出现在 monitor.ts/console.ts（grep：`monitor.ts:55`、`console.ts:666`、`:719`），无第三方写同名 key；`setExtensionWidget` 对同名 key 先删上下两个 map（`interactive-mode.ts:2104-2105`）；数组形态的组件是 `Container`/`Text`，**都没有 `dispose`**（`tui.ts:211` `class Container`；`Text` 无 dispose；全 `packages/tui/src` 只有 `components/alt-screen-flash.ts:38`、`components/cancellable-loader.ts:37` 有）⇒ `removeExisting` 不可能抛、也不可能被第三方顶掉。**排除。**
- **S6 — 渲染层丢更新（TUI 侧）**。`Text` 只在自身实例内按 text/width 缓存（`components/text.ts:14-16, 45-49`），每 tick 都新建实例 ⇒ 无陈旧命中；主屏 diff 渲染器在内容缩短时会主动逐行清掉多余行（`tui-main-screen.ts:331-364`，`\r\x1b[2K`），`clearOnShrink` 只影响"整屏重绘 vs 差分"（`tui.ts:344` 默认 false；`tui-main-screen.ts:286-291`）；`widgetContainerBelow` 只在构造函数赋值（`interactive-mode.ts:481, 542`，布局挂载 `:858-877`），uiMode 切换复挂同一批容器（`:767-813`）。⇒ **渲染层不会给出"陈旧但可见"的帧。排除**（此结论同时给出 §3.1 的关键推论：**停表必然清面板**（`stopMonitor` → `apply(undefined)` → `interactive-mode.ts:2101-2108` 走空 map 分支 → `tui-main-screen.ts:331-364` 擦除），所以"可见的陈旧帧"**不可能是循环停表**，只能是"循环仍在跑但每帧在改动 widget 之前就失败/被吞"。）

**3.1.4 运行产物一致性**：全局 bundle `agent-team-loop.js` 的 `startMonitor`（bundle 行 22527-22541）、`readMonitorState` 的 workers 段（bundle 行 22185-22190）、`getMwStatus`（bundle 行 18281-18291）、`WORKER_COLS_MAX=9`（bundle 行 20982）与 HEAD 源码逐行等价 ⇒ 下面的结论对 E2 实际运行版本同样成立。
### 3.2 `/mw restart` 的真实语义（kill 谁 / 起谁 / 写哪些文件 / 是否重挂扩展）

- 入口：`/mw` 命令注册在 `ui-bridge.ts:2204`，`restart` 分支 `:2291-2305` → `restartMw`。
- 实现：`mw-runner.ts:324-338` → `restartSequence`（`:298-321`）：
  1. 写停表请求 `.mw/mw.stop`（`mw-runner.ts:329-331`；协议同 `mw.py:100-103`，serve 侧清请求见 `mw.py:219`/`:356`/`:398` 的 `_clear_stop_request`）；
  2. 轮询 `getMwStatus`（`mw-runner.ts:82-97`，`process.kill(pid,0)` 活性判定）直到旧 pid 消失（超时 30 s，`:334`）；
  3. `startMw`（`:124-136`）detached 起 `python mw.py start --project=<dir>`；
  4. `waitForMwStart`（`:149-157` → `waitForStart` `:159-181`）确认"新 pid 连续存活 3 s"。
  **没有 `mw.py restart` 子命令**；`mw.py start`（`mw.py:414-450`）以 `DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW`（`:436-441`）起 `mw.py serve`。
- serve 侧写点：`.mw/mw.pid`（`mw.py:84-86`，调用 `:270`）、`.mw/serve.meta`（`mw.py:121-127`：`pid`/`started_at_ms`/`code_dir`，调用 `:272`）。conductor 自写 `.mw/conductor.pid`（`conductor.py:84-85` `conductor_pid_file`、`:6625` `write_text`）。launcher 自写 `.mw/launcher-beat.<pid>`（`launcher.py:786` → `mw_common.py:2065-2070`）。
- 三者生命周期（现场证据）：serve 是父进程，launcher/conductor 是 serve 的**子进程**（10-09T09:12:31Z / 本地 17:12 现场：`pid 107724 parent 71884`，`126800/125148 parent 107724`；`71884` 已退出 = serve 已脱离 pi）。旧世代的 launcher/conductor 随 serve 停表退出：E2 `.mw/launcher-beat.73496` 最后一次写入 15:21:10，新 beat 文件 `launcher-beat.126800` CreationTime 15:21:13（`mw.log` 亦记 `started (PID 107724) launcher=126800` / `conductor spawned (PID 125148)`）。`mw.log` **没有时间戳**，逐世代时间只能取自 beat 文件的 CreationTime/LastWriteTime。
- **是否 relaunch 扩展 / pi 窗口：否。** 三条独立证据：
  1. `/mw` 处理函数只做上面 4 步（`mw-runner.ts:324-338` + `startMw` `:124-136`），不触碰 pi；
  2. pi 侧"会话启动"会**无条件**重写 `.mw/window-model`（`dispatch-models.ts:100-111`，钩子 `:321-326` 注册在 `session_start`/`model_select`），而 E2 的 `.mw/window-model` mtime = **2026-09-23 17:53:28**，10-09 全天未写 ⇒ 10-09 该窗口**没有任何 session_start/`/reload`**；
  3. 该 PM 窗口的会话文件 `2026-09-23T07-46-52-599Z_01a0cd3b-...jsonl` 连续写至 10-09 09:13Z，891 条内只有 **1** 个 `"type":"session"` 头、4 个 `compaction`（09-24、09-25、09-26、10-09T07:20:41Z），无新建会话文件。
  ⇒ 重启不会重挂扩展，面板的 4 s 定时器**与重启无关地**继续存在（`monitor.ts:837`）；`/mw restart` 不是"循环被停掉"的原因。

### 3.3 beat 文件的身份耦合：确定性结论 = **不缓存（面板根本不读）**

全仓 grep `launcher-beat` 的全部命中点：

- 写者：`launcher.py:783-786`（每 poll 第一件事）→ `mw_common.py:2065-2070`（`launcher_beat_write`，单行 `ts=<iso>`，无锁覆写）；常量 `mw_common.py:2058` `_BEAT_FILE_PREFIX`、`:2059-2060` 新鲜阈 30 s。
- 读者：**只有 Python** `mw_common.py:2073-2111` `other_live_launcher`（glob `.mw/launcher-beat.*`、跳过 self、ts<30 s 且 pid 存活 → 真），调用点 `launcher.py:590-593`（静默回收前让位）。
- 测试：`test_common.py:490-560`、`test_launcher.py:950,990,1039`。
- 文档/CHANGELOG：`packages/coding-agent/CHANGELOG.md:206`、若干 `.agenticdoc/**` 记录。
- **TS 侧（`src`、`dist`、以及运行时真正加载的 `~/.pi/agent/extensions/agent-team-loop.js`）命中数 = 0。**

⇒ 结论（二选一，取"不缓存"）：**面板既不扫描也不缓存 `launcher-beat.<pid>`；monitor 全部读面只有 `getMwStatus`(.mw/mw.pid)、`readServeMeta`(.mw/serve.meta)、`.mw/conductor.pid`、`_autopilot/config.json`、`_workers.parallel`、`_autopilot/gates/`、`_autopilot/_roadmap.md`、`_index.parallel`、`timeline.jsonl`**（`monitor.ts:289,294,316,334,355,363,382` 与 `deriveAutopilotPanel:578-641`）。记录 §3.5 把 beat 文件名列为"首要嫌疑"**被证伪**；task 中 `monitor.ts:596-609/635` 指向的是 autopilot 的 **tick** 新鲜度（`BEAT_EV`，`status-model.ts:992`），不是 launcher beat 文件，两者同名不同物，后续 plan 不要串。

### 3.4 PID 段为何"静态"：结论 = **面板每 tick 都在重读，静态的是源文件不是面板**

- serve 段：`monitor.ts:289` `getMwStatus` + `:292` `serveStaleness` + `:294` `readServeMeta`（每 tick 重新 `fs.readFileSync` `serve.meta`，`mw-runner.ts:207-216`）；`upMs = nowMs − started_at_ms`（`monitor.ts:294-303`）。
- conductor 段：`monitor.ts:316-330` 每 tick 重读 `.mw/conductor.pid` 并 `process.kill(pid,0)`。
- 因此"重启后写一次即固定"**只对文件成立**（`mw.py:270/272`、`conductor.py:6625-6627` 各写一次/世代），**对面板不成立**：面板每次 tick 都拿到同样的新值。
- 推论：新 PID 不能证明"面板活着"，只能证明"最后一帧成功于 15:21:13 之后"；反之它也不能证明"面板已死"。**唯一带微弱活性信息的字段是 `serve: ... up <duration>`**（`monitor.ts:688` + `formatDuration:651-658`，分钟级粒度），不足以支撑 4 s 级验收。

### 3.5 快照自证缺位（现状字段 + 可复用的先例）

- `MonitorSnapshot`（`monitor.ts:170-176`）字段恰好 5 个：`serve/conductor/autopilot/workers/gates`——**没有任何采集时刻/快照年龄/读盘时刻**。
- `MonitorAutopilot`（`:156-168`）10 个字段里 `tickAgeMs`(`:160`)/`tickStale`(`:162`) 是**conductor tick 的年龄**，不是面板快照的年龄。
- 其余"年龄类"字段都是**被观测对象的年龄**：`MonitorServe.upMs`(`:71`，源 `serve.meta`)、`MonitorWorker.elapsedMs`(`:92-93`)、`MonitorGate.ageMs`(`:107`)、`MonitorStall.ageMs`(`:152`)。
- 现有 staleness 先例（可直接复用同一机制）：`:609` `staleAfterMs = max(30_000, pollMs*5)` → `:635` `tickStale: tickAgeMs !== null && tickAgeMs > staleAfterMs` → `:713` 渲染 `STALE (conductor not ticking)`；格式化函数 `formatDuration`(`:651-658`)。`MonitorServe.stale/staleDetail`(`:67-68`) 同型。
- **关键语义提醒（给 G4）**：在帧**内部**算出的"快照年龄"对活 tick 恒为 0（渲染瞬间就是采集瞬间），因此它只能证明"这一帧是新的"，不能证明"上一帧到现在没有断"。要能区分冻结，帧里必须携带**绝对采集墙面时刻**（和/或单调 tick 计数）——面板冻结时该戳不再前进，肉眼与自动化都能判。这也正是"能区分 §3.1 里 S3/S4（每帧都失败）与 S6（渲染层丢更新）"的那一个字段。
### 3.6 `/mw restart` 后重挂面板的可行挂点（1-2 个）

- **挂点 A（推荐，最小改动面）**：tick 内已有的跨代观测点——`serve.pid`（`monitor.ts:289-300`，每 tick 从 `serve.meta` 重读）。在模块级保存上一 tick 的 pid，pid 变化（重启）时重新 `stopMonitor()` + `startMonitor(projectDir, apply, ...)`（`:847-853` / `:820-838`）即可在 ≤1 tick 内重挂；同一位置还能顺手把"重臂次数/最近重臂时刻"写进帧（配合 §3.5）。
- **挂点 B（存在现成生命周期钩子，但目前 monitor 没接）**：PM 侧 `pi.on("session_shutdown", () => clearInterval(pollHandle))`（`pm-orchestrator.ts:726-732`）与 `index.ts:28-35`（`session_shutdown` 里重置 `ACTIVATION_FLAG`）证明"会话替换时清掉自己的定时器"是本扩展既有惯例；`monitor.ts` 既没有 shutdown 钩子（`console.ts:690-693` 注释里明确留着"a future session_shutdown hook can call this too"），也没有像 watch widget 那样在每次 `session_start` 刷新 ctx（`pm-orchestrator.ts:795` `ui.ctx = ctx` → `ui-bridge.ts:704-708` `applyWatchWidget`）。⇒ 在 `session_shutdown` 里 `stopMonitor()`，或在 `autoStartMonitor`（`console.ts:710-725`）里把 `:714` 的早退改成"已有活动但 ctx 不同则先 stop 再 start"。这条同时封掉 §3.1 S2。

### 3.7 既有 TS 测试面（G4 的 VC 要能机械验收）

- `packages/coding-agent/test/suite/autopilot-monitor.test.ts`（1121 行）：
  - fake timers 先例：`:230`、`:483`、`:605`（`vi.useFakeTimers()`），并用 `vi.advanceTimersByTime(4000)` 精确推进 tick：`:277,279,283`（VC-002）、`:332`（VC-004）、`:425-427`（VC-008）、`:663`。
  - 生命周期用例：`:238`（VC-001 首帧 0 tick）、`:262`（ticks 重算）、`:292`（VC-003 workers 行）、`:319`（VC-004 gate 归零）、`:340`（VC-005 off 清 widget 且后续 tick 不再渲染）、`:412`（VC-008 三 tick 文件字节不变）、`:437-472`（VC-011 两个模块实例互不串扰）。
  - 自动开面板 / 幂等：`:747-781`（含 `:761-765` "已活动则不再 start，widgets.length 不变"的断言）。**这正是 S2/G4 要新增反向用例的位置**（现状把"幂等不重启"当成正确行为）。
  - 进度段与 stale 鲜度：`:812-`（`:986` "flags a stale tick when the conductor stopped beating"、`:1003` 空项目退化、`:1084` timeline 尾部读）。
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（5380 行）：fake timers 大量先例（`:1908,1930,1963,1994,2043,2074,2102,2133,2295,2338,2378,2841,3077,...`）。
- 可机械验收的现成装配：`startMonitor(root, apply, { nowMs: () => now })` 注入 `nowMs`（`monitor.ts:826`）+ `vi.advanceTimersByTime` ⇒ "≤2 个刷新周期（8 s）内跟随"可直接写成断言（写盘 → 推 8000 ms → 断言帧含 `workers: N running`）；"冻结自证"则断言帧内采集时刻戳随 tick 前进。

### 3.8 历史实例核实（reflect 表里标"待核"的 09-23 / 09-25 / 09-26）

可得的逐世代事实（E2 `.mw/launcher-beat.*`，CreationTime = 该 launcher 首次 poll ≈ serve 重启时刻；共 12 个世代文件）：

| 世代（pid） | 创建（≈重启） | 最后 beat |
|---|---|---|
| 35160 | 2026-09-22 16:55:16 | 09-23 00:01:21 |
| 34580 | 2026-09-23 00:01:29 | 09-23 15:47:25 |
| 46824 | 2026-09-23 15:47:29 | 09-24 11:03:42 |
| 49640 | 2026-09-24 11:03:43 | 09-25 14:47:11 |
| 55896 | 2026-09-25 14:47:13 | 09-26 10:19:55 |
| 36348 | 2026-09-26 10:19:59 | 09-26 10:30:44 |
| 73496 | 2026-09-26 10:30:48 | 10-09 15:21:10 |
| 126800 | 2026-10-09 15:21:13 | 至今 |

⇒ 09-23/09-25/09-26 三天共 **5** 次 serve 重启（09-23 00:01:29、09-23 15:47:29、09-25 14:47:13、09-26 10:19:59、09-26 10:30:48）。

**同型证据是否可得：不可得（明确结论）**：
1. 面板帧**从不落盘**（widget 内容只在内存，`monitor.ts` 无任何写路径，只读性亦由 `autopilot-monitor.test.ts:412` 的"三 tick 文件字节不变"用例印证），故历次"面板快照"无留存。
2. 逐世代的 `.mw/serve.meta`/`mw.pid`/`conductor.pid` 被下一次重启覆写（现存的只有 10-09 世代），`mw.log` 无时间戳，所以除 beat 文件外**没有逐世代的时间/pid 证据**。
3. 人证也不可得：该 PM 窗口的会话 jsonl（跨 09-23 → 10-09，891 条）**只有 2 条** user 消息提到 monitor，均在 10-09（16:27:48、16:39:12）；09-23/09-25/09-26 无任何 monitor/面板相关用户报告；`.agenticdoc/_autopilot/reflect/` 目录下 12 条记录中无其它 monitor 条目。
⇒ 因此该表 3 行的证据强度应据实改写为"**不可得（快照未留存；仅能确认这 3 天发生过 5 次同型重启）**"，不能写成"同型已证实"，也不应写成"已排除"。

### 3.9 与 G2 的行号重叠（供 plan 排串行）

G2（`evidence/research/design-g2-gate-reminder-wiring-20261009.md`）计划：给快照加 `blockedOnHuman`，在 `readMonitorState` 的 `return` 之前计算，新增一行渲染在 attention 循环之前。

**先说一处必须纠正的锚点**：G2 文档写的 `MonitorSnapshot（:488-495）`、`MonitorAutopilot（:155-166）` 与当前 HEAD 不符（实测 `MonitorAutopilot` `:156-168`、`MonitorSnapshot` `:170-176`）；G2 引的 `monitor.ts:596-609`（tick 扫描）与 `:635 tickStale`、`:724-749`（attention）当前仍然准确。G2 的编辑落点应按实测重锚为 `:156-176`（类型）、`:382-386`（采集 + return）、`:707-727`（渲染插入点）。

**重叠判断（G4 候选改动点 vs G2 落点）**：

| G4 落点（候选） | G2 落点 | 重叠 |
|---|---|---|
| `MonitorSnapshot` 类型块 `:170-176`（加 `collectedAtMs`/tick 计数类字段） | `MonitorAutopilot :156-168` + 同一类型区（它也要加 `blockedOnHuman`） | **同区（156-176 共 21 行）**；若两边都在一次 edit 里改这一段，会互相 rebase |
| `readMonitorState` 采集与 `return` `:382-386` | "compute 位置：`readMonitorState` return 之前" | **同几行（`:386` 的返回对象）**，必串行 |
| `renderMonitorLines` 头部行 `:673`（把采集时刻放进首行） | 插入点 `:707-727`（autopilot enabled 分支内、attention 之前） | 同函数、不同行；若 G4 把年龄戳并到 `autopilot:` 行（`:717`）则与 G2 插入点相邻 1 行 |
| 生命周期段 `:805-853`（重臂/心跳） | 不涉及 | 不重叠 |
| 测试：`test/suite/autopilot-monitor.test.ts`（G2 加 blockedOnHuman 用例；G4 加跟随/年龄戳用例） | 同一文件 | 同文件、不同用例，冲突成本低 |

⇒ 建议：**G2 → G4 串行**（或 G4 独占 `:673` 首行 + `:805-853` 生命周期段，G2 独占 `:707-727`，并把 `:382-386` 返回对象的改动合并到先落地的一方）。plan 里不要并行改 `monitor.ts`。

---

## 4. 结论 → 决策映射

- **D1（钉死）**：`/mw restart` 与面板冻结**没有直接因果**。重启只杀/起 serve 及其子进程，写 `.mw/mw.pid`(`mw.py:270`)、`.mw/serve.meta`(`:272`)、`.mw/conductor.pid`(`conductor.py:6625-6627`)、`launcher-beat.<pid>`(`launcher.py:786`)，**不触碰 pi 进程**；10-09 该窗口无任何 `session_start`/`/reload` 痕迹（`.mw/window-model` mtime 09-23 17:53:28）。⇒ G4 不要围绕"重启"做设计，而要围绕"帧必须自证新鲜"。
- **D2（证伪）**：`launcher-beat.<pid>` 身份耦合**不存在**（TS 侧 0 命中，§3.3）。reflect 记录的首要嫌疑与长期处置项"不缓存 beat 文件名、改目录扫描取最新"**直接删除**。
- **D3（钉死）**：PID 段每 tick 重读（§3.4）；"新 PID"不是活性证据。⇒ G4 的 VC 不能用 PID 段做判据，必须用 `workers`/`gates` 这类动态段 + 帧内采集时刻戳。
- **D4（钉死，现象约束）**：可见的陈旧帧 ⇒ 循环仍在跑（停表会清 widget：`stopMonitor:847-853` → `console.ts:669-677` → `interactive-mode.ts:2101-2108` → `tui-main-screen.ts:331-364`），且每次帧尝试都在"改动 widget 之前"失败/被吞。⇒ 该修的代码点是 `monitor.ts:829-832`（不要用裸 catch 丢掉整帧：失败也要产出一个"带诊断的降级帧"），以及 tick 内两个未受保护的读（`worker-store.ts:119`、`mw-runner.ts:85`）与 `:438-439` 的 finally（读失败必须降级而不是跳过渲染）。
- **D5（钉死）**：快照无自证字段，`MonitorAutopilot.tickStale`(`:635`)/`formatDuration`(`:651-658`) 是可复用的先例（§3.5）。⇒ G4 加"绝对采集墙面时刻（+ 可选 tick 计数）"；"在帧内算年龄"无效（活 tick 恒为 0）。
- **D6（留作真 bug，非本型事故触发）**：S2 重激活不可重挂（`monitor.ts:825` + `loader.ts:412-441` 工厂复用 + `interactive-mode.ts:518-520/2160` 清 widget + `runner.ts:552-556`）会让面板在 `/new`、`/resume`、`/fork`、`/import` 后**永久消失**（不是冻结）。⇒ 与 D1 的重臂挂点合并处理（`session_shutdown` 停表 / `autoStartMonitor` 检测 ctx 变化后 stop+start），并补 `autopilot-monitor.test.ts:761-765` 的反向用例。
- **D7（证据口径）**：reflect 表 3 行"待核"应改写为"快照未留存，不可得；仅确认 3 天 5 次同型重启"（§3.8）；"重启时点 = 冻结时点"的表述应改为"冻结窗口 [15:21:13, 16:37:22]"（§1.1）。
- **D8（排期）**：G2 与 G4 都必须改 `monitor.ts` 的 `:156-176` 类型区与 `:382-386` 返回对象 ⇒ 串行（G2 → G4）。

## 5. 数据缺口

1. **冻结起始时刻不可得**：面板帧无采集时刻戳，`.mw`/会话面也没有逐 tick 心跳；只能给出窗口 [15:21:13, 16:37:22]。⇒ 本卡不能把触发语句钉到某一行；D4 给的是"必须收紧的代码点"而不是"已确认的触发点"。要补证据只能靠 G4 落地的年龄戳（下一次复现即可定性）。
2. **tick 异常不可得**：`monitor.ts:829-832` 无日志/计数，10-09 的运行期异常没有留下任何痕迹（pi 无 TUI 日志，`~/.pi/agent/` 下无 log 目录，`.mw/*` 无相关行）。⇒ 若要事后可诊断，G4 应把"最近一次 tick 失败的时刻/错误摘要"放进帧或落一个 best-effort 诊断文件（当前 `monitor.ts` 全文无写路径）。
3. **共享冲突层面不可复查**：S3 的两处读在事后实测均成功（§2.5），无法回放 10-09 的瞬时错误码。
4. **历次（09-23/09-25/09-26）面板状态不可得**：见 §3.8。
5. **bundle 与源码的一致性已核（bundle = HEAD 逻辑等价）**，但不能排除"11:07 之后源码又改过 monitor 而 E2 未重装"的窗口；10-09 11:07:35 之后的源码改动均未进入 E2 运行实例。

---

[VERIFY] RQ-4: TS/JS 侧读 `launcher-beat` 命中=0（src/dist/全局 bundle 三处 grep 合计 0，Python 侧 1 写者/1 读者）；monitor tick 的裸 catch 点=1（`monitor.ts:829-832`）；tick 内未受保护读调用=2（`worker-store.ts:119`、`mw-runner.ts:85`）+ finally 内 unguarded close=1（`monitor.ts:438-439`）；停止路径=1（`monitor.ts:847-853`，唯一生产调用 `console.ts:669-677`），且停表会清 widget（`interactive-mode.ts:2101-2108` + `tui-main-screen.ts:331-364`）⇒ 可见陈旧帧必然来自"活循环 + 每帧失败"；实测面板同路径对 E2 文件 `WorkerStore.readAll()` = parsed 593（写卡时）/ 621（复跑时），running 2、runnable 2（两次一致）；冻结窗口 = 15:21:13→16:37:22 = 4,569 s ≈ 1,142 个 4 s tick；E2 `.mw` 现存 beat 世代=12，其中 09-23/09-25/09-26 三天同型重启=5 次；PM 会话 jsonl 891 条含 compaction 4 次、只有 1 个 session 头、提及 monitor 的 user 消息=2 条且均在 10-09；`.mw/window-model` mtime=2026-09-23T17:53:28（10-09 无 session_start/model_select 写入）。