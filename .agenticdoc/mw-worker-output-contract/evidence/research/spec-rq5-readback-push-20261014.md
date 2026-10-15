# RQ5 复核：终态回读推送范围缺口（C1 锚点 / 全分支清单 / ackStore 语义 / 用例形状 / 可证伪性 / 无 I/O 放大）

- Key: mw-worker-output-contract
- Card: `tasks/T-RQ5-readback-push.md`（dispatch card `mw-dispatch-card: v1`）
- 性质：只读复核（research）。**未修改仓库任何文件**；实跑探针 1 次（命令与输出见 §7）。
- 吸收前置（未重新发现）：`evidence/readback-push-scope-gap-20261014.md`（14,191 B）、`evidence/readback-push-scope-repro-20261014.mts`（5,197 B）。
- 主源码：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（1,822 行）、`pm/ui-bridge.ts`、`shared/ack-store.ts`、`shared/worker-store.ts`。

---

## 0. 结论先行

1. **C1 两处锚点复核成立**：`notified` 是 `startWorkerPollLoop` 内的**进程级 `Set`**（`:1350`，窗口会话生命周期，无持久化、无导出），`:1436 notified.add(entry.taskKey)` 确实早于 `:1440` 的 owner 门禁 `continue`。`:1440` 把两个语义相反的抑制条件压进一条 `if`：`!watch.key`（C3，刻意静默）与 `ownerKeyOf(entry) !== watch.key`（C1，缺陷）。
2. **全分支清单 = 6 组 13 条判定**（§2）。本函数**只有 2 条投递出口**：escalation `deliverPmAlert`（`:1426`）与 terminal readback `deliverWorkerResult`（`:1459` / `:1466`）。gate reminder 走**独立**的 delivery watermark（`:1516`/`:1517`）与独立 drop 记录（`:1505`/`:1509`/`:1540`），与 `notified` 无耦合。
3. **`ackStore` 与 `notified` 不等价，ack 不参与投递**：ack 标记持久化在 `.agenticdoc/_workers.acked`（`ack-store.ts:20`，`taskKey | ackedAtIso`），只被 widget 渲染与 `ackTasks` 读写；poll loop 把它用在**唯一一处** —— `:1392` `renderWatchLines`。因此「未 ack 即补推」在本函数是**全新语义**，不与既有语义冲突，但需要新去重键（否则未 ack 的跨 key 行会每 tick 重投）。
4. **用例形状：不需要 faux provider / harness**。`startWorkerPollLoop` 只依赖 `pi.sendMessage` 与 `ui.ctx.ui.setWidget`；`packages/coding-agent/test/` 已有现成的 fake pi + 临时 root + 假时钟形状（`agent-team-loop.test.ts:1939/1970/1987`，suite 侧 `mwgal-t10-state-surface.test.ts:33/545`）。落点与 P1…P6 映射见 §4。
5. **可证伪性（AC-011 闸门）**：P3 是唯一能区分 C1 的断言（`b1` 开窗 running ⇒ 排除 C2；`watch.key` 全程非空 ⇒ 排除 C3），但 **P4 的绝对计数子句 `step4 === 1` 在 C1 修复后必然翻转为 2**（step4 是累计投递数，P3 修好后 step3=1）；此外既有回归测试 `agent-team-loop.test.ts:2053-2085`（`t0` 在 `!watch.key` 期间终态，之后 watch key-a 不得复活，断言在 `:2077`）会被「朴素后移 `notified.add`」打破 ⇒ 修法必须把 C3 与 C1 分开记账。P5/P6 只在 AC-012 选「补推开窗即终态未 ack 行」时翻转。
6. **R5 无 I/O 放大**：`:1440` 的判定分支之前只有内存/纯计算（`notified.has` `:1435`、`ownerKeyOf` `:1440` = `path.relative` + `split`）；全部文件读取（`recordWriteScopeResidualRisks`→读 `trace.log` `:1448`、`heartbeatStatsSuffix` `:1456`、`readOutputBody` `:1457`、`readSpawnFailure` `:1465`）都在门禁**之后**。记账后置的稳态增量 = 每 tick 每条未投递终态行一次 Set miss + 一次 `path.relative`。

---

## 1. 问 1：C1 两处锚点现状

### 1.1 `notified` 的声明与生命周期

