# Design 复核：终端回读推送域修（C1/C3 拆分 / 补推去重键 / 未回读计数 / P4 断言债 / 测试形态）

- Key: `mw-worker-output-contract`
- Card: `tasks/T-DR5-readback-delivery.md`（dispatch card `mw-dispatch-card: v1`; `card_sha256: d063c83f9e98e500cfb443a81a2ce2ab8e95dd9048722c6dfb10f29336679368`）
- 性质：**只读设计复核（research）**。未修改仓库任何文件；未跑仓库测试套件；未跑探针（探针为既有证据，本卡只在其上做设计）。
- 前置证据（吸收，未重新发现）：`evidence/readback-push-scope-gap-20261014.md`（14,191 B）、`evidence/readback-push-scope-repro-20261014.mts`（5,197 B）、`evidence/research/spec-rq5-readback-push-20261014.md`（29,452 B，含 11/11 自然实验与探针断言全文）。
- spec 锚点：§1.5 P6、§1.6 S6、§3 AC-011 / AC-012 / AC-013、§4 R5 / R6。

---

## 0. 结论与决策

**先回答一句话**：C1 与 C3 的最小拆分 = 把 `!watch.key` 抽成「先记账、再静默」的独立分支，owner 不匹配改为「不记账」的独立分支，然后把 `notified.add` 后移到 owner 门禁之后、`recordWriteScopeResidualRisks` 之前；补推去重键取 `taskKey`、投递水位仍用进程内 `notified`，不引入 ack 耦合；AC-012 取「不补推 + widget 未读计数」；AC-013 取「无 watch key 时单行 widget 计数，不发消息」。

| 决策 | 内容 | 依据 |
|---|---|---|
| D-1 | C3 = `!watch.key` → `notified.add` + `continue`（保持静默、继续记账）；C1 = owner 不匹配 → `continue`（**不**记账）；两者拆成两个分支 | AC-011(d)；spec-rq5 §5.2 第三处翻转；既有锁 `agent-team-loop.test.ts:2079` |
| D-2 | `notified.add` 后移到 owner 门禁之后、`recordWriteScopeResidualRisks`（`pm-orchestrator.ts:1448`）之前 | spec §1.6 S6；AC-011(a)；R5（门禁前无 I/O） |
| D-3 | 去重键 = `taskKey`；投递水位 = 进程级 `notified`（窗口会话）；**ackStore 不参与投递抑制** | R6；`ack-store.ts:9-11`；`ui-bridge.ts:713/722` |
| D-4 | 新增 `readbackDelivered`（`notified` 的子集，仅「门禁后已投递」）作为未回读计数的唯一依据；挂在 `PmWatchState` 上（进程级、不持久化） | AC-012/AC-013；`ui-bridge.ts:494-507`（`PmWatchState` 已有同类进程级字段 `dispatchedTaskKeys`） |
| D-5 | AC-012 取方案 B（开窗即终态行**不**补推），机械判据 = widget 出现 `N unread` 尾行；方案 A（补推历史的终态行）被 AC-011(b)「P5/P6 断言不变」排除 | AC-011(b)；spec-rq5 §5.2 「AC-011 与 AC-012 的耦合」 |
| D-6 | AC-013 = 无 watch key 时渲染**单行 widget**（N>0 才渲染，N=0 清空），**不发消息**；N = 全项目「终态 ∧ 未 ack ∧ 未投递」条数 | AC-013；`applyWatchWidget` 在 `ui.ctx === undefined` 时 no-op（`ui-bridge.ts:900-902`）⇒ 不污染既有 `messages === []` 锁 |
| D-7 | 测试落 `packages/coding-agent/test/suite/mwoc-t01-readback-delivery.test.ts`（沿用 key 前缀先例），纯文件夹具 + 假 `pi` + 假时钟；**不需要 faux provider** | §6；先例 `mwgal-t10-state-surface.test.ts` 全文无 harness |
| D-8 | owner 门禁**保持 owner-key-only**（不换成 `ownedByThisWindow`）；「本窗口显式跨 key 派发的终态行只 escalate 不回读」这一不对称作为已知残留记录，不并入本卡 | AC-011 的闸门要成对读 P2+P3；`ui-bridge.ts:469-471` |

---

## 1. C1/C3 拆分的最小改法

### 1.1 现状原文（`pm/pm-orchestrator.ts`）

命令与输出（`Select-String`，逐字）：

```
1407: for (const entry of entries) {
1434: for (const entry of entries) {
1435: if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
1436: notified.add(entry.taskKey);
1440: if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
1448: recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
1456: const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
1457: const body = readOutputBody(taskDir);
```

`pm/pm-orchestrator.ts:1434-1448`（原文片段）：

```ts
			for (const entry of entries) {
				if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
				notified.add(entry.taskKey);
				// One-shot transcript summaries fire only for this window's watched
				// key; without a watched key the window stays silent (no cross-window
				// broadcast). The widget above still shows current state either way.
				if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
				// Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
				const taskDir = path.dirname(entry.taskPath);
				// AC-007/DD-08 residual risk: ...
				// single dispatch-alarm ledger channel; `notified` above bounds it to
				// once per task per session.
				recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
```

`notified` 是 `startWorkerPollLoop`（`:1337` 起）内的进程级 `Set`，开窗基线在 `:1350`；门禁前无任何文件读取（R5 已核）。

### 1.2 改动后代码形态（最小改法）

