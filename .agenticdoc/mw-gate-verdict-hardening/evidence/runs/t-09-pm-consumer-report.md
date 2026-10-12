# T-09 回执：G2 PM 侧消费者（ledger → `deliverPmAlert`）+ G4 `session_shutdown` 停表

- key: `mw-gate-verdict-hardening` · 卡: `tasks/T-09-pm-consumer.md`（blocked-by T-03）
- 日期: 2026-10-10 · 实测工作树 HEAD: `776b82d7f`（= 任务文本给的本轮基线）
- 覆盖 AC: **AC-005**（PM 侧送达半边）、**AC-018** · VC: **VC-007**（`pushed=true`）、**VC-023**
- 落地决策: **D-005**（判定 Python / 投递 TS）、**D-006**（ledger `phase:"remind"`）、**D-010**（`gate.key` 作用域 + 会话去重）

## 0. 开工前基线核对（原文）

```
$ git rev-parse --short HEAD
776b82d7f
$ git status --porcelain -- packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
 M packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts
 M packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts
```

两文件在开工时已带 T-17/T-19/T-22 的**未提交**改动（已收口、已 ack）。本卡在其之上继续加，**未回退**任何既有改动（全程未跑 `checkout`/`reset`/`stash`/`clean`，未 `git add`）。
`T-03` 前置已落地：`packages/multi-workers/autopilot/timeline.py:105` 的 `EVENT_TYPES` 含 `"gate-reminder"`（实测 grep 命中）。
`test/suite/autopilot-monitor.test.ts` **存在**（`Get-ChildItem -Recurse -Filter '*monitor*'` 唯一命中），卡里的 [VERIFY] 路径按原文可跑。

## 1. 改动面（2 文件，未动 `ui-bridge.ts`）