`pm/pm-orchestrator.ts:1348-1357`（原文）：

```ts
	// Baseline snapshot: rows already terminal when this window opens are
	// history — never replay their summaries. Only transitions observed while
	// this session is open are notified, at most once each.
	const notified = new Set(
		workerStore
			.readAll()
			.filter((e) => isTerminal(e.status))
			.map((e) => e.taskKey),
	);
```

- **进程级、非持久化、非导出**：`const` 声明在 `startWorkerPollLoop` 函数体内（`:1337` 起）。全仓 `notified` 命中仅 `:170/:173/:178`（另一个函数 `evidenceReviewNotice` 的**入参** Set，与回读无关）与 `:1350/:1435/:1436/:1446`（本函数）。无 `export`、无 `appendEntry`、无 session entry 读写。对比之下同一函数的 gate reminder 通道用 `pi.appendEntry(GATE_REMINDER_ENTRY_TYPE, …)`（`:1523`）持久化——worker 回读**没有**对应持久化。
- **生命周期 = 窗口会话**：`pmActivate` 在 `:1644` 启动循环，`session_shutdown` 时 `clearInterval`（`:1653`）。`/reload` / session 替换后新循环重新做基线快照 ⇒ 期间终态的行全部沉底（这正是 C2）。
- **基线语义**：开窗时已终态的行直接进 `notified`，此后永不投递。

### 1.2 `:1434-1448` 实际代码（原文）

```ts
1434			for (const entry of entries) {
1435				if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
1436				notified.add(entry.taskKey);
1437				// One-shot transcript summaries fire only for this window's watched
1438				// key; without a watched key the window stays silent (no cross-window
1439				// broadcast). The widget above still shows current state either way.
1440				if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
1441				// Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
1442				const taskDir = path.dirname(entry.taskPath);
```

顺序即缺陷：`:1436` 的语义是「已作为回读投递过」，而 `:1440` 的 `continue` 表示「不投递」。两者叠加 ⇒ 非 watch key 的终态行被记账为已推送，且**永久**（同 key 后续接管时 `:1435` 直接 `continue`）。

补充：`:1440` 的门禁只认 `ownerKeyOf`，**不认** `watch.dispatchedTaskKeys`（跨 key 显式派发的任务）。同一函数里 escalation 分支（`:1416`）用的是 `!watch.key || (ownerKey !== watch.key && !owned)`，即「watch key ∪ 本窗口派发」。**这是本函数内的第二处不对称**：本窗口显式跨 key 派发的任务，其 risk escalation 会推送，但其终态回读不会。

### 1.3 `entry` 的字段来源与 `ownerKeyOf`

`entry` 来自 `workerStore.readAll()`（`:1400`，队列文件 `.agenticdoc/_workers.parallel`），类型 `WorkerEntry`（`shared/worker-store.ts:14-28`）：`taskKey | status | cli | provider | taskPath | dispatchedAt | updatedAt | model | origin`（7..9 列，`:40-47`）。

`pm/ui-bridge.ts:457-460`（原文）：

```ts
export function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string {
	const rel = path.relative(agenticdocRoot, path.normalize(entry.taskPath));
	return rel.split(path.sep)[0] ?? "";
}
```

即「`taskPath` 相对 agenticdoc 根的第一段」。`{root}/{key}/workers/{task}/task.md` → `key`；根级 legacy 行 → 自己的 taskKey（永不匹配任何 watch key）。注意：`worker-store.ts:59` 另有一个正则版 `workerOwnerKey`（`WORKER_PATH_KEY_RE`），回读门禁用前者。

### 1.4 轮询间隔常量

`pm/pm-orchestrator.ts:66`：

```ts
const POLL_INTERVAL_MS = 4000; // < 5s per AC-001
```

作为默认值出现在签名 `:1345`：`pollIntervalMs = POLL_INTERVAL_MS,`。模块私有（未导出）；`pmActivate` 用默认值（`:1644`），测试/探针显式传小间隔。

---

## 2. 问 2：`startWorkerPollLoop` 全部投递/抑制分支（核心清单）

区间：`setInterval` 回调 `:1385-1548`。下表按执行顺序，「行号」为 `pm/pm-orchestrator.ts`。