```ts
			for (const entry of entries) {
				if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
				// C3 — no watched key: stay silent (no cross-window broadcast), but
				// consume the terminal transition for this session so that adopting a
				// key later cannot resurrect it. Locked by
				// test/extensions/agent-team-loop.test.ts:2079. NOT counted as
				// delivered: the unread counter (AC-013) must still see it.
				if (!watch.key) {
					notified.add(entry.taskKey);
					continue;
				}
				// C1 — another key's terminal row: not this window's business AND not
				// consumed, so the owner window (or this window after a key switch)
				// still gets its one readback. No I/O on this path (R5).
				if (ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
				// Owned + watched: account the delivery once. This stays the bound
				// for recordWriteScopeResidualRisks below ("once per task per
				// session") — do not move it past that call.
				notified.add(entry.taskKey);
				readbackDelivered.add(entry.taskKey);
				const taskDir = path.dirname(entry.taskPath);
				recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
				// ... header / body / deliverWorkerResult unchanged ...
			}
```

- 顺序 = 条件求值顺序：`notified.has || !isTerminal`（`:1435`）→ **C3** → **C1** → 记账（原 `:1436` 的位置后移）→ `recordWriteScopeResidualRisks`（`:1448`）→ 投递。
- 相对原码的**净改动**：一个 `if` 拆成两个 `if`，且 `notified.add` 从 `:1436` 移到 owner 门禁之后、`recordWriteScopeResidualRisks` 之前。
- `readbackDelivered` 是 D-4 新增的进程级 `Set`（见 §5.4），仅服务 AC-012/AC-013 的未读计数；不参与屏蔽判定。

### 1.3 既有断言 `agent-team-loop.test.ts:2079` 仍通过的推演

相关原文（命令 + 输出）：

```
2053: it("stays silent without a watched key and for tasks under other keys", async () => {
2076: // Watching key-a later must not resurrect the already-consumed t0.
2077: watch.key = "key-a";
```

`agent-team-loop.test.ts:2067-2079`（原文片段，`read` 工具行号）：

```ts
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			for (const key of ["t0", "t2"]) {
				...
				await store.upsert({ ...entry, status: "done" });
			}
			vi.advanceTimersByTime(500);
			// No watched key → no notifications, even for globally active keys.
			expect(messages).toEqual([]);          // :2075
			// Watching key-a later must not resurrect the already-consumed t0.
			watch.key = "key-a";                    // :2077
			vi.advanceTimersByTime(500);
			expect(messages).toEqual([]);          // :2079  ← C3 回归锁
```

逐 tick 推演（`watch.key = undefined` 起步，`t0` 属 key-a、`t2` 属 key-b，二者均 `pending` → `done`）：

| tick | entry | `:1435` | C3 分支 | 结果 |
|---|---|---|---|---|
| 1 | t0 done | 未命中（不在基线） | `notified.add("t0")` + continue | 不投递 |
| 1 | t2 done | 未命中 | `notified.add("t2")` + continue | 不投递 |
| 2..5 | t0/t2 | 命中 `notified.has` | — | 不投递 |
| 6（`watch.key="key-a"`）| t0 | 命中 `notified.has` | — | 不投递 |
| 6 | t2 | 命中 `notified.has` | — | 不投递 |

`expect(messages).toEqual([])` 在 `:2075` 与 `:2079` 均成立。**关键**：C3 分支保留了 `notified.add`（若把 `notified.add` 朴素后移到整条门禁之后，`t0` 不在 `notified` 里，第 6 tick 会被投递 ⇒ `:2079` 失败——正是 AC-011(d) 禁止的写法）。

同块其余测试不受影响：

| 测试 | 位置 | 改后结果 |
|---|---|---|
| baseline snapshot（开窗即终态永不回读） | `:1998-2029` | 基线仍由 `:1350` 播种 ⇒ 不变 |
| watched key 下 pending→done 恰好一次 | `:2031-2051` | 门禁通过 → `notified.add` → 投递一次；第 2 tick 命中 `notified` ⇒ 不变 |
| `_scratch` 被 watch 时 failed 投递 | `:2087-2111` | 同上 ⇒ 不变 |
| spawn-failure 回读 | `:2136-2160` | 同上 ⇒ 不变 |

---

## 2. 补推语义与去重键

### 2.1 `ackStore` 未 ack 是否触发补推 —— 结论：**不触发**

三条理由，均有代码锚点：

1. **语义不同轴**。`notified` = 「本窗口已投递过」的**窗口会话级**水位（`pm-orchestrator.ts:1349-1356` 声明在 `startWorkerPollLoop` 内，无持久化、无导出；RQ5 命令 A/D 已核）；`ackStore` = 「PM 已处理完」的**项目级持久化**水位（`ack-store.ts:9-11`/`:20`：`.agenticdoc/_workers.acked`，`taskKey | ackedAtIso`）。`done` 行不需要 ack 即进 history（`ui-bridge.ts:800`：`e.status === "done" || acked.has(...)`）⇒ 「未 ack 即补推」会让所有未被 ack 的 `done` 行**每 tick 重投**。
2. **ack 不参与投递**。poll loop 里 ack 的唯一用途是 widget 渲染（`pm-orchestrator.ts:1392` → `ui-bridge.ts:713` 的 `acked` 集合）；函数体内无任何 ack 投递/抑制分支（RQ5 命令 B）。因此「ack 触发补推」是**新增**语义，不是放宽既有语义——收益是 C2 行可补推，代价是去重键必须另建。
3. **`ackedAt` 不能进去重键**。`ack()` 幂等但会**重写时间戳**（`ack-store.ts:44-56`，`new Date().toISOString()`），把时间戳当投递凭证会在 re-ack 时失效。

