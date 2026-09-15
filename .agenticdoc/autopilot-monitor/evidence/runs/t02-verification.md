# T-02 Verification Run (2026-09-11)

Key: autopilot-monitor | Task: T-02 L0 静态扫描 + changelog + 构建部署 + L2 双 widget 验证
扫描对象：T-01 产出（monitor.ts / console.ts 本任务零改动，git 工作区中两者的未提交修改均来自 T-01）
工作目录：`packages/coding-agent`（rg 扫描）、`packages/multi-workers`（build）

## L0

[VERIFY] VC-009: write_api_calls=0, persist_writes=0 — PASS

rg 原始输出（三条指定扫描命令，2026-09-11）：

```
$ rg -n "writeFile|appendFile|writeSync|rmSync|mkdirSync|renameSync|openSync" src/extensions/agent-team-loop/autopilot/monitor.ts
（零匹配，rg 退出码 1 = no matches found）

$ rg -n "writeFile|appendFile|writeSync|rmSync" src/extensions/agent-team-loop/autopilot/console.ts
（零匹配，rg 退出码 1 = no matches found）

$ rg -n "config.json" src/extensions/agent-team-loop/autopilot/monitor.ts src/extensions/agent-team-loop/autopilot/console.ts
src/extensions/agent-team-loop/autopilot/monitor.ts:28: * on/off state lives only in module memory (AC-009), never in config.json.
src/extensions/agent-team-loop/autopilot/monitor.ts:63:	/** False while _autopilot/config.json is absent or invalid — autopilot
src/extensions/agent-team-loop/autopilot/monitor.ts:151:	// intent (enabled/paused) from config.json, whose absence means "never
```

辅助扫描（定位 console.ts 唯一持久化写路径的调用点，确认 monitor case 不经手）：

```
$ rg -n "saveConfig|readConfig" src/extensions/agent-team-loop/autopilot/console.ts
49:	readConfig,
52:	saveConfig,
279:	const cfg = readConfig(projectDir);
284:	const saved = saveConfig(projectDir, { ...cfg.config, enabled });
331:	const cfg = readConfig(projectDir);
336:	const saved = saveConfig(projectDir, { ...cfg.config, paused });

$ rg -n "writeFileSync|saveConfig" src/extensions/agent-team-loop/autopilot/status-model.ts | Select-Object -First 10
191:export function saveConfig(projectDir: string, config: AutopilotConfig): { ok: true } | { ok: false; error: string } {
208:		fs.writeFileSync(tmp, `${JSON.stringify(ordered, null, 2)}\n`, "utf8");
```

结论（AC-008 只读承诺 + AC-009 内存态）：
- monitor.ts 对全部写 API（writeFile/appendFile/writeSync/rmSync/mkdirSync/renameSync/openSync）零匹配 → write_api_calls=0。
- console.ts 对写 API 同样零匹配；唯一持久化写 saveConfig（实际 fs.writeFileSync 位于 status-model.ts:208，写临时文件后原子改名）在 console.ts 的调用点仅两处：L284（cmdSetEnabled，enable/disable 路径）与 L336（cmdSetPaused，pause/resume 路径）。cmdMonitor（monitor case）不含任何 saveConfig/写调用 → monitor 路径 persist_writes=0。
- `config.json` 的 3 处匹配全在 monitor.ts 注释里，描述的是只读 readConfig 意图读取（enabled/paused，经 status-model.ts readConfig）；monitor 开关状态仅存于模块内存变量（monitor.ts 模块级 monitorTimer/monitorApply，AC-009），无任何 config.json 写入。

## L2

[VERIFY] VC-010: distinct_widget_ids=2 — PASS（harness 级测试，未走 pending manual）

测试文件：`packages/coding-agent/test/suite/autopilot-monitor.test.ts`（T-02 追加，未改 src/）
测试名：`VC-010: the watch widget and the monitor panel render under two distinct ids on the same UI — distinct_widget_ids=2`

方法：同一 fake ui（keyed Map 记录 setWidget）上，先驱动 watch widget 生产渲染路径（ui-bridge.ts `setWatchWidget` → `WATCH_WIDGET_KEY` = "agent-team-loop-watch"），再经 `/autopilot monitor on` 命令路径（console.ts `cmdMonitor` → `MONITOR_WIDGET_ID` = "agent-team-loop-monitor"），断言：
- setWidget 调用恰好覆盖两个不同 id（agent-team-loop-watch / agent-team-loop-monitor），各自帧内容完好、互不覆盖；
- 两 widget 均 belowEditor 叠放（D-003）；
- 交错刷新（monitor tick 重渲染 + watch 重渲染）后两 id 各自保持最新帧；
- `/autopilot monitor off` 仅清除 monitor id，watch 面板保留。

vitest 原始输出（首次全绿运行）：

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

···········

 Test Files  1 passed (1)
      Tests  11 passed (11)
   Start at  17:06:26
   Duration  557ms (transform 140ms, setup 0ms, import 282ms, tests 90ms, environment 0ms)
```

（T-01 既有 10 用例 + T-02 新增 VC-010 用例共 11 条；邻接回归 autopilot-console.test.ts + agent-team-loop.test.ts 147/147 通过；`npm run check` 全量通过，biome 自动修复 1 个文件即本测试文件的格式）

实机/双窗口演示不在本任务门禁内：id 契约与互不覆盖行为已由上述 harness 级测试锁定；若 PM 需要实机双面板演示，步骤——打开 pi 窗口 → `/pm-key watch <key>`（或既有 watch 开启方式）→ `/autopilot monitor on` → 预期底部 watch 面板与 monitor 面板并存、各自 4s 刷新。

## Build

`python -X utf8 mw.py build --install`（packages/multi-workers，2026-09-11 17:05 前后）— 成功，退出码 0，共 5 行输出，最后三行：

```
[mw build] installed globally: C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js
[mw build] dist rebuilt: H:\git\Multi-Workers\packages\coding-agent\dist
[mw build] Restart open pi windows to load the new bundle and dist.
```

## CHANGELOG

`packages/coding-agent/CHANGELOG.md` `## [Unreleased]` → `### Added` 末尾追加 1 行（现 L85），diff 摘要 `1 file changed, 1 insertion(+)`：

```
- Added `/autopilot monitor [on|off]`: a live bottom panel for the orchestration stack — mw serve (PID, fresh/stale, uptime), conductor (alive, enabled/paused), running workers across all keys with elapsed minutes, and pending gates with the approve/reject hint. Read-only file sources (pid/meta/config/workers/gates), 4s refresh, per-window in-memory toggle; headless sessions degrade to a notice.
```