### 组 A — 每次 tick 的 widget（非投递，但先于所有判定）

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| A1 | `:1389` + `:1390-1394` | `watch.key` 为真 | `applyWatchWidget(renderWatchLines(...))`（`:1392` 读 `ackStore`），`widgetShown = true` |
| A2 | `:1395-1397` | `watch.key` 为空**且** `widgetShown` | 清 widget |

### 组 B — 发散风险 escalation（投递出口 1）

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| B1 | `:1408` | `entry.status !== "running"` **或** `escalated.has(taskKey)` | `continue`（不投递） |
| B2 | `:1416` | `!watch.key` **或**（`ownerKey !== watch.key` **且** 非本窗口派发） | `continue`（不投递） |
| B3 | `:1418` | 无 checkpoint **或** `ck.risk === "low"` | `continue`（不投递） |
| B4 | `:1419` + `:1426-1432` | 上三条不命中（running + owned + mid/high risk） | `escalated.add` → `deliverPmAlert(...)`（**投递**，triggerTurn） |

### 组 C — 终态回读（投递出口 2；C1 所在）

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| C1 | `:1435` | `notified.has(taskKey)` **或** `!isTerminal(status)` | `continue`（不投递；`isTerminal` = done/failed/needs-clarification/lost，`:68-70`） |
| C2 | `:1436` | （无条件，落在 C1 之后） | `notified.add(entry.taskKey)` ← **记账点，早于门禁** |
| C3 | `:1440` | `!watch.key` **或** `ownerKeyOf(entry) !== watch.key` | `continue`（**不投递**；本条同时承担 C3 与 C1 两个子因） |
| C4 | `:1448` | 上条不命中 | `recordWriteScopeResidualRisks(...)`（副作用：可能写 dispatch-alarm ledger；读 `trace.log`） |
| C5 | `:1456-1459` | `readOutputBody(taskDir)` 返回非空 | `deliverWorkerResult(header + body + PM_CONTINUE_HINT)`（**投递**） |
| C6 | `:1461-1474` | body 为空 | `deliverWorkerResult(spawnFailure ? … : 无 output.md 摘要… + PM_CONTINUE_HINT)`（**投递**） |

对照：组 B 的「owned」包含 `dispatchedTaskKeys`，组 C 不包含（见 §1.2 补充）。

### 组 D — gate reminder（独立通道，投递出口 3）

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| D1 | `:1504-1506` | `!watch.key` | `recordDroppedGateReminder(..., "no-watch")` 后 `continue`（不投递，**但留可见记录**） |
| D2 | `:1508-1510` | `reminder.gateKey !== ""` **且** `!== watch.key` | `recordDroppedGateReminder(..., "other-key")` 后 `continue`（不投递，留记录） |
| D3 | `:1513-1517` | `reminder.seq > 0` **且** `seq <= reminderWatermark` | `continue`（不投递；watermark 是**独立**去重轴） |
| D4 | `:1518-1520` | `seq === 0` **且** `unsequencedSeen.has(dedup)` | `continue`；否则 `unsequencedSeen.add(dedup)` 放行 |
| D5 | `:1523-1527` + `:1529-1534` | 上三条不命中 | `pi.appendEntry(GATE_REMINDER_ENTRY_TYPE, {seq,…})` → `deliverPmAlert(...)`（**投递**，持久化去重） |

### 组 E — reminder 的一次性 resume 水位（组 D 的前置）

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| E1 | `:1481-1497` | `!reminderHistoryRead`（每会话一次） | 扫 session entries 的 `GATE_REMINDER_ENTRY_TYPE` 取最大 `seq`，写入 `reminderWatermark`（`delivered > 0` 时） |
| E2 | `:1379-1382` | 开窗一次性 | `reminderWatermark = max(ledger seq)`（开窗基线） |

### 组 F — tick 级异常兜底

| # | 行号 | 判定条件 | 结果 |
|---|---|---|---|
| F1 | `:1536-1546` | 本 tick 抛错 | `recordDroppedGateReminder(..., "read-error", msg)`（进程内按 `${gateId}:${n}:${reason}` 去重，`:173-178`），不投递 |

### 通道侧（不是本函数的分支，但决定投递可见性）