**推荐**：投递补推完全由 C1/C3 拆分 + `notified` 承担；`ackStore` 只决定「未读计数」与 widget 的 unhandled/history 分界（§5）。

### 2.2 去重键候选逐条代价

| 候选 | 去重粒度 | 持久化 | 代价 / 失效模式 | 结论 |
|---|---|---|---|---|
| `notified`（进程内 `Set<taskKey>`，现状沿用） | 窗口会话 × taskKey | 无 | 跨窗口重复投递；窗口重启后重算基线（历史行沉底 = C2）；taskKey 复用（同目录重跑）时二次终态被吞 | **采用**为投递水位 |
| 新增 `readbackDelivered`（`PmWatchState` 上的进程级 `Set<taskKey>`） | 窗口会话 × taskKey | 无 | 同上；只用于计数，不参与屏蔽 | **采用**为未读计数依据（D-4） |
| `ackStore`（`taskKey \| ackedAtIso`） | 项目 × taskKey | 有（`_workers.acked`） | 作为投递去重 ⇒ 未 ack 行每 tick 重投（无界）；re-ack 改时间戳破坏键；一个窗口的 ack 会静默另一个窗口该有的回读（`ackTasks` 的 `scope` 只做归属校验，不去重窗口）；语义错位 | **不采用**（保留为处理水位） |
| `taskKey + run_id` | task × run | 视来源 | `WorkerEntry`（`worker-store.ts:13-27`）无 run 字段；run 身份在 `shared/run-store.ts`，回读路径未接入（RQ5 未找到清单第 6 条）⇒ 需扩队列列或旁路读取，超出 S6 最小面 | **暂不采用**（见 2.4） |

### 2.3 推荐（写死到实现）

- 投递水位：`notified`（语义 = 「本窗口不再投递」= 开窗基线 ∪ C3 消费 ∪ 门禁后已投递）。
- 未读计数依据：`readbackDelivered`（⊂ 门禁后已投递），不持久化。
- 去重键：`taskKey`。
- ack：只进计数与 widget，不进投递判定。

### 2.4 多窗口与多 run 行为说明（spec R6 未验证项）

- **多窗口**：`notified` / `readbackDelivered` 随 `PmWatchState` 每窗口一份（进程级；`setWindowWatch` 只持久化 `{ key, claimed }`，见 `ui-bridge.ts` 的 `WATCH_ENTRY_TYPE` 写入），**不跨窗口共享**。两个窗口同时 watch 同一 key 时各自投递一次（跨窗口重复），与现状一致，本修法不加重。C1 场景下：W1 watch keyA 期间 b1 终态（C1，不记账）→ W2 watch keyB 投递 b1 → W1 之后切到 keyB 时**无投递凭证**，会再投一次（跨窗口重复）。这是「不共享投递账本」的固有结果；若要跨窗口去重需新增**持久化投递水位**（与 ack 分离），属本卡范围外。
- **多 run**：`taskKey` = 任务目录名，实际按派发唯一；同一 `taskKey` 在同一窗口会话内二次终态会被 `notified` 吞掉（现状同）。run 级粒度需要 `taskKey + runId`，而队列行无 run 字段 ⇒ 记录为残留，不并入 S6。

---

## 3. `recordWriteScopeResidualRisks` 的界

### 3.1 现状与风险

`pm-orchestrator.ts:1444-1448` 原文（含注释）：

```ts
				// AC-007/DD-08 residual risk: a contract-allowed write whose basename
				// still names a deny-list artifact is only observable here (the guard
				// wrote `blocked=false risk=deny-basename` and moved on). Reuses the
				// single dispatch-alarm ledger channel; `notified` above bounds it to
				// once per task per session.
				recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
```

`recordWriteScopeResidualRisks`（`pm-orchestrator.ts:611-616`）在命中时调用 `recordDispatchAlarm`，而 `recordDispatchAlarm`（`:562-580`）**无任何去重**：`fs.appendFileSync(ledger, ...)` 无条件追加。⇒ 「每任务一次」的界**完全**由 `notified` 提供；若记账后移到投递之后或整体拿掉，稳态每 tick 会追加一行 dispatch-alarm（4s 一次）。

### 3.2 修复后如何保持界（代码形态）

```ts
				if (ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
				notified.add(entry.taskKey);        // ← 必须在下面这行之前
				readbackDelivered.add(entry.taskKey);
				const taskDir = path.dirname(entry.taskPath);
				recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
```

可达性矩阵（改后）：

| 行状态 | `:1435` | C3 | C1 | `notified.add` | `recordWriteScopeResidualRisks` 触发次数 |
|---|---|---|---|---|---|
| 开窗即终态（基线） | 命中 → skip | — | — | 已在基线集合 | 0（现状同：基线直接 skip） |
| 无 watch key 期间终态 | 未命中 → C3 | add + continue | — | 一次 | 0（现状也是先 `:1436` 再 `:1440` continue ⇒ 0） |
| owner ≠ watch.key | 未命中 → C1 | — | continue，**不记账** | 否 | 0；接管后首次通过门禁时**恰好 1 次** |
| owner = watch.key | 未命中 → 门禁通过 | — | — | 一次 | **恰好 1 次**，后续 tick 命中 `notified` |

结论：C3 **必须继续记账**（否则不仅 `:2079` 失败，该行若在某 tick 被 watch 到还会多记一次 residual）；C1 **必须不记账**（否则 residual 与该行的补推一起丢失）。两条正是 AC-011(d) 要求的分工。

---

## 4. AC-011 的 P4 断言改写方案

### 4.1 为什么必须改

