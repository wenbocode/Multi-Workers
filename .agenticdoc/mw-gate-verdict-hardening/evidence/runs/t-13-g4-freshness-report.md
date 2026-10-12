# T-13 回执：G4 帧自证与失败降级（AC-015/AC-016/AC-017；VC-020/VC-021/VC-022）

- Key: `mw-gate-verdict-hardening`（phase=EXECUTE）· 卡：`tasks/T-13-g4-freshness.md`
- 基线：HEAD `776b82d7f`；开工前确认 T-08 已落（`monitor.ts` 有 snapshot 级 `blockedOnHuman` + `BLOCKED_ON_HUMAN` 置顶行）且 `git diff` 无第三处并发改动。
- 状态：**done**。两个 `[VERIFY]` 全绿（26 passed / 38 passed），两组非空洞对照真跑见红。

## 0. 结论摘要

面板现在**不能撒谎**：每帧携带绝对采集墙面时刻 + 单调 tick 计数；读取失败不再被裸 catch 吞掉整帧，而是产出**降级帧**（沿用上一帧数据 + 失败时刻 + 错误摘要）；帧戳超过 3 个刷新周期未前进时首行显式 `STALE PANEL`；数据面变化 ≤2 周期跟随。**未新增任何写路径**（失败证据只落在帧内）。

## 1. 写面与改动坐标（符号名 + 实际行号）

只改了两个文件（独占写面）；`stopMonitor`、T-08 的 `blockedOnHuman`/置顶行逻辑逐字未动。

### `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`

| 位置（final 行号） | 改动 |
|---|---|
| `PANEL_STALE_MISSED_CYCLES` `:74` | 新常量 = 3（AC-015 ">3 个刷新周期"的界；注释说明这是 conductor `staleAfterMs = max(30s, pollMs*5)`/`tickStale` 机制在**面板节奏**上的实例，不复用该变量数值，因为两个是不同时钟） |
| `interface MonitorSnapshot` `:186`，新字段 `:204` 起 | `collectedAtMs?` / `tickCount?` / `stale?` / `staleDetail?` / `degraded?` / `lastErrorAtMs?` / `lastError?`（可选，手搓快照仍可构造） |
| `readMonitorState` 返回对象 `:446` | 采集即自证：`collectedAtMs: nowMs`、`tickCount: monitorTickCount` |
| `monitorHeaderLine` `:739` | 首行 = `[autopilot monitor]` + `STALE PANEL (...)` + `collected <ISO> tick N`；按优先级拼装，溢出时先截断/丢弃低优先位，保证 `STALE PANEL` 永不被长 detail 挡掉 |
| `renderMonitorLines` 首行 `:767` + 降级行 `:772` | 首行改为 `monitorHeaderLine(s)`；`degraded` 时追加 `DEGRADED: <error> (read failed at <ISO>)`（错误摘要在前，长路径/时间戳不会遮蔽它） |
| 模块级状态 `:925` / `:930` / `:936` | `monitorTickCount`（成功采集单调计数，**stop/start 均不重置**，重臂不能靠回退到 0 伪造新鲜）；`lastGoodSnapshot`（降级帧复用的上一帧，run-scoped）；`anchorAtMs`（本 run 的时间锚：最后一次成功采集，尚无成功时=run 起始；失败不推进） |
| `errorSummary` `:944` | `name: message`，空错误回退 `unknown error`，从不抛 |
| `degradedSnapshot` `:964`（边界注释 `:983`） | 有上一帧 ⇒ `{...lastGoodSnapshot, ...diagnostics}`（数据沿用、戳不前进、`stale` 按 anchor 计算）；**无上一帧（首次 tick 即失败）** ⇒ 空骨架 + 诊断（`collectedAtMs` + `lastErrorAtMs` + `lastError`），不伪造数据 |
| `startMonitor` `:1018` | 原裸 catch（`try { apply(render(readState())) } catch {}`）拆成两段：读失败 → `degradedSnapshot(...)` 后照常 `apply`；仅 widget 写入自身失败才静默重试。run 起始重置 `lastGoodSnapshot`，`anchorAtMs = nowMs()` |

### `packages/coding-agent/test/suite/autopilot-monitor.test.ts`

| 位置（final 行号） | 改动 |
|---|---|
| `flakyReadState` `:551` | 按需抛错的 `readState` 注入（不改任何文件） |
| G4 describe `:564-719` | VC-020 `:574`、VC-021 `:621`、VC-022 `:656`（含首次 tick 即失败边界 + 持续失败转 `STALE PANEL`） |
| 既有断言 `:254 / :351 / :720 / :736 / :835` | 首行现在带自证戳，`toBe("[autopilot monitor]")` → `toContain("[autopilot monitor]")`（机械改；T-08 的 `blockedOnHuman` 语义断言未动） |

## 2. [VERIFY] 命令原文与输出

命令 1：

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

[VERIFY] VC-011: age_shown=true blocked_marker=true
[VERIFY] VC-020: stamp_advances=true stale_warned=true
···········[VERIFY] VC-021: followed_within_cycles=2
[VERIFY] VC-022: degraded_frame=true silent_frames=0
···············

 Test Files  1 passed (1)
      Tests  26 passed (26)
   Start at  18:31:17
   Duration  712ms (transform 272ms, setup 0ms, import 465ms, tests 139ms, environment 0ms)