| 项 | 行号 | 说明 |
|---|---|---|
| triggerTurn 合并 | `pm/ui-bridge.ts:175-187`（`deliverPmAlert`）→ `:189-193`（`deliverWorkerResult` 直接转调） | `pi.sendMessage(msg, { triggerTurn: true })`；注释 `:168-174`：idle PM 立刻起 turn，**streaming PM 的文本被 steer 进当前 turn**（即合并/不成为独立可见消息）。这是「并发放大器」，不是 C1 主因；合并比例未量化（母报告 §6 已声明）。 |
| ack 通道 | 不在本函数 | 见 §3。 |

**小计**：不投递判定 11 条（A2、B1、B2、B3、C1、C3、D1、D2、D3、D4、F1），投递出口 3 条（B4、C5/C6 同属一条投递通道、D5）。其中只有 C3 是 C1 缺陷所在，且它把 C1（owner 不匹配）与 C3（`!watch.key`）合并。

---

## 3. 问 3：`ackStore` 的语义位置

- **存储**：`shared/ack-store.ts:20` `this.filePath = path.join(agenticdocRoot, "_workers.acked")`；行格式 `taskKey | ackedAtIso`（`:9-11`、解析 `:59-71`）。**持久化**（跨窗口/跨会话），**项目级**（不是 per-key）。写入走 `.mw/workers.lock` + tmp+rename 原子替换（`:44-56`）。
- **写入者（2 处）**：`pm/ui-bridge.ts:654` 与 `:681`（都在 `ackTasks`，`:639` 起）——入口是 `/mw ack` 与 `ack_worker_result` 工具（`:2467-2497`）。worker 模式不注册工具，worker 不能自 ack。
- **读取者（3 处）**：`ui-bridge.ts:713`（`renderWatchLines`：unhandled = terminal-非-done-未 ack；history = done ∪ acked）、`ui-bridge.ts:649`（`ackTasks` 的 "all" 展开）、`ui-bridge.ts:2519`（`list_tasks` 的 `acked` badge）。
- **`startWorkerPollLoop` 与 ack 的关系**：唯一一处是 `:1392` 把它传给 `renderWatchLines` 渲染 widget。函数体内没有任何 `ackStore.ack` / `ackStore.readAll` 判定（§7 命令 B 输出只有 2 行，其一为参数声明、其一为 `:1392`）。**ack 既不触发也不抑制回读投递**。
- **与 `notified` 的关系**：
  - `notified` = 进程级、窗口会话、仅 `taskKey`、语义「本窗口已投递过」、覆盖全部终态（含 done）。
  - `acked` = 持久化、项目级、仅 `taskKey`、语义「PM 已处理完」、widget 生命周期的 unhandled/history 分界。
  - **不等价**：不 ack 的行可能已投递（`done` 行不需要 ack 即进 history）；已 ack 的行也可能从未投递（C1 缺陷现场：既未推送也未 ack）。
- **对 AC-012 的前提结论**：「未 ack 即补推」是**新增**语义，与既有代码无冲突（没有任何既有分支读 ack 来决定投递）。但它**不能**直接替换 `notified`：若只按「未 ack」判定，一个一直不被 ack 的跨 key 终态行会**每 tick 重投**。因此 S6 必须定义 `notified`（投递记账）与 `acked`（处理记账）的分工，并给出补推去重键（R6：`taskKey` vs `taskKey + run_id`）。当前两者都只按 `taskKey` 去重，`run_id` 维度在回读通道内**不存在**（`WorkerEntry` 无 run 字段；run 身份在 `shared/run-store.ts`，回读路径未接入）。

---

## 4. 问 4：用例化的可行形状（不写实现，只给落点与断言）

### 4.1 结论：不需要 harness / faux provider

`startWorkerPollLoop` 的外部依赖只有 `pi.sendMessage`（投递）、`pi.appendEntry`（gate reminder，本用例可不给）、`ui.ctx.ui.setWidget`（widget）、以及文件系统。它**不调用模型**，`triggerTurn` 在测试里只需断言透传。因此复用 `createHarness`（`test/suite/harness.ts:110`，faux provider）是多余的，且会引入不必要的 provider 装配；正确形状是「纯文件夹具 + 假 pi + 假时钟」。

### 4.2 落点（文件级）