探针 `:101` 原文（`evidence/readback-push-scope-repro-20261014.mts`）：

```ts
	["P4 control: b2 goes terminal under watch -> pushed", step4 === 1 && had("b2"), `saw b2=${had("b2")}`],
```

`step4` 是**累计投递数**。C1 修复后 P3 阶段 `b1` 被补推一次 ⇒ `step3` 由 0 变 1 ⇒ `step4 = step3 + 1 = 2`，`step4 === 1` 必然为假。这是**断言债**（spec-rq5 §5.2 已判定），不是行为回归。

### 4.2 探针的具体 diff（存在性，推荐）

```diff
-	["P4 control: b2 goes terminal under watch -> pushed", step4 === 1 && had("b2"), `saw b2=${had("b2")}`],
+	["P4 control: b2 goes terminal under watch -> pushed", had("b2"), `saw b2=${had("b2")}`],
```

### 4.3 相对式变体（等价的第二方案）

```diff
-	["P4 control: b2 goes terminal under watch -> pushed", step4 === 1 && had("b2"), `saw b2=${had("b2")}`],
+	["P4 control: b2 goes terminal under watch -> pushed", step4 === step3 + 1 && had("b2"), `step3=${step3}, step4=${step4}, saw b2=${had("b2")}`],
```

两者都对：存在性断言只验证「b2 被投递」，相对式额外验证「本阶段恰好多 1 条」。P6 已是相对式（`step5 === step4`），不受 `step3` 变化影响；P1/P2 是绝对零，不受影响。

### 4.4 「P3 必须恰好补推 1 次」的判定方式

探针 P3 改写（`:96-100`）：

```diff
-	[
-		"P3 DEFECT: takeover of keyB still pushes nothing for terminal b1",
-		step3 === 0 && !had("b1"),
-		`deliveries=${step3}, saw b1=${had("b1")}`,
-	],
+	[
+		"P3 (C1): takeover of keyB replays the un-notified terminal row exactly once",
+		count("b1") === 1,
+		`count b1=${count("b1")}, deliveries=${step3}`,
+	],
```

其中需新增计数助手：

```ts
const count = (taskKey: string): number => deliveries.filter((d) => d.includes(`[${taskKey}]`)).length;
```

「恰好 1 次」的机械判据 = `count("b1") === 1`（不是 `>=1`，故能同时排除「删掉 owner 门禁改跨 key 广播」——那样 P2 会先失败）。转化成仓库测试时用同一判据：接管 keyB 后推进 ≥8 个 tick，`count("b1")` 仍恒为 1（幂等）。

**成对读法（必须）**：P2（keyA 期间不得投递 keyB，`count === 0`）+ P3（接管后 `count === 1`）。只看 P3 无法区分「记账后置」与「取消 owner 门禁」。

---

## 5. AC-012 / AC-013 的机械判据与实现点

### 5.1 统一语义

- `notified`（掩蔽水位）= 开窗基线 ∪ C3 消费 ∪ 门禁后已投递。
- `readbackDelivered`（未读计数依据）= 门禁后已投递。
- `acked`（`AckStore.readAll()`）= 已处理。
- **未读 N** = `#{ e : isTerminal(e.status) ∧ e.taskKey ∉ acked ∧ e.taskKey ∉ readbackDelivered }`（scope 见下）。

### 5.2 AC-012 的 C2 机械判据（方案 B：不补推 + widget 计数）

**判据（写死进用例）**：设 `r` 是开窗时已终态的行（进入 `:1350` 基线），`ownerKeyOf(r) === watch.key`，且 `r ∉ ackStore`：

1. 任意 tick 的 `messages` 都不含 `[${r.taskKey}]`（不补推；即 P5/P6 不变）；
2. 该 key 的 widget 内容含尾行 `${N} unread`，其中 N 至少包含 `r`；
3. 对 `r` 执行 `ackStore.ack([r.taskKey])` 后，下一次 widget 不再含 `unread` 段。

实现点：
- 屏蔽不变（基线与 `:1435`）；
- 计数来自 `readbackDelivered` 的补集（§5.4）；
- 尾行由 `renderWatchLines` 在已有 `acked` 集合上追加（不新增读）。

### 5.3 AC-013 的无 watch key 未读数

**判据（写死进用例）**：当 `watch.key === undefined`：

1. 每个 tick 的 `messages` 长度不增长（窗口不跨 key 广播，行为不变）；
2. `ui.ctx.ui.setWidget` 的最后一次调用内容是：`N === 0` 时为 `undefined`；`N > 0` 时为**恰一行**且含 `${N} unread`（N 定义同 §5.1，scope = 全部队列行）；
3. N 随 ack 归零（ack 掉所有终态行后，widget 回到 `undefined`）。

实现点：`pm-orchestrator.ts:1395-1397` 的「无 watch key ⇒ 清空」分支改为「无 watch key ⇒ N>0 时渲染一行、否则清空」。不走 `displaySummary`/`sendMessage`（否则会打破既有 `messages === []` 锁，见 `:2075`/`:2079`）。

### 5.4 实现形态（代码骨架）

`ui-bridge.ts` 的 `PmWatchState`（`ui-bridge.ts:494-507` 区域）新增字段，语义与既有 `dispatchedTaskKeys` 对齐：

```ts
	/** Task keys THIS window session actually delivered a terminal readback for
	 * (post owner gate). Process-local, never persisted — same contract as
	 * `dispatchedTaskKeys`. Sole input for the AC-012/AC-013 "unread" counter:
	 * a row suppressed as history (open-time baseline / C3) is NOT in here and
	 * therefore still counts as unread. `AckStore` is the PM's HANDLING
	 * watermark, not a delivery ledger — unacked never implies undelivered and
	 * no branch replays a readback because of ack state. */
	readbackDelivered?: Set<string>;
```