| 文件 | 改动 |
|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts` | +5 处：① `:5` 新增 `import { stopMonitor } from "../autopilot/monitor.ts"`；② `:753` 新增 `GateReminder` 接口 + `:768` `GATE_REMINDER_ENTRY_TYPE` + `:774` `readGateReminders()`（只读 ledger，跳坏行）；③ `:833-851` poll 循环新增去重状态（`reminderWatermark` 开窗高水位、`unsequencedSeen`、`reminderHistoryRead`）；④ `:945-990` 新增一个**读取分支**（在既有 `workerStore` 终态回读之后，仅追加）；⑤ `:1101-1104` 既有 `session_shutdown` 处理器内追加 `stopMonitor()`（不新增第二个注册，避免覆盖既有的 poll-loop 停表）。 |
| `packages/coding-agent/test/extensions/agent-team-loop.test.ts` | 新增 describe `startWorkerPollLoop gate reminders (G2)`（`:2409`，6 用例，`:2480/:2506/:2522/:2544/:2566/:2582`）+ 新增 it `session_shutdown stops the monitor panel and leaves no timer (AC-018/VC-023)`（`:4636`）。**只加用例，未改既有断言**。 |
| `.../pm/ui-bridge.ts` | **未改**。幂等做在调用方（水位），因此不需要动 T-22 刚动过的文件。 |

契约遵守：只**读** `auto-decisions.jsonl`（`fs.readFileSync`，全文无写该文件的 API 分支）；未碰 `packages/multi-workers/**`；未改 `deliverWorkerResult`（`ui-bridge.ts` 原样）。

### 判据落点（`文件:行号`）

- ledger 路径: `pm-orchestrator.ts:775` `path.join(agenticdocRoot, "_autopilot", AUTO_DECISIONS_FILE)`（`AUTO_DECISIONS_FILE` 与 Python 单写者同名，`:494`）。
- 只取 `phase == "remind"`: `pm-orchestrator.ts:798`。
- 幂等水位: `pm-orchestrator.ts:848`（进程内 `unsequencedSeen` 只兜底无 `seq` 行）、`:944`（开窗高水位）、`:974`（`if (reminder.seq <= reminderWatermark) continue`）。
- 会话持久化: `:981` `pi.appendEntry(GATE_REMINDER_ENTRY_TYPE, {seq,gateId,n})`；重启回读 `:953-961`（`ui.ctx.sessionManager.getEntries()`，先例 `console.ts:75` / `restoreWatch` 同机制）。
- 多窗口作用域: `:966-970`（`gateKey !== "" && gateKey !== watch.key ⇒ skip`；`!watch.key ⇒ skip`）。
- 送达原语: `deliverPmAlert`（`ui-bridge.ts:131`，`triggerTurn` 在 `:139`），本卡未复制判定（TS 侧 0 阈值/0 gate 文件读取）。
- G4 停表: `:1101` `pi.on("session_shutdown", () => { clearInterval(pollHandle); stopMonitor(); })`；`stopMonitor`（`monitor.ts:847`）非活动时直接 `return false`、**不清 widget**（满足"不清空非活动状态"）。

## 2. `[VERIFY]` 实测（原文，命令在 `packages/coding-agent` 下运行）

```
$ node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
...
 Test Files  1 passed (1)
      Tests  184 passed (184)
   Duration  5.18s
```

```
$ node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts
 RUN  v4.1.9 H:/git/Multi-Workers/packages/coding-agent
·····················
 Test Files  1 passed (1)
      Tests  21 passed (21)
   Duration  998ms
```

新增用例逐条绿（`--reporter=verbose -t "gate reminders"` 与 `-t "session_shutdown"` 的用例名）：

- `startWorkerPollLoop gate reminders (G2) > delivers a new remind row once and never replays it on later ticks (VC-007)`
- `... > does not replay reminders that predate a fresh window (no-replay baseline)`
- `... > resumes from the recorded session watermark, delivering only newer rows`
- `... > scopes keyed reminders to the watched key and still delivers keyless ones (D-010)`
- `... > stays silent without a watched key`
- `... > tolerates a torn ledger line without crashing the tick`
- `pmActivate lifecycle (m3) > session_shutdown stops the monitor panel and leaves no timer (AC-018/VC-023)`

回归（所有 import `pm-orchestrator.ts` 的测试文件，6 个）：

```
$ node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts \
    test/extensions/agent-team-loop-pm-state-sync.test.ts \
    test/extensions/agent-team-loop-profile-injection.test.ts \
    test/suite/autopilot-console.test.ts test/suite/autopilot-protocol.test.ts \
    test/suite/worker-dispatch-guard.test.ts
 Test Files  6 passed (6)
      Tests  269 passed (269)
```

全量检查：

```
$ npm run check
EXIT=0
Checked 1110 files in 614ms. No fixes applied.
> check:pinned-deps / check:ts-imports / check:shrinkwrap / check:install-lock:coding-agent / tsgo --noEmit / check:browser-smoke
（全部通过，无输出即无错误）
```

## 3. 非空洞对照（摘掉判据 ⇒ 指名用例转红；每次跑完已还原，`COUNTERFACTUAL` grep = 0）

### A1（幂等水位）— 摘掉 `pm-orchestrator.ts:974` 的 `if (reminder.seq <= reminderWatermark) continue;`

```
 FAIL  test/extensions/agent-team-loop.test.ts > startWorkerPollLoop gate reminders (G2) > delivers a new remind row once and never replays it on later ticks (VC-007)
AssertionError: expected [ …(3) ] to have a length of 1 but got 3
 Tests  1 failed | 183 skipped (184)
```

⇒ 同一 ledger 行（`seq=1`）在 3 个 tick 内被推 **3** 次。水位恢复后同用例绿（1 次）。
（对照 A1 变异同时覆盖"只读分支每次 tick 重读整表"的情形：去重若不生效，append-only 每 tick 都会被重新投递。）

### A2（开窗不重放历史）— 摘掉 `pm-orchestrator.ts:944-947` 的开窗高水位播种

```
 FAIL  ... > does not replay reminders that predate a fresh window (no-replay baseline)
- Expected
+ Received
- []
+ [ "[mw] 门提醒（1）：gate gate-old（kind=stalled，key=key-a）已 pending 超阈…" ]
 Tests  1 failed | 183 skipped (184)
```

⇒ 去掉播种后，开窗前已在 ledger 的 `remind` 行被重放。恢复后绿。

### B（G4 `session_shutdown` 停表 / VC-023）— 摘掉 `pm-orchestrator.ts:1103` 的 `stopMonitor()`

```
 FAIL  test/extensions/agent-team-loop.test.ts > pmActivate lifecycle (m3) > session_shutdown stops the monitor panel and leaves no timer (AC-018/VC-023)
AssertionError: expected true to be false
 Tests  1 failed | 183 skipped (184)
```

⇒ 停表 hook 缺失时 `isMonitorActive()` 仍为 `true`（panel 残留、interval 未清）。恢复后绿（`isMonitorActive()===false`，`vi.getTimerCount()===0`，widget 收到 `undefined` 清屏）。

### 对照后还原校验

```
$ Select-String -Path src/extensions/agent-team-loop/pm/pm-orchestrator.ts -Pattern 'COUNTERFACTUAL'   # 0 命中
$ Select-String -Path ... -Pattern 'reminder.seq <= reminderWatermark|stopMonitor\(\)'
974:					if (reminder.seq <= reminderWatermark) continue;
1103:		stopMonitor();
```

## 4. AC / VC 映射

| AC/VC | 用例 | 判据落点 |
|---|---|---|
| AC-005（PM 侧可见推送）/ VC-007 `pushed=true` | `delivers a new remind row once …` | `:945` 读 `phase:"remind"` ⇒ `:986` `deliverPmAlert`（`triggerTurn` 实测 `options[0].triggerTurn === true`） |
| AC-005（不重复）/ AC-014 | `never replays it …` + 对照 A1/A2 | `:944` 开窗高水位 + `:974` `seq <= watermark` + `:981` session entry |
| D-010（多窗口作用域） | `scopes keyed reminders …`；`stays silent without a watched key` | `:966-970`（keyed 按 `watch.key`；keyless 至少要求本窗口在 watch） |
| 重启/恢复不翻倍 | `resumes from the recorded session watermark …` | `:953-961` 回读 `GATE_REMINDER_ENTRY_TYPE` 条目，把水位降到"最后一次已投递 seq" |
| 健壮性（坏 ledger 不拖垮 poll） | `tolerates a torn ledger line …` | `:783-790` `JSON.parse` 失败 `continue` |
| AC-018 / VC-023（会话替换后不永久消失） | `session_shutdown stops the monitor panel …` + 对照 B | `:1101-1104` `stopMonitor()`；`session_start` 的 `autoStartMonitor(ctx, projectDir)`（既有）负责下一会话重挂 |

## 5. 已知边界 / 残余（诚实记录）

1. **keyless（stage 级）门的跨窗口去重是不完整的**：本卡的写面只有 `pm-orchestrator.ts`/`ui-bridge.ts`，且硬规则要求"只读 ledger、不写协调文件"。`gate.key == ""` 的提醒由"任一在 watch 的窗口"投递，去重靠**本进程水位 + 本会话 session entry** ⇒ 同一行在本窗口内只推一次、重启不重放；但**两个窗口同时 watching** 时，各自会推一次（跨窗口 keyless 去重需要共享写者，超出本卡写面）。`gate.key` 非空的提醒已按 `watch.key` 严格作用域，不存在该问题。design D-010 把该语义压在"消费侧 session entry"上，实现按此落地；跨窗口 keyless 的残余登记为已知边界，未声称已闭合。
2. **开窗高水位的取舍**：新窗口开窗前已存在的 `remind` 行视为历史，不重放（对照 A2 即该判据）。若某行在窗口关闭期间产生、且本会话**无**已投递记录，则它不会被补投（重启路径靠 session entry 承担补投：有记录时水位降到已投递点，窗口关闭期间新增的行会被投递；全新窗口不补投历史）。
3. **本卡不含 T-07（Python 判定/生产者）**：实测 `packages/multi-workers/autopilot/conductor.py` 当前无 `_remind_pending_gates`/`phase:"remind"` 命中 ⇒ 生产侧尚无 `remind` 行；本卡用例用合成 ledger 行覆盖消费路径，**端到端（conductor 写 → extension 推）未在真实项目上观测**。
4. **G4 的 `console.ts:690-693` 扩展点**：本卡只加 `stopMonitor()` 停表；未调用 `resetMonitorSuppression()`（那会覆盖用户显式 `/autopilot monitor off` 的会话级 opt-out）。AC-018 的重挂由既有 `autoStartMonitor` 在 `session_start` 完成。
5. **未跑**：`npm run build`、`npm test`、全量 vitest（按硬规则）；Python 侧 pytest 未跑（本卡未改 Python）。

## 6. 协作约束

- 全程未 `git add`/commit；未跑 `reset --hard`/`checkout .`/`clean -fd`/`stash`。
- 未碰 `_workers.parallel`/`_workers.acked`/`_index.parallel` 等协调文件，未 kill 进程。
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` 保持 T-22 原状（本卡未编辑）。
- 报告副本：`.agenticdoc/mw-gate-verdict-hardening/evidence/runs/t-09-pm-consumer-report.md`。