推荐：新建 `packages/coding-agent/test/suite/mwoc-t01-readback-delivery-scope.test.ts`（沿用本仓 key 前缀 suite 命名先例 `mwds-t04-deliverable.test.ts`、`mwgal-t10-state-surface.test.ts`）。
备选：并入既有 `describe("startWorkerPollLoop summary scoping")`（`packages/coding-agent/test/extensions/agent-team-loop.test.ts:1938`）——该块已有全部夹具。
`AGENTS.md` 的 `test/suite/regressions/<issue-number>-*.test.ts` 命名只在有 GitHub issue 号时适用；本 key 无 issue 号，故走 key 前缀。

### 4.3 可复用夹具（逐条 `文件:行号`）

| 需要的东西 | 复用点 | 说明 |
|---|---|---|
| 假 `pi`（记录 `sendMessage` 内容 + options） | `packages/coding-agent/test/extensions/agent-team-loop.test.ts:1939-1950` | `messages: string[]` + `options: Array<{triggerTurn?: boolean}>`；断言 triggerTurn 透传 |
| 假 `pi.appendEntry`（若加 gate reminder 断言） | `packages/coding-agent/test/suite/mwgal-t10-state-surface.test.ts:541-547` | 同文件 `:549-590` 是完整的 suite 调用样板 |
| 假 `ui` ctx（捕获 widget 行） | `agent-team-loop.test.ts:1956-1968` | AC-013 计数断言要用 |
| 临时 `.agenticdoc` 根 | `agent-team-loop.test.ts:148-151`（`mkdtemp`）、`mwgal-t10-state-surface.test.ts:43-45`、`mwds-t04-deliverable.test.ts:91` | 根 = `<tmp>`；`agenticdocRoot` 可直接用 `<tmp>`（`mwgal` 用 `<tmp>/.agenticdoc`） |
| 队列行 + task.md + output.md | `agent-team-loop.test.ts:1970-1985`（`queueTask`，`WorkerStore.upsert`） | 最贴近探针；`taskPath = <root>/<owner>/workers/<taskKey>/task.md` |
| 原始 9 列队列行（不经过 store） | `mwgal-t10-state-surface.test.ts:103-120`（`writeWorkers`） | 与探针的 `row()` 等价；注意列顺序 `taskKey|status|cli|provider|taskPath|dispatchedAt|updatedAt|model|origin` |
| 确定性时钟 | `agent-team-loop.test.ts:2015-2017`、`mwgal-t10-state-surface.test.ts:568-571` | `vi.useFakeTimers()` + `vi.advanceTimersByTime(...)`，回调同步执行；替代探针的 `wait(TICK*N)`（消除 50ms 真实 sleep 的不确定性） |
| 循环句柄清理 | `agent-team-loop.test.ts:2024`（`clearInterval(handle)`） | 必须在 `finally` 里 |
| `watch.key` 中途切换 | `agent-team-loop.test.ts:2077` 先例 | 循环闭包持有同一对象引用，直接 `watch.key = "keyB"` 即生效 |

### 4.4 用例骨架（形状，非实现）

单个 `it`（推荐，忠实映射探针时序与对照）：

```
describe("startWorkerPollLoop terminal readback scope (mwoc AC-011/012/013)")
  it("P1..P6: terminal readback is scoped to the watched key, no premature notify", ...)
    root = mkdtemp(); store/ack/index = new *Store(root)
    rows: a1 running(keyA) | a2 done(keyA) | b1 running(keyB) | c1 done(keyC)
    pi = fakePi(); watch = { key: "keyA" }; ui = { ctx: fakeUiCtx().ctx }
    vi.useFakeTimers()
    handle = startWorkerPollLoop(pi, store, new AckStore(root), index, root, watch, ui, 100)
    -- P1 -- advance; expect writes==0
    -- P2 -- b1 -> done;  advance; expect no "[b1]" delivery (owner gate intact)
    -- P3 -- watch.key = "keyB"; advance; expect exactly one "[b1]" delivery   <-- C1 回归点
    -- P4 -- b2 -> (running->done); advance; expect "[b2]" delivered (control)
    -- P5 -- expect never "[a2]"   (open-time terminal under watched key)
    -- P6 -- watch.key = "keyC"; advance; expect never "[c1]", no extra deliveries
    clearInterval(handle); vi.useRealTimers(); rmSync(root)
```

### 4.5 P1…P6 → 测试名与断言（改造后**期望值**，即 AC-011 的判据）