`pm-orchestrator.ts` 循环内：

```ts
	const readbackDelivered = (watch.readbackDelivered ??= new Set<string>());
```

计数助手（`ui-bridge.ts`，纯函数，供两处复用）：

```ts
/** AC-012/AC-013 unread count: terminal rows with no readback in this window
 * session and no PM ack. Pure. */
export function countUnreadTerminal(
	entries: readonly WorkerEntry[],
	acked: ReadonlySet<string>,
	readbackDelivered: ReadonlySet<string>,
): number {
	let n = 0;
	for (const e of entries) {
		if (!isTerminalStatus(e.status)) continue;
		if (acked.has(e.taskKey) || readbackDelivered.has(e.taskKey)) continue;
		n += 1;
	}
	return n;
}
```

`renderWatchLines` 增加**可选**第 7 参（现有调用点不传 ⇒ 字节不变，零回归）：

```ts
export function renderWatchLines(
	indexStore: IndexStore,
	workerStore: WorkerStore,
	ackStore: AckStore,
	agenticdocRoot: string,
	key: string,
	extraTaskKeys?: ReadonlySet<string>,
	readbackDelivered?: ReadonlySet<string>,
): string[] {
	...
	// before `return lines;`（复用上面已读的 `acked` 与 `owned`）
	if (readbackDelivered) {
		const unread = countUnreadTerminal(owned, acked, readbackDelivered);
		if (unread > 0) lines.push(`  ${unread} unread — terminal result(s) not delivered this session`);
	}
```

poll loop 的 tick 头部（把 `const entries = workerStore.readAll();` 从 `:1400` 提到 widget 块之前，`widgetShown` 语义不变）：

```ts
			const entries = workerStore.readAll();
			if (watch.key) {
				applyWatchWidget(
					ui,
					renderWatchLines(
						indexStore, workerStore, ackStore, agenticdocRoot,
						watch.key, watch.dispatchedTaskKeys, readbackDelivered,
					),
				);
				widgetShown = true;
			} else {
				const acked = entries.some((e) => isTerminal(e.status))
					? new Set(ackStore.readAll().keys())
					: new Set<string>();
				const unread = countUnreadTerminal(entries, acked, readbackDelivered);
				applyWatchWidget(ui, unread > 0 ? [`[mw] no watched key | ${unread} unread terminal result(s)`] : undefined);
				widgetShown = unread > 0;
			}
```

（原 `:1400` 的 `const entries = workerStore.readAll();` 删除，避免二次读。）

I/O 核算：watched-key 路径复用 `renderWatchLines` 内部已有的 `ackStore.readAll()`（`ui-bridge.ts:713`），**零新增读**；no-watch 路径新增一次 `_workers.acked` 读（仅当存在终态行时），`_workers.parallel` 读次数不变。R5 关心的「`ownerKeyOf` 门禁前无 I/O 放大」不受影响。

### 5.5 与既有 widget 测试的兼容性（已核）

`agent-team-loop.test.ts:2214-2217` 原文：

```ts
			// Turning the watch off clears the widget.
			watch.key = undefined;
			vi.advanceTimersByTime(500);
			expect(widgets[widgets.length - 1]).toBeUndefined();
```

该测试只有一行 **running** 的 `t7`（`:2196`）⇒ `entries.some(isTerminal)` 为假 ⇒ N=0 ⇒ `applyWatchWidget(ui, undefined)` ⇒ 最后一次 `setWidget` 仍是 `undefined`。**通过**。AC-013 的新行为只在 N>0 时生效，与「关掉 watch 清空 widget」的既有约定不冲突。

其余直接调用 `renderWatchLines` 的用例（`agent-team-loop.test.ts:2903` VC-002「8 unhandled」、`:2933` VC-003）不传第 7 参 ⇒ 输出逐字节不变。`mwgal-t10-state-surface.test.ts:566` 的 poll-loop 用例 worker 队列为空 ⇒ 无 widget 断言变化。

---

## 6. 测试形态

### 6.1 文件与命名

- 新建 `packages/coding-agent/test/suite/mwoc-t01-readback-delivery.test.ts`。先例：`mwds-t0*.test.ts`、`mwgal-t1*.test.ts`（同目录 key 前缀）。
- 或并入既有 `describe("startWorkerPollLoop summary scoping")`（`packages/coding-agent/test/extensions/agent-team-loop.test.ts:1938`）——该块已有全部夹具。**推荐新建 suite 文件**：三个 AC 各一个 `it`，与 C3 回归锁（扩展测试）分离。
- `test/suite/regressions/<issue-number>-*.test.ts` 命名只在有 GitHub issue 号时适用；本 key 无 issue 号。

### 6.2 夹具表（逐条 `文件:行号`）

