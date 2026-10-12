# 运行时回写观测：老副本 `upsert` = 全表 9 列重写（2026-10-10 18:09–18:20）

- 关联：`incident-in3-queue-reenqueue-20261010.md`（IN-3）、D-044/D-046、T-15/T-18
- 观测者：PM（只读 + 归一写，无进程操作）
- 环境：`mw serve` PID 14240，launcher PID 4756；全局扩展副本 `~/.pi/agent/extensions/agent-team-loop.js` 时间戳 **2026-10-10 10:53:02**（不含 T-15/T-17/T-18/T-19/T-20/T-22 源码改动）；HEAD `776b82d7f`

## 1. 机制（源码级确认，非推断）

```
$ git show b8bc115ff:packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts
  async upsert(entry: WorkerEntry): Promise<void> {
      const existing = this.readAll();                       // 解析全表
      const content = `${existing.map(serializeWorkerLine).join("\n")}\n`;   // 重写全表
      fs.writeFileSync(tmpPath, content, "utf8");
```

- `readAll()` = `lines.map(parseWorkerLine).filter(...)` ⇒ **不可读行静默消失**（IN-3 放大器 F4）；
- `serializeWorkerLine` 输出恒 **9 列**（`origin` 末列，缺省物化为 `manual`）。
- 该代码就是此刻**运行时里跑的东西**（10:53 副本 = `b8bc115ff` 代）；T-15 的槽位保留写入只在**源码**里。

## 2. 现场实测（两次独立复现）

`dispatch_worker` 每派一次任务，队列列宽即被整表翻成 9：

| 时刻 | 动作 | 归一前 | 归一后 |
|---|---|---|---|
| 18:09:08–18:09:35 | 派 T-01/T-02/T-03/T-04/T-05 | `{9: 258}` | `{8: 258}` |
| 18:19 前后 | 派 T-09 | `{9: 259}` | `{8: 259}` |

两次归一均：`unparsable=0`、`conductor 行=0`、`origin` 全为 `manual` ⇒ **无损**（缺失 `origin` 在 TS store 里归一为 `manual`，在 Python 里 `worker_is_conductor` 判定同 false）。

归一工具（T-18 的槽位保留写者，逐行替换、不重排、不改其它行字节语义）：
`evidence/scripts/t23-normalize-whole-queue.py`（幂等；先 `before/after` 打印，带 unparsable/conductor 前置拒绝）。

## 3. 风险闭环

- **触发条件**：9 个 10-10 10:53 之前启动的长驻 pi 窗口（PID 80740/25704/50032/95236/30656/10604/18200/117296/136660）内存里是 pre-`b8bc115ff` 的 **7..8 列**读法；9 列整表 ⇒ 它们读到 **0 行**。任一窗口 `agent_settled` 即可能重演 IN-3（且 `max_workers=None`，launcher 上界也不在运行时）⇒ 250+ 任务重派。
- **本次缓解**：每次派发后立刻把整表归一到 8 列（唯一旧新解析器都能读全的列宽）。8 列 **同时**验证了 AC-023 的双向容差在真实队列上成立。
- **根治**：① `mw build --install --allow-dirty` 刷新全局副本（内部会跑根 `npm run build`，需用户明确请求）；② 重启 launcher/serve；③ 9 个旧窗口重启（否则内存里的旧解析器永远在）。
- **残留**：只要运行时未切换，下一次派发就会再翻一次 ⇒ 归一脚本须作为每次派发的固定后置步骤；D-046 已据此约束后续动作（或在切换前停用派发）。

## 4. 与既有证据的关系

- 这是同一机制（列宽漂移 8↔9 + parse-all/rewrite-all）在**当前运行时**的现场重现，与 IN-3 的 02:50 事故同源；
- `test_in3_queue_replay.py` 的“旧 codec 丢 250/250”断言在此得到真实队列侧证（9 列整表在旧读法下同样归零）。

## 5. 现场观测：终态回读的**假 failed**（T-08，2026-10-10 18:16-18:24）

这一节记录一次非计划的现场实验，它同时（a）验证了 AC-022 的必要性，（b）让我犯了一次重复派发。

### 5.1 事实（可复核）

