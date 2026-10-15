# 终态回读推送的范围缺口（notified 标记早于 owner 门禁）

- 状态：**已定位 + 已复现**（未修复；修共享推送路径需要先开 key）
- 观测窗口：2026-10-13T17:10Z – 2026-10-14T00:03Z（本窗口，cwd `H:\git\Multi-Workers`）
- 组件：`packages/coding-agent/src/extensions/agent-team-loop/pm/{pm-orchestrator.ts,ui-bridge.ts}`
- 探针脚本：`.agenticdoc/_scratch/evidence/readback-push-scope-repro-20261014.mts`

---

## 0. 结论先行

1. 终态 worker 结果**是按 watch key 定向推送**的：只有 `ownerKeyOf(entry) === watch.key` 的行才会被注入 PM 会话（`pm-orchestrator.ts:1440`）。
2. 但"已通知"标记 `notified.add(entry.taskKey)` 发生在**该门禁之前**（`:1436` 在 `:1440` 之前）⇒ 一个终态行只要在**它所属 key 不是本窗口 watch key** 的那次轮询里被看到，就被**永久记账为已推送**；之后窗口接管/切换到该 key 也**不会再补推**（丢失，不可恢复）。
3. 另有开窗基线（`:1350`）：窗口打开时已经终态的行一律视为历史，永不回读；以及无 watch key 时整段静默（`:1440` 的 `!watch.key` 分支）。
4. 后果：多 key 批次（本窗口同时推进 `mw-write-face-guard` + `mw-dynamic-concurrency`）中，终态回读**部分静默丢失**；PM 只能靠 `list_tasks` 轮询发现，会把"已终态"误报成"仍在 running"。
5. 合成探针（真实 `startWorkerPollLoop` + 临时队列）复现了该落差，含对照组：`b1` 永不推送，而同一 key 的 `b2` 在同一窗口被推送 ⇒ 不是探针假阴性。

## 1. 现象与影响

- 期望：worker 终态后，PM 会话收到一条 `[task] status: <output.md body>` + `PM_CONTINUE_HINT` 的注入消息（"finish call"），PM 据此吸收并派发下一个任务。
- 实际：本窗口 11 个终态任务里 **7 个有推送、4 个完全没有**（§4 账本）；4 个中的 3 个是 PM 靠 `list_tasks` 主动轮询才发现的。
- 影响面：
  - PM 的"吸收终态 → 推进下一任务"循环会**停摆**（依赖用户再问一句），并可能基于过期快照对外报告状态（本窗口发生过一次：报告"2 个仍在 running"，实际已终态）。
  - `ack_worker_result` 的提示只在推送消息里出现；未推送的行不会收到"请 ack"的指引（仍在 widget 未处理区可见，因此不是完全隐形）。
  - 与并发批次的规模正相关：**同批越多、跨 key 越多、watch key 翻转越多，丢失越多**。

## 2. 根因（代码锚点）

`pm/pm-orchestrator.ts:1349-1357`（开窗基线）：

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

`pm/pm-orchestrator.ts:1434-1440`（**顺序即缺陷**）：

```ts
			for (const entry of entries) {
				if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
				notified.add(entry.taskKey);            // 1436: 先记账
				// One-shot transcript summaries fire only for this window's watched
				// key; without a watched key the window stays silent (no cross-window
				// broadcast). The widget above still shows current state either way.
				if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;  // 1440: 后过滤
```

- `:1436` 与 `:1440` 相邻但语义相反：`notified` 的语义是"已经作为回读投递过"，而 `:1440` 的 `continue` **不投递**。二者叠加 ⇒ 非 watch key 的终态行被标记成"已投递"。
- `notified` 是窗口进程级 `Set`（`:1350` 声明于 `startWorkerPollLoop` 内），生命周期 = 窗口会话；同 key 后续不会因为"再次轮询"而重投（`notified.has` 直接 continue）。
- 投递通道本身是"尽力而为"的：`ui-bridge.ts:176-189` `deliverPmAlert` → `pi.sendMessage(..., { triggerTurn: true })`，其注释明确写着 *"With `triggerTurn: true` an idle PM starts an LLM turn immediately; **a streaming PM gets the text steered into the current turn**"* —— 推送期间 PM 正在跑 turn 时不会各自成为独立可见的新消息。这是**并发放大器**，不是本缺口的主因。
- 三处子因，独立可验：
  - **C1 顺序缺陷**（主因，本文复现）：`:1436` 早于 `:1440` ⇒ 永久抑制 + 接管不补推。
  - **C2 开窗基线**：`:1350` 打开窗口时已终态 = 历史，永不回读（若窗口重启，期间终态的行全部沉底）。
  - **C3 无 watch key 静默**：`:1440` 的 `!watch.key` ⇒ 未 watch 任何 key 的窗口一个回读也收不到。