| 需要的东西 | 复用点 | 说明 |
|---|---|---|
| 临时根 | `agent-team-loop.test.ts:148`（`mkdtemp`）、`mwgal-t10-state-surface.test.ts:43` | `root = <tmp>`，`agenticdocRoot = root`（`mwgal` 用 `<tmp>/.agenticdoc`；两者皆可，同一文件内保持一致） |
| 假 `pi`（记录 content + options） | `agent-team-loop.test.ts:1939-1950` | 断言 `triggerTurn: true` 透传 |
| 假 `ui.ctx`（捕获 widget） | `agent-team-loop.test.ts:1956-1968` | AC-012/AC-013 必需 |
| 队列行 + task.md + output.md | `agent-team-loop.test.ts:1970-1985`（`queueTask`）/ `:1987-1997`（`activateKey`） | `taskPath = <root>/<owner>/workers/<taskKey>/task.md` |
| 原始 9 列队列行 | `mwgal-t10-state-surface.test.ts:103-120`（`writeWorkers`） | 列序 `taskKey\|status\|cli\|provider\|taskPath\|dispatchedAt\|updatedAt\|model\|origin` |
| 基线（开窗即终态）行 | `queueTask(..., status: "done")` 在 `startWorkerPollLoop` 之前 | 复现 C2 |
| 假时钟 | `agent-team-loop.test.ts:2015-2017`、`mwgal-t10-state-surface.test.ts:568-571` | `vi.useFakeTimers()` + `vi.advanceTimersByTime(...)` |
| 句柄清理 | `agent-team-loop.test.ts:2024` | `clearInterval(handle)` 必须在 `finally` |
| `watch.key` 中途切换 | `agent-team-loop.test.ts:2077` 先例 | 闭包持有同一对象引用，直接赋值即生效 |

### 6.3 各 AC 的用例骨架

```ts
// mwoc-t01-readback-delivery.test.ts
import { startWorkerPollLoop } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
// ... 复制 mkdtemp / fakePi / fakeUiCtx / queueTask / activateKey ...

describe("mwoc AC-011/012/013 terminal readback delivery scope", () => {
	afterEach(() => vi.useRealTimers());

	it("AC-011: takeover replays an un-notified cross-key terminal row exactly once", async () => {
		// a1 running(keyA) | a2 done(keyA, 基线) | b1 running(keyB) | c1 done(keyC, 基线)
		vi.useFakeTimers();
		try {
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(300);
			expect(messages).toHaveLength(0);                       // P1
			await setStatus(store, "b1", "done");
			vi.advanceTimersByTime(400);
			expect(count("b1")).toBe(0);                            // P2（owner 门禁保留）
			watch.key = "keyB";
			vi.advanceTimersByTime(800);
			expect(count("b1")).toBe(1);                            // P3 (C1)：恰好一次
			const step3 = messages.length;
			await setStatus(store, "b2", "done");                   // keyB 下新增行
			vi.advanceTimersByTime(800);
			expect(count("b2")).toBe(1);                            // P4：存在性
			expect(messages.length).toBe(step3 + 1);                // P4：相对式
			expect(count("a2")).toBe(0);                            // P5 (C2)
			watch.key = "keyC";
			vi.advanceTimersByTime(600);
			expect(count("c1")).toBe(0);                            // P6
			clearInterval(handle);
		} finally { fs.rmSync(root, { recursive: true, force: true }); }
	});

	it("AC-012: an open-time terminal row is not replayed but counted unread", async () => {
		// a2 done(keyA) 在开窗前列好；watch.key = "keyA"；ui.ctx = fakeUiCtx().ctx
		vi.advanceTimersByTime(400);
		expect(count("a2")).toBe(0);                                // 不补推（方案 B）
		expect(widgets.at(-1)!.some((l) => /1 unread/.test(l))).toBe(true);
		await new AckStore(root).ack(["a2"]);
		vi.advanceTimersByTime(400);
		expect(widgets.at(-1)!.some((l) => l.includes("unread"))).toBe(false);
	});

	it("AC-013: a window with no watched key surfaces N without broadcasting", async () => {
		// x1 done、x2 failed，均未 ack；watch.key = undefined；ui.ctx = fakeUiCtx().ctx
		vi.advanceTimersByTime(400);
		expect(messages).toHaveLength(0);                           // 不广播
		const last = widgets.at(-1)!;
		expect(last).toHaveLength(1);
		expect(last[0]).toContain("2 unread");
		await ackStore.ack(["x1", "x2"]);
		vi.advanceTimersByTime(400);
		expect(widgets.at(-1)).toBeUndefined();                     // N=0 ⇒ 清空
	});
});
```

负向对照（spec §1.7 第 5 条硬要求）：三条用例在 HEAD 上必须**失败**——
- AC-011：P3 `count("b1")` 为 0（已由探针 P3 实跑证实）；
- AC-012：HEAD 的 widget 无 `unread` 尾行；
- AC-013：HEAD 在 `watch.key === undefined` 时 `applyWatchWidget(ui, undefined)`（`pm-orchestrator.ts:1395-1397`），最后一次 `setWidget` 是 `undefined`，`last[0]` 取不到。
另：既有 C3 锁 `agent-team-loop.test.ts:2079` 与 widget 锁 `:2215` 必须保持绿（§1.3、§5.5）。

### 6.4 `vi.useFakeTimers()` 的必要性：**必要**

`startWorkerPollLoop` 的唯一驱动是 `setInterval`（`pm-orchestrator.ts:1385`，间隔 `pollIntervalMs`，默认 `POLL_INTERVAL_MS = 4000`，`:66`）。用真实计时器就要 `await sleep(...)`（探针用的 50ms 真实等待），断言点会与 tick 边界赛跑；`vi.useFakeTimers()` + `vi.advanceTimersByTime(...)` 让回调**同步**执行，使「推进 N 个 tick 后断言的投递次数」确定。既有 poll-loop 测试一律用此模式（`agent-team-loop.test.ts:2015-2017`）。

### 6.5 **不需要** faux provider

`startWorkerPollLoop` 的外部依赖只有 4 个：`pi.sendMessage`（投递）、`pi.appendEntry`（gate reminder，本三例可不给）、`ui.ctx.ui.setWidget`（widget）、文件系统。它**不调用模型**，`triggerTurn` 只需断言透传（假 `pi` 的 `options` 数组已足够）。因此：