| 探针断言 | 建议测试名（`it(...)`） | 改造后期望断言 | 说明 |
|---|---|---|---|
| P1 | `P1: no readback while every row is running` | `expect(deliveries).toHaveLength(0)` | 与探针一致（存量行为） |
| P2 | `P2: the owner gate still suppresses cross-key rows` | `expect(pushed("b1")).toBe(false)`，且此刻 `deliveries === 0` | **必须保留**：区分「记账后置」与「直接删掉 owner 门禁」 |
| P3 | `P3 (C1): takeover of keyB replays the un-notified terminal row exactly once` | `expect(pushed("b1")).toBe(true); expect(count("b1")).toBe(1)` | **唯一翻转项**（探针期望 `false`/0 → 改造后期望 `true`/1） |
| P4 | `P4 control: a row terminal while its key is watched is delivered` | `expect(pushed("b2")).toBe(true)`（**去掉**探针的 `step4 === 1` 绝对计数） | 绝对计数在修复后变 2（见 §5） |
| P5 | `P5 (C2): an open-time terminal row under the watched key is not replayed` | `expect(pushed("a2")).toBe(false)` | 仅在 AC-012 选「不补推」时成立 |
| P6 | `P6: an open-time terminal row under an unwatched key is not replayed` | `expect(pushed("c1")).toBe(false)` 且 `deliveries` 未新增 | 同上 |

附加断言（可选，直接服务 AC-015/AC-013）：
- P3 的投递必须带 `triggerTurn: true`（用 `agent-team-loop.test.ts:1940` 的 `options` 数组）。
- AC-013（无 watch key 时显示未回读条数 N）：用 `fakeUiCtx`（`:1956`）捕获 widget 行，或在无 watch key 分支断言一条新消息；当前代码**没有**该 surface（§7 命令 C），所以这条必须先落实现。

---

## 5. 问 5：可证伪条件的可执行化（断言是否真能区分 C1 与 C2/C3）

### 5.1 断言实现位置（探针 `readback-push-scope-repro-20261014.mts`）

| 断言 | 行号（探针文件） | 表达式 |
|---|---|---|
| P1 | `:94` | `step1 === 0` |
| P2 | `:95` | `step2 === 0` |
| P3 | `:96-100` | `step3 === 0 && !had("b1")`，detail `deliveries=${step3}, saw b1=${had("b1")}` |
| P4 | `:101` | `step4 === 1 && had("b2")` |
| P5 | `:102-106` | `!had("a2")` |
| P6 | `:107` | `step5 === step4 && !had("c1")` |

（对应探针阶段：`step1` `:76`，`step2` `:82`，`step3` `:86`，`step4` `:100`，`step5` `:104`。）

### 5.2 区分能力判定

- **P3 对 C1 是决定性的**：`b1` 在开窗时是 **running**（不在 `:1350` 基线的 terminal 快照里），因此它的静默**不可能**由 C2 解释；`watch.key` 在 P3 阶段已是 `"keyB"`（非空），因此**不可能**由 C3 解释。修复（记账后置）后 `b1` 在第一次 tick 即投递一次 ⇒ `saw b1` 由 `false` 变 `true`，`step3` 由 0 变 1。**成立**。
- **P1/P2/P5/P6 是负向断言**（零投递 / 未出现某 key），C1-only 修复不改变它们：P1（全 running）、P2（keyA watch 期间 keyB 终态）、P5（`a2` 开窗即终态，仍在 `notified` 基线）、P6（`c1` 开窗即终态且 `step5 === step4` 是**相对**比较，不受 step4 绝对值变化影响）。**成立**。
- **P4 会翻转 —— 必须指出**：P4 的判据是 `step4 === 1`，而 `step4` 是**累计投递数**。按报告自身的预测（P3 修复后 `step3 = 1`），`step4 = step3 + 1 = 2`。因此**原样搬成测试的 P4 在修复后必然失败**，尽管其语义部分 `had("b2") === true` 始终成立。改造时必须把 P4 改为存在性/增量断言（§4.5）。
- **AC-011 与 AC-012 的耦合（第二个翻转源）**：P5/P6 的「不变」只在 C1-only 修复下成立。若 AC-012 选**方案 A**（对应 key 被 watch 且该行未 ack 时补一次回读），则 `a2`（P5）必然被补推，P6 视 `c1` 的 key 是否随后被 watch 也可能翻转。**结论：AC-011 的闸门必须在「仅做 S6/C1 记账后置」的实现上评估；若 AC-012 走方案 A，AC-011 的 P5/P6 期望值必须同步改写。**
- **P3 不能单独证明「不是删门禁」**：任何「取消 owner 门禁改为跨 key 广播」的改动同样会让 P3 翻转。因此 AC-011 的闸门必须**成对**读 P2（keyA 期间不得投递 keyB）+ P3（接管后投递 1 次）。仅看 P3 不足以确认修复方向。
- **既有回归测试的碰撞（第三处翻转）**：`packages/coding-agent/test/extensions/agent-team-loop.test.ts:2053-2085` 断言：无 watch key 时 `t0`/`t2` 终态不投递 (`:2076` `expect(messages).toEqual([])`)，之后 `watch.key = "key-a"` 仍不投递 (`:2077` `expect(messages).toEqual([])`)。**若把 `:1436` 无条件后移到 `:1440` 之后**，则 `!watch.key` 分支也不会记账，`t0` 会在 `watch.key = "key-a"` 后的 tick 被投递 ⇒ 该测试失败。修法必须区分：C3（`!watch.key`，保持静默且**继续记账**）与 C1（owner 不匹配，**不记账**）。这是 S6 的一个硬约束，且是现成的现存测试闸门。