## 3. 复现 A：合成探针（可重跑，决定性）

脚本：`.agenticdoc/_scratch/evidence/readback-push-scope-repro-20261014.mts`
做法：构造临时 agenticdoc 根（`<tmp>/proj/.agenticdoc`）+ 9 列队列行 + 假 `pi`（只记录 `sendMessage`），**调用真实的 `startWorkerPollLoop`**（`pollIntervalMs=50`）。不碰仓库任何文件，退出时删临时树。

场景：`a1` running（本窗口 key）、`a2` **开窗即终态**（本窗口 key）、`b1` running（别的 key）、`c1` 开窗即终态（未 watch 的 key）。

```
deliveries: ["[b2] done … 无 output.md 摘要（worker 可能崩溃/超时）。日志：…\\keyB\\workers\\b2\\worker.log"]
PASS  P1 no push while both rows are running  (deliveries=0)
PASS  P2 keyA window gets no keyB push (owner gate)  (deliveries=0)
PASS  P3 DEFECT: takeover of keyB still pushes nothing for terminal b1  (deliveries=0, saw b1=false)
PASS  P4 control: b2 goes terminal under watch -> pushed  (saw b2=true)
PASS  P5 DEFECT: a2 terminal at open under the watched key is never replayed  (saw a2=false)
PASS  P6 c1 terminal at open under an unwatched key is never replayed  (saw c1=false)
VERDICT: defect reproduced as predicted
```

关键在 **P3 + P4 的对照**：
- `b1` 在 loop 打开时是 **running**（不在 `:1350` 基线里），它在"窗口 watch 别的 key"期间终态 → 被 `:1436` 记账、被 `:1440` 跳过；随后 `watch.key = "keyB"`（接管），**8 个 tick 内依旧 0 推送**（C1 的直接证据，排除 C2 解释）。
- 对照 `b2` 在同一 key 被 watch 时终态 ⇒ **推送成功**（证明探针与投递通道工作正常，`b1` 的静默是缺陷而非假阴性）。
- P5（同 key 开窗即终态）隔离出 C2；P6 隔离出"未 watch key 的基线行"。

重跑：

```
node .agenticdoc/_scratch/evidence/readback-push-scope-repro-20261014.mts
```

两次连跑输出一致（确定性）。

## 4. 复现 B：本会话自然实验（11/11 吻合）

**证据 1：终态时刻**来自每个任务的 `trace.log` 的 `[END]` 行（文件事实）：

```
[END] 2026-10-13T17:16:39.437Z  mdc-rq3-config-mirror
[END] 2026-10-13T17:17:30.462Z  wfg-rq2-enforcement      <- 从未推送
[END] 2026-10-13T17:18:19.751Z  mdc-rq2-dependency-sources
[END] 2026-10-13T17:18:44.247Z  mdc-rq1-dispatch-chain
[END] 2026-10-13T17:22:39.647Z  wfg-rq3-safety
[END] 2026-10-13T17:22:50.104Z  wfg-rq1-write-face-sources
[END] 2026-10-13T23:52:59.997Z  wfg-rq-d1-glob-intersection  <- 从未推送
[END] 2026-10-13T23:55:21.899Z  mdc-rq-d4-task-deps
[END] 2026-10-13T23:56:35.559Z  wfg-rq-d2-runtime-guard
[END] 2026-10-13T23:57:37.677Z  mdc-rq-d5-cap-and-status      <- 从未推送
[END] 2026-10-14T00:02:39.633Z  mdc-rq-d3-lock-critical-section <- 从未推送
```