- `createHarness`（`packages/coding-agent/test/suite/harness.ts:101`，内部 `registerFauxProvider` `:103`）是给**模型驱动**的 agent session 用的，用在这里只会引入 provider/agent-session 装配噪音。
- 先例：`test/suite/mwgal-t10-state-surface.test.ts` 与 `mwds-t04-deliverable.test.ts` 均在 `test/suite/` 下直接 import 模块、不引 harness（grep `harness|faux` 命中 0）。
- 与 `AGENTS.md`「test/suite 用 harness + faux provider」的偏差属**有意**：该规则的适用面是模型参与的集成用例；本模块是纯状态机 + 文件系统，走「纯文件夹具 + 假 pi + 假时钟」在本仓有既有先例。

### 6.6 用例命名与 `[VERIFY]`

沿用既有 poll-loop 测试的 `[VERIFY]` 行风格（如 `agent-team-loop.test.ts:2961`：`console.log("[VERIFY] VC-002: ...")`），三个 `it` 各输出一行 `[VERIFY] mwoc-AC-0xx: ...` 供验收脚本抓取。

---

## 证据

以下命令均在仓库根 `H:\git\Multi-Workers` 只读执行；未修改任何文件。

**命令 1**：`Select-String -Path packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts -Pattern 'notified|recordWriteScopeResidualRisks\(|const POLL_INTERVAL_MS'`

```
66: const POLL_INTERVAL_MS = 4000; // < 5s per AC-001
170: notified: Set<string>,
173: if (notified.has(dedup)) return;
178: notified.add(dedup);
611: export function recordWriteScopeResidualRisks(agenticdocRoot: string, taskKey: string, taskDir: string): number {
1349: // this session is open are notified, at most once each.
1350: const notified = new Set(
1371: // `notified` worker baseline). `reminderHistoryRead` gates the one-shot
1435: if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
1436: notified.add(entry.taskKey);
1446: // single dispatch-alarm ledger channel; `notified` above bounds it to
1448: recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
```

（`:170/:173/:178` 属另一个函数的入参 `Set`，与回读无关。）

**命令 2**：定位门禁与投递出口的精确行号

```
1407: for (const entry of entries) {
1434: for (const entry of entries) {
1435: if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
1436: notified.add(entry.taskKey);
1440: if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
1448: recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
1456: const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
1457: const body = readOutputBody(taskDir);
```

**命令 3**：既有 C3 回归锁定位

```
2053: it("stays silent without a watched key and for tasks under other keys", async () => {
2076: // Watching key-a later must not resurrect the already-consumed t0.
2077: watch.key = "key-a";
```

配合 `read` 工具：`:2075 expect(messages).toEqual([]);`、`:2079 expect(messages).toEqual([]);`（卡面所记 `:2077` 是赋值行，断言在 `:2079`）。

**命令 4**：无「未回读 / 未推送 / unread」surface（AC-013 缺失证据）

`Select-String` 在 `pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`、`shared/ack-store.ts`、`shared/worker-store.ts` 上匹配 `未回读|未推送|unread`，命中 12 行，全部是 queue/config `unreadable` 语义（如 `pm-orchestrator.ts:444 | "queue-unreadable"`、`worker-store.ts:166 unreadable lines`）。**无**任何终态回读的未读计数 surface。

**命令 5**：widget 与 ack 的锚点

```
ui-bridge.ts:457: export function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string {
ui-bridge.ts:469: export function ownedByThisWindow(entry: WorkerEntry, watch: PmWatchState, agenticdocRoot: string): boolean {
ui-bridge.ts:625: function isUnhandledStatus(status: WorkerStatus): boolean {
ui-bridge.ts:697: export function renderWatchLines(
ui-bridge.ts:713: const acked = new Set(ackStore.readAll().keys());
ui-bridge.ts:716: const all = workerStore.readAll();
ui-bridge.ts:717: const owned = all.filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
ui-bridge.ts:722: const unhandled = owned.filter((e) => isUnhandledStatus(e.status) && !acked.has(e.taskKey));
ui-bridge.ts:738: if (unhandled.length > 0) parts.push(`${unhandled.length} unhandled`);
ui-bridge.ts:900: export function applyWatchWidget(ui: PmUiHolder, lines: string[] | undefined): void {
ui-bridge.ts:901: if (!ui.ctx) return;
ack-store.ts:20: this.filePath = path.join(agenticdocRoot, "_workers.acked");
ack-store.ts:26: readAll(): Map<string, string> {
ack-store.ts:42: async ack(taskKeys: string[]): Promise<{ acked: string[]; rejected: string[] }> {
```

**命令 6**：既有 widget 清空锁（§5.5）

```
2214: // Turning the watch off clears the widget.
2225: it("does not render a widget without a UI context (headless)", async () => {
```

`:2196 await queueTask(root, "key-a", "t7", "running");` ⇒ 关 watch 时无终态行 ⇒ N=0 ⇒ 仍清空。

**命令 7**：`WorkerEntry` 无 run 字段

```
worker-store.ts:13: export interface WorkerEntry {
worker-store.ts:147: export class WorkerStore {
worker-store.ts:186: readAll(): WorkerEntry[] {
```

字段（`:14-27`）：`taskKey | status | cli | provider | taskPath | dispatchedAt | updatedAt | model | origin?`。

**命令 8**：`recordDispatchAlarm` 无去重（§3.1）