| 项 | 值 | 证据 |
|---|---|---|
| T-08 worker 启动 | 10:16:51.278Z（本地 18:16:51），pids 只有一条：`[START] pid=93028` | `workers/mwg-t08-g2-surfaces/trace.log` 首行；`worker.log` 只有 **1 条** `[worker] start` |
| 框架给出的终态 | 派发后约 **3 秒** 报 `mwg-t08-g2-surfaces failed`（“无 output.md 摘要”） | mw 服务回读消息；队列该行当时确为 `failed` |
| worker 实际结局 | `[worker] done exit=0 elapsed=5m tools=72 tool_errors=10` | `worker.log` 第 2 行 |
| 交付物 | `output.md` 2427 B、`report.md` 10200 B（均写在 18:22:00-18:22:21） | 目录 mtime |
| 队列行最终值 | `failed` → `done`（由 launcher 在 worker 真正退出后回写） | 队列快照（18:20 为 `failed`，18:24 为 `done`） |
| PM 独立复核 | `autopilot-monitor.test.ts + autopilot-gate-presentation.test.ts + autopilot-console.test.ts` = **73 passed**，`[VERIFY] VC-011: age_shown=true blocked_marker=true` | 本次运行输出 |

⇒ **框架在 worker 仍存活时给出了终态 `failed`**，且该判断持续了约 5 分钟（直到 worker 真正退出）。注意：该时刻**没有** `run.json`（运行时是 10:53 老副本，不含 T-20 的 worker 自写状态），因此 launcher 没有产品侧终态可依据。

### 5.2 机制：已坐实 vs 仍是假设

- **已坐实**：`failed` 出现在启动后 3 秒；worker 进程（pid 93028）随后继续运行 5 分钟并以 exit=0 结束；行最终被回写为 `done`。
- **已坐实**：同一时刻我正在跑**无锁逐行**的 v1 归一脚本（见 §3/D-050），它在 18:16:5x 正在整表重写队列；T-08 自己的 `worker.log` 里就留下了一行 `3] Permission denied: ..._workers.parallel`（它的某个启动期写队列动作被我的写者挡住）。
- **假设（未坐实，需后续复现）**：spawn 握手与并发队列写者相撞 ⇒ launcher 的启动期 `update_status(running)` 或进程注册被挡/错过 ⇒ 下一次 reconcile 依据“无 pid/无产物的静默行”判 `failed`。没有直接日志能把这条链路钉死（老副本的 reconcile 无 `lost`/`run.json` 分支）。
- **不假设的部分**：这不是“PM 读错”的问题——队列行本身就是 `failed`，读回读只是如实反映它。

### 5.3 处置

1. **PM 误信该回读 ⇒ 重复派发**：18:17:34 我按 AC-022/框架约定以新 key `mwg-t08b-g2-surfaces` 把同一张卡又派了一次（当时判断是“3 秒即死的空跑”）。
2. **止损**：18:23:43 前 T-08b 仍在**只读调查**阶段（trace 显示它在读 T-08 的 task.md/报告、`git diff`，未写任何文件），遂 PM 直执 kill **PID 144224**（T-08b，属我自己派发的重复 worker）；文件 mtime 证明 `monitor.ts`(18:20:41)/`autopilot-monitor.test.ts`(18:21:11) 的写入全部来自 T-08 那一个进程 ⇒ **重复写未发生、T-08 交付完好**。
3. T-08 交付经 PM 独立复核（73 passed）后按 **done** 核销；T-08b 按 `failed`（人工终止）核销并记 `[supersedes]` 关系。

### 5.4 教训（纪律级）

- 在**运行时未切换**（无 `run.json` 产品侧状态）的当前环境里，**终态回读不可信**：任何 `failed` 结论在重派前必须先看 `worker.log` / `trace.log` / `output.md` / 进程表三件套。本次若先看一眼 `worker.log` 就会看到 `elapsed=5m` 仍在跑。
- 这正是 AC-022 第 ③ 条要求的产品侧意义：**worker 自报状态**（`run.json` 的 `running`/终态 + `output.md` marker）是唯一能压住“spawn 竞态下被误判终态”的东西；T-20 已实现（launcher 只允许补 `lost`，且 `[END]`/run.json 终态优先），但**尚未切换运行时**（D-043）。
- 残留 **R18（新）**：即便切换运行时，仍应有一条机器判据锁住“**刚派发的行不得被静默判 failed**”（例如：无 `run.json` 且行龄 < 握手窗口 时，reconcile 只能保持 `running`）。当前无此用例 —— 建议后续 key 或本 key 的补充卡处理。