---

## 6. 问 6：无 I/O 放大的确认（R5）

**判定分支（`:1440` 的 `continue`）不读 `output.md` body，也不读任何文件。**

证据（按行号顺序，均在 `pm/pm-orchestrator.ts`）：

| 行号 | 语句 | I/O |
|---|---|---|
| `:1435` | `if (notified.has(entry.taskKey) \|\| !isTerminal(entry.status)) continue;` | 无（内存 Set + 纯函数） |
| `:1436` | `notified.add(entry.taskKey);` | 无 |
| `:1440` | `if (!watch.key \|\| ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;` | 无（`path.relative` + `split`，见 `ui-bridge.ts:457-460`） |
| `:1448` | `recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);` | **读 `trace.log`**（`:611-615` → `countWriteScopeResidualRisks` `:590-607` `fs.readFileSync(path.join(taskDir,"trace.log"))`），且在计数 > 0 时写 dispatch-alarm ledger |
| `:1456` | `heartbeatStatsSuffix(taskDir, entry)` | **读 `trace.log`**（`readTaskProgress`） |
| `:1457` | `readOutputBody(taskDir)` | **读 `output.md`**（`ui-bridge.ts:504-518`） |
| `:1465` | `readSpawnFailure(taskDir)` | **读 `worker.log`**（`ui-bridge.ts:520-541`） |

所有文件读取都在 `:1440` 之后 ⇒ 记账后置**不会**让未投递的跨 key 终态行增加每 tick 的文件读取。每 tick 的稳态增量只有：`notified.has` miss + `ownerKeyOf` 一次 `path.relative`。

需要区分的既有开销（记账后置不改动它）：每 tick 开头无条件 `workerStore.readAll()`（`:1400`，读 `_workers.parallel`），以及有 watch key 时 `renderWatchLines`（`:1390-1393`，读 `_workers.acked` + 队列 + 各 running 行 trace）。R5 的争点只是「判定分支是否放大」，答案是**不放大**。

---

## 7. 探针实跑（命令 + 输出）

命令（仓库根）：

```
node .agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-repro-20261014.mts
```

输出（本次实跑，逐字）：

```
deliveries: ["[b2] done — 无 output.md 摘要（worker 可能崩溃/超时）。日志：C:\\Users\\WENBOZ~1\\AppData\\Local\\Temp\\mw-readback-probe-X8s7nT\\proj\\.agenticdoc\\keyB\\workers\\b2\\worker.log"]
PASS  P1 no push while both rows are running  (deliveries=0)
PASS  P2 keyA window gets no keyB push (owner gate)  (deliveries=0)
PASS  P3 DEFECT: takeover of keyB still pushes nothing for terminal b1  (deliveries=0, saw b1=false)
PASS  P4 control: b2 goes terminal under watch -> pushed  (saw b2=true)
PASS  P5 DEFECT: a2 terminal at open under the watched key is never replayed  (saw a2=false)
PASS  P6 c1 terminal at open under an unwatched key is never replayed  (saw c1=false)
VERDICT: defect reproduced as predicted
```