**证据 2：推送账本**来自本窗口 pi 会话 JSONL（`type=custom_message, customType=agent-team-loop:worker-summary`），即"确实被投递过"的消息：

```
2026-10-13T17:16:44 [mdc-rq3-config-mirror] done
2026-10-13T17:18:24 [mdc-rq2-dependency-sources] done
2026-10-13T17:18:50 [mdc-rq1-dispatch-chain] done
2026-10-13T17:22:45 [wfg-rq3-safety] needs-clarification
2026-10-13T17:22:56 [wfg-rq1-write-face-sources] done
2026-10-13T23:55:27 [mdc-rq-d4-task-deps] needs-clarification
2026-10-13T23:56:41 [wfg-rq-d2-runtime-guard] needs-clarification
total worker-summary entries: 7   (本窗口 11 个终态任务 -> 仅 7 条回读)
```

**吻合性**（11/11）：

| 任务 | key | 终态 | 推送 | 判定 |
|---|---|---|---|---|
| mdc-rq3-config-mirror | mdc | 17:16:39 | 17:16:44 (+5s) | watch=mdc，正常 |
| wfg-rq2-enforcement | wfg | 17:17:30 | — | 终态时 watch=mdc（由 17:18:24/17:18:50 两条 mdc 推送证明）⇒ `:1436` 记账 + `:1440` 跳过 ⇒ **永久丢失**；17:22:45 起 watch 已翻到 wfg，仍不补推 ⇒ **C1 的现场证据** |
| mdc-rq2-dependency-sources | mdc | 17:18:19 | 17:18:24 (+5s) | 正常 |
| mdc-rq1-dispatch-chain | mdc | 17:18:44 | 17:18:50 (+6s) | 正常 |
| wfg-rq3-safety | wfg | 17:22:39 | 17:22:45 (+6s) | watch 已翻到 wfg ⇒ **直接反证"门禁只是推迟而非丢失"**：同一时刻 wfg-rq2 已不可救 |
| wfg-rq1-write-face-sources | wfg | 17:22:50 | 17:22:56 (+6s) | 正常 |
| wfg-rq-d1-glob-intersection | wfg | 23:52:59 | — | 期间无任何推送（下一次是 23:55:27 的 mdc）⇒ 终态时 watch=mdc ⇒ 永久丢失 |
| mdc-rq-d4-task-deps | mdc | 23:55:21 | 23:55:27 (+6s) | 正常 |
| wfg-rq-d2-runtime-guard | wfg | 23:56:35 | 23:56:41 (+6s) | watch 已在 23:55:27–23:56:41 之间翻回 wfg |
| mdc-rq-d5-cap-and-status | mdc | 23:57:37 | — | 终态时 watch=wfg ⇒ 永久丢失 |
| mdc-rq-d3-lock-critical-section | mdc | 00:02:39 | — | 终态时 watch≠mdc（若=mdc 应在 ~00:02:45 推送）⇒ 永久丢失 |

推送时间全部落在 `[END]` 之后 **+5~6s**（轮询 4s 间隔，`POLL_INTERVAL_MS=4000`，`pm-orchestrator.ts:66`），说明"该推的都推了、时间也对"；4 个缺失项**无一例外**落在"终态时其 owner key ≠ watch key"的窗口里，且**之后 watch key 翻回也不补** —— 与 C1 的预测完全一致。

**复现命令**：

```powershell
# 证据 1
cd .agenticdoc; Get-ChildItem mw-dynamic-concurrency/workers,mw-write-face-guard/workers -Directory |
  ForEach-Object { $t=Join-Path $_.FullName 'trace.log'; if (Test-Path $t) { "{0} {1}" -f $_.Name,(Select-String -Path $t -Pattern '\[END\]' | Select-Object -First 1).Line } }
```

证据 2 的账本抽取程序（临时脚本，约 15 行）：

```js
import * as fs from "node:fs";
const lines = fs.readFileSync(process.argv[2], "utf8").split(/\r?\n/);
for (const line of lines) {
  if (!line.trim()) continue;
  let e; try { e = JSON.parse(line); } catch { continue; }
  if (!JSON.stringify(e).includes("agent-team-loop:worker-summary")) continue;
  console.log(String(e.timestamp).slice(0,19), JSON.stringify(String(e.content).split("\n")[0].slice(0,60)));
}
```