```

命令 2：

```
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts
```

```
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent

······································

 Test Files  1 passed (1)
      Tests  38 passed (38)
   Start at  18:31:18
   Duration  964ms (transform 266ms, setup 0ms, import 456ms, tests 394ms, environment 0ms)
```

附加回归（只读消费者，非卡要求）：`autopilot-gate-presentation.test.ts` 12 passed；`tsgo --noEmit` 退出 0；`biome check`（无 `--write`）两文件 Clean（未跑 `npm run check`：其 `--write` 全仓重写会踩到其它并发会话的文件）。

## 3. 非空洞对照（真跑：摘掉判据 ⇒ 转红）

控制 1（摘掉降级分支）：把 `frame = degradedSnapshot(err, now, intervalMs);` 改为 `return;`。

```
=== CONTROL 1: degraded branch removed ===
 FAIL  ... > VC-020: the absolute stamp + tick advance every tick; >3 stale periods raise STALE PANEL
 FAIL  ... > VC-022: a failing read emits a DEGRADED frame, including when the FIRST tick fails
      Tests  2 failed | 1 passed | 23 skipped (26)
```

控制 2（摘掉过期告警）：把 `const late = ageMs > intervalMs * PANEL_STALE_MISSED_CYCLES;` 改为 `const late = false;`。

```
=== CONTROL 2: stale warning removed ===
 FAIL  ... > VC-020: the absolute stamp + tick advance every tick; >3 stale periods raise STALE PANEL
 FAIL  ... > VC-022: a failing read emits a DEGRADED frame, including when the FIRST tick fails
      Tests  2 failed | 1 passed | 23 skipped (26)
```

两次控制后均已从备份还原；还原校验：无 `CONTROL-` 标记、降级分支与 stale 判据原文俱在，随后主用例复跑 26 passed。

VC-021 反向用例本身即 "0 running → N running 在 ≤2 周期内跟随"：夹具先落 1 行 `done`（面板 `workers: 0 running`），再改写为 3 行 `running`，推进 2×4000ms 后断言 `workers: 3 running (all keys)`。

## 4. 逐条交付对照

1. **帧自证**：`MonitorSnapshot.collectedAtMs`（绝对 `Date.now()`，经注入 `nowMs` 可测）+ `tickCount`（模块级单调，stop/start 不重置，`:925`）；渲染进首行 `:769/:739`。VC-020 断言戳随 tick 前进且 tick 计数递增。
2. **过期告警**：连续 **>3** 个刷新周期未前进 ⇒ 首行 `STALE PANEL (no refresh since <ISO>, <dur>)`（`formatDuration`）。判据 `ageMs > intervalMs * PANEL_STALE_MISSED_CYCLES`（恰 3 周期不告警，第 4 周期告警，用例两侧都断言）。
3. **失败不静默**：裸 catch 改为降级帧（`:964`/`:1045`），沿用上一帧数据 + `lastErrorAtMs` + 错误摘要 + `degraded` 标记；帧数增长（不丢帧）。
4. **跟随**：`MONITOR_INTERVAL_MS = 4000` 未改；VC-021 断言 2 周期内跟随。
5. **契约**：未围绕 `/mw restart` 设计；**零新增写路径**（VC-022 在失败/降级路径上仍断言 `hashTree` 不变；VC-008 三 tick 字节不变继续绿）；T-08 `blockedOnHuman` 字段与置顶行逐字未动；`stopMonitor` 未动。
6. **边界**：首次 tick 即失败（无上一帧）⇒ 空骨架 + `collectedAtMs` + 错误摘要，注释写在 `degradedSnapshot` `:958`/`:983`；用例 `:656` 覆盖，并追加"持续失败时戳不前进 ⇒ `STALE PANEL`"。

## 5. 未保护读与写面纪律

卡风险条款要求：若发现 `readMonitorState` 之外还有不受该 try 保护的读，先回报 PM，不得扩写到 `shared/worker-store.ts` / `shared/mw-runner.ts`。RQ-4 点名的三处（`worker-store.ts:119`、`mw-runner.ts:85`、`monitor.ts` `readTimelineTail` 的 `finally closeSync`）**全部在 `readMonitorState` 内**，即受 `startMonitor` 的 try 保护——本次把该 try 的失败语义从"丢帧"改为"降级帧"后，这三处任一抛出都会落到降级帧，**无需且未改** `worker-store.ts`/`mw-runner.ts`。未发现其它不被保护的独立读路径。

## 6. 并发与工作树

- 只写上述两文件；未 `commit`、未 `git add`、未 `reset/checkout/stash/clean`；未碰任何协调文件（`.agenticdoc/_workers.parallel`/`_workers.acked`），测试只用 `mkdtemp` 临时目录；未 kill 进程。
- `git status` 中其它已改文件（`conductor.py`、`pm-orchestrator.ts`、`worker-store.ts` 等）属其它并发任务，本卡未触碰。
- 依 task.md 提示：本仓库运行时为旧副本，worker 终态回读不可靠 ⇒ 以上结论**只以本机实跑输出为准**（本回执的原始命令/输出）。