（`node -v` = v24.19.0；Windows，git-bash 调用。探针只写 `os.tmpdir()` 下的临时树并在退出时 `fs.rmSync`。）

### 7.1 用于「未找到清单」的检索命令与输出

**命令 A**：`grep -n 'notified' packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
输出：`:170/:173/:178`（`evidenceReviewNotice` 的入参 Set）、`:1349/:1350/:1371/:1435/:1436/:1446`。→ 无持久化、无导出。

**命令 B**：`sed -n '1337,1550p' …/pm-orchestrator.ts | grep -n 'ackStore'`
输出：
```
4:	ackStore: AckStore,
56:					renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key, watch.dispatchedTaskKeys),
```
→ 函数体内 ack 仅出现在参数声明与 `:1392` 的 widget 渲染，**无 ack 投递/抑制分支**。

**命令 C**：`grep -rn 'unread|未回读|未推送' packages/coding-agent/src/extensions/agent-team-loop | head -20`
输出：全部命中 `autopilot/monitor.ts` 的 gate-queue readability（`unreadable`）语义（`:158/:161/:163/:187/:254/:309/:407/:462/:514/:527/:530/:553/:678/:949/:954/:957/:1019/:1062/:1303/:1304`）。→ **AC-013 的「未回读条数 N」surface 未找到**（无匹配「未回读 / 未推送」的代码）。

**命令 D**：`grep -rn 'appendEntry' …/pm/pm-orchestrator.ts`
输出：`:257`、`:379`（`WATCH_ENTRY_TYPE`）、`:1328`（`GATE_REMINDER_DROPPED_ENTRY_TYPE`）、`:1523`（`GATE_REMINDER_ENTRY_TYPE`）。→ worker 回读的 `notified` **没有**持久化 entry（对比 gate reminder 有）。

---

## 未找到清单

1. `notified` 的持久化/导出/session entry：未找到（命令 A、D 输出如上）。
2. `startWorkerPollLoop` 内的 ack 读写或 ack 触发补推：未找到（命令 B 输出如上）。
3. AC-013 的「未回读条数 N」实现（widget 或消息）：未找到（命令 C 输出如上，全部命中 gate-queue readability 的另一语义）。
4. `triggerTurn` 在 PM 正在跑 turn 时的合并/丢失比例：未找到（本 RQ 未实跑真实窗口；母报告 §6 已声明未覆盖，本复核不补测）。
5. 双窗口同 key 的交互行为：未找到（同上，未实测）。
6. `notified` 与 `run_id` 维度的去重键：未找到 —— `WorkerEntry`（`worker-store.ts:14-28`）无 run 字段，回读路径未接入 `shared/run-store.ts`。

## 未覆盖面声明

- 本 RQ 只做**静态复核 + 1 次探针实跑**；未修改任何源码，未跑仓库测试套件（禁止 `./test.sh` 全量、未跑包级定向套件），因此「改造后的期望值」是**按代码语义推导**，不是已执行的绿色测试。
- 未实跑多窗口 / 真实 provider / gate reminder 通道的端到端；未量化 `triggerTurn` steer 比例（对齐母报告 §6 的未覆盖面）。
- C2 的产品判断（是否补推开窗即终态行）不在本 RQ 结论内；§5.2 只指出它与 AC-011 的 P5/P6 期望值耦合。
- 探针本身仍是独立脚本（非仓库回归测试）；§4 给的是转型形状，转型与实现留给 tasks。

[VERIFY] branches=13 (11 suppression + 3 delivery exits, A2/B1/B2/B3/C1/C3/D1/D2/D3/D4/F1 + B4/C4-C6/D5); probe_runs=1; probe_PASS=6/6; VERDICT="defect reproduced as predicted"; repo_files_modified=0; flips_after_C1_fix={P3:true(by design), P4_absolute_count:true, P1:false, P2:false, P5:false, P6:false}; existing_test_collision=agent-team-loop.test.ts:2077; notified_persistence=absent; ack_branches_in_poll_loop=0; file_reads_before_gate=0