```powershell
node <上面脚本>.mjs "C:\Users\wenbozhou\.pi\agent\sessions\--H--git-Multi-Workers--\<本窗口 session>.jsonl"
```

（会话文件按 `LastWriteTime` 最新 + 含 `agent-team-loop:worker-summary` 条目判定；本窗口为 `2026-10-13T15-27-03-170Z_01a135df-d202-72c9-a227-27b5a63edd86.jsonl`。）

## 5. 可证伪预测（修复判据）

若把 `notified.add` 移到 `:1440` 的 owner 门禁**之后**（即：只有真正要投递的行才记账）：

- 预测 A（探针）：P3 变为 `saw b1=true`（接管 keyB 后 b1 被补推一次），P1/P2/P4/P5/P6 不变。
- 预测 B（历史数据回放）：wfg-rq2-enforcement 应在 **17:22:45 那一波**与 wfg-rq3-safety / wfg-rq1 同批出现（3 条 wfg 回读而非 2 条）；同理 d1 应在 23:56:41 一波、d5 与 d3 应在 watch 回到 mdc 时被补推。
- 反证条件：若修复后 b1 仍不推送，或 wfg-rq2 仍无对应波次，则 C1 不是主因（需转向 C2/C3 或 `triggerTurn` 合并路径）。
- C2 的独立判据：开窗即终态的行，即使 key 正是 watch key，也永不回读（探针 P5）；是否应改为"未 ack 即回读"属产品决策，需与 `notified`/`ackStore` 语义一并定。

## 6. 影响面与未覆盖面

- 影响面：PM 吸收入口（回读投递）、`ack` 引导语、跨 key 批次推进节奏；不涉及 worker 执行、队列写入、门禁判定（只影响"通知"，不影响"事实"——队列行与 widget 都是对的）。
- 未覆盖面（本报告未验证）：
  - 未在**两个真实窗口**下复现跨窗口场景（同一 `.agenticdoc` 被两个 PM 窗口 watch 不同 key 时的行为；`notified` 是窗口进程级，理论上互不影响，但未实测）。
  - 未量化 `triggerTurn` 在 PM 正在跑 turn 时的合并/丢失比例（§2 的"放大"只是代码注释 + 本窗口一次观测）。
  - 未覆盖 gate reminder 通道（`GATE_REMINDER_ENTRY_TYPE`，有独立 watermark 机制）与 widget 渲染路径。
  - C2 的修复方向（是否补推历史终态行）未做产品判断。
  - 未跑任何仓库测试；探针是独立脚本，不构成回归测试。

## 7. 修复方向（仅记录，不实施）

1. **最小改动（对应 C1）**：把 `:1436` 的 `notified.add(entry.taskKey)` 移到 `:1440` 门禁之后（或改为"仅在真正投递成功时记账"），并把 `notified` 的语义写进注释。风险面：跨 key 行若一直不被任何窗口 watch，会**每次轮询反复进入判定**（不投递，但 `notified` 不再增长）——需要确认 `readOutputBody` 等只在投递分支执行（现状 `:1456` 起才读 body，判定分支无 I/O 放大）。
2. **补推语义（对应 C2）**：接管/切换 watch key 时，对该 key 下"终态且未 ack"的行补一次回读（与 `ackStore` 对齐），可避免窗口重启后的回读沉底。需定义去重键（`taskKey` + run id？）。
3. **C3**：无 watch key 时的静默是刻意设计（"no cross-window broadcast"），建议保持；但可在 widget 未处理区加一行"有 N 条未回读终态行"的提示，避免完全无声。
4. 落点均在 `pm/pm-orchestrator.ts` 的 `startWorkerPollLoop` 内（+可能 `ui-bridge.ts`），属共享推送路径，按 AGENTS.md 实现门禁需先开 key（建议 `mw-readback-delivery-scope`），并补回归测试（探针场景可直接转成 `test/suite/` 用例，fake pi + 临时 root 是现成形状）。