`pm-orchestrator.ts:562-580`：`fs.appendFileSync(ledger, `${JSON.stringify(row)}\n`, "utf8")` 无条件追加；无 key/去重分支。

## 残留与未验证

1. **多窗口投递去重**：本设计不引入持久化投递水位 ⇒ 跨窗口重复投递与「W1 切 key 后重投 W2 已投的行」（§2.4）保留。未实测。
2. **`taskKey + run_id`**：`WorkerEntry` 无 run 字段，未接入 `shared/run-store.ts`；同 key 重跑的第二次终态会被 `notified` 吞掉（现状同）。未实测。
3. **`triggerTurn` 在 PM 正在流式输出时的 steer/合并比例**：未量化（母报告与 RQ5 均已声明）。本设计的投递次数断言在假 `pi` 上成立，不代表真实会话里的可见消息条数。
4. **跨 key 显式派发的不对称**（D-8）：`ownedByThisWindow`（`ui-bridge.ts:469-471`）在 escalation 分支被使用（`pm-orchestrator.ts:1415`），但回读门禁只认 `ownerKeyOf`；本设计**保持**该不对称，未改。若后续要求「本窗口派发的跨 key 任务终态也回读」，需把门禁换成 `ownedByThisWindow` 并同步改写 P2 用例（`dispatchedTaskKeys` 为空的形态下 P2 仍成立，但需补一条非空形态的对照）。
5. **`N unread` 尾行/单行 widget 的具体文案**未定稿：本文给出候选字面量（`${n} unread — terminal result(s) not delivered this session`、`[mw] no watched key | ${n} unread terminal result(s)`），实现时须在用例里钉死同一字面量。
6. **`readbackDelivered` 只服务计数**：它不参与屏蔽，所以即使某行被投递后又被 ack，计数逻辑不依赖投递顺序；该性质未被测试覆盖（可用 §6.3 的 AC-012 用例覆盖 ack 归零路径）。
7. 本卡**未实跑**任何仓库测试，未运行探针；§1.3/§4/§5 的「改后通过」是按代码语义推演，非已执行的绿色测试。实现期须按 §6 落用例并跑 `node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-t01-readback-delivery.test.ts`（包内）与既有 `test/extensions/agent-team-loop.test.ts`。

## 未覆盖面声明

- 未覆盖真实窗口的端到端（多窗口、真实 provider、真实 4s 轮询）。
- 未覆盖 gate reminder 通道（`GATE_REMINDER_ENTRY_TYPE`，独立 watermark）与 widget 的其余渲染路径（本次只在 poll loop 与 `renderWatchLines` 尾部动刀）。
- 未覆盖 `_scratch` / legacy 根级行（`ownerKeyOf` 对根级行返回自身 taskKey）在补推下的行为；该形态在 F-DR5 范围内属边角。
- 未覆盖 Python 侧（`packages/multi-workers`）：回读推送全在 TS，Python 不消费 `notified`。
- 未评估 `N unread` 计数在超大队列（数千行）下的渲染成本；`countUnreadTerminal` 是 O(entries) 线性扫描，已读的 `owned`/`all` 数组复用，不新增读。
- 未执行探针改写（探针文件属证据，本卡只读）；§4 的 diff 是提案，实施时由实现方决定是否同步更新 `evidence/readback-push-scope-repro-20261014.mts`。

## 上下文来源

- `.agenticdoc/mw-worker-output-contract/spec.md`（§1.5 P6、§1.6 S6、§3 AC-011/AC-012/AC-013、§4 R5/R6）
- `.agenticdoc/mw-worker-output-contract/tasks/T-DR5-readback-delivery.md`
- `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-gap-20261014.md`
- `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-repro-20261014.mts`
- `.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq5-readback-push-20261014.md`
- `.agenticdoc/goal.md`（项目级目标锚点：PM 编排多 Worker + 文件驱动去中心化协调）
- 源码：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`、`shared/ack-store.ts`、`shared/worker-store.ts`、`worker/output-sections.ts`
- 测试：`packages/coding-agent/test/extensions/agent-team-loop.test.ts`、`test/suite/mwgal-t10-state-surface.test.ts`、`test/suite/mwds-t04-deliverable.test.ts`、`test/suite/harness.ts`
- `AGENTS.md`（测试与写面规则）

[VERIFY] design_decisions=8 (D-1..D-8); questions_answered=6/6; c1_c3_split=two_branches (C3 notify+silent, C1 no-account) ; notified_add_moved_to_after_owner_gate_before_recordWriteScopeResidualRisks=true; existing_lock_agent-team-loop.test.ts:2079=passes_by_derivation (C3 branch keeps notified.add); dedup_key=taskKey (notified=delivery watermark, readbackDelivered=unread counter, ackStore=handling watermark only, no ack-triggered repush); residual_risks_bound=notified.add before recordWriteScopeResidualRisks (recordDispatchAlarm has no dedup, pm-orchestrator.ts:562-580); P4_assertion_debt=fixed to had("b2") or step4===step3+1; P3_criterion=count("b1")===1; AC-012=option_B (no replay + N unread widget line, mechanical criterion pinned); AC-013=no-watch single-line widget N unread, N=0 -> clear, no message broadcast; test_file=packages/coding-agent/test/suite/mwoc-t01-readback-delivery.test.ts; fakeTimers=required (setInterval-driven); faux_provider=not_required (loop never calls model; harness.ts:101 createHarness is model-driven); existing_widget_lock:2217=passes (t7 running -> N=0 -> widget cleared); repo_files_modified=0; test_suites_run=0; lines_cited_verified_by_Select-String=true
