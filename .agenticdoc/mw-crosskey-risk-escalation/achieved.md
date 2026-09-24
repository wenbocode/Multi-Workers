# Achieved: mw-crosskey-risk-escalation

> 日期: 2026-09-24 | Phase: DONE
> 触发源：key `mw-worker-visibility-gate` 质检门禁 Q-X-006 / 残留 R-5（用户 2026-09-24 决定「开」）
> 一句话：本窗口派到别键（含 `_scratch`）的 worker 在高风险检查点上现在会唤醒 PM，alert 带 owner key；别窗口的 worker 仍然静默。

## 系统行为变化

### 1. 分化升级的归属判定从「watched key」扩到「watched key ∪ 本窗口派发」

- 变化前：`pm/pm-orchestrator.ts` 的 `startWorkerPollLoop` 分化升级循环只升级 `ownerKeyOf(entry) === watch.key` 的 running worker。本窗口因为门禁兜底或显式 `key:` 派发把 worker 送到 `_scratch`/他键后，该 worker 的 `risk=high` 检查点**不会**投递 PM——它只在底栏面板的跨 key 聚合行里被动可见（`mw-worker-visibility-gate` 交付的那一行），PM 不主动看面板就发现不了。`list_tasks`/`ack_worker_result` 早已按 `dispatchedTaskKeys` 扩了可见面与可操作面，升级面是唯一没跟上的那一个。
- 变化后：
  ```ts
  const ownerKey = ownerKeyOf(entry, agenticdocRoot);
  const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
  if (!watch.key || (ownerKey !== watch.key && !owned)) continue;
  ```
  —— 归属是"watched key **或** 本窗口派发过"。`!watch.key` 短路保留（没在 watch 任何 key 的窗口不会因历史派发记录开始投递）；`dispatchedTaskKeys` 是进程内状态，不持久化、不跨窗口共享，所以**别窗口的 worker 依旧静默**（既有反例用例继续绿，且 M-2 变异证明它真在守卫）。
- 影响面：所有 PM 窗口的分化升级投递；低风险抑制、`escalated` 的 once-per-task 去重、`deliverPmAlert` 的 `triggerTurn` 全部不变。

### 2. 异地 alert 携带 owner key

- 变化前：alert 首句恒为 `[mw] 发散风险：worker '<task>' 检查点 risk=<…>`。
- 变化后：`ownerKey === watch.key` 时**逐字节不变**（`worker '<task>' 检查点 …`，机械字节比对 sha256 全等，533 bytes）；`ownerKey !== watch.key` 时插入 owner 标记：
  `[mw] 发散风险：worker 't-cross'（owner key=_scratch）检查点 risk=high（elapsed …m，reads=… writes=…，phases=…，重复读 top=…）。…`
- 影响面：PM 能立刻分辨"这是我从别键派出去的活"，从而正确选择继续等待 / steer 收窄 / 终止分拆 / 直执；watched key 场景的既有阅读体验与既有断言不受影响。

## 证据

- `evidence/research/spec-crosskey-escalation-baseline-2026-09-23.md`（F1~F4：过滤两分句、`dispatchedTaskKeys` 语义、既有反例守卫用例、投递口无需改动）
- `evidence/research/design-crosskey-escalation-alternatives-2026-09-23.md`（形态选择 / `ownerKeyOf` 必须保留 / 夹具可重现 / 文案条件附加）
- `evidence/verify-independent-2026-09-23.md`（T-3 独立验证：4/4 VC 自建探针复现，M-1/M-2/M-3 三变异"改坏即红 + sha256 复原"，含 HEAD vs current 的 alert 字节比对；回归 183/183 + `npm run check` EXIT=0；git status 起止逐行相同）
- `evidence/quality-gate-report-2026-09-24.md`（质检门禁：11 充分 / 1 有条件 / 0 无证据 → ✅ 通过）
- 两个 worker 的 `workers/*/output.md` 与 `trace.log`（`[VERIFY]` 原始行、TDD 红阶段实测失败输出）

## 偏差

1. 升级循环上方既有块注释末句 "(scoped to the watched key)" 在本次改动后失真，改写为 "(scoped to the watched key ∪ this window's dispatched tasks — … D-101)"；代码语义改动仍限于条件 + 文案两处（+19 行含注释，-3 行）。
2. T-3 的 VC-004 复现使用真实定时器 + 自建 fake pi 探针（任务书允许"fake timers 或自建 pi 桩"），驱动的是真实 `startWorkerPollLoop`；T-1 曾用一次性临时用例做字节比对，T-3 重做为可复跑脚本并保留在报告里。
3. 未改 `pm/ui-bridge.ts`（聚合行与 `PmWatchState` 类型由 `mw-worker-visibility-gate` 交付，本 key 只消费）、未改 risk 判据、未新增导出或去重集合、未做全局广播（D-104 否决）。

## 遗留

| ID | 内容 | 去向 |
|----|------|------|
| R-1 | `dispatchedTaskKeys` 是进程内状态（GC-5 有意为之）→ 窗口重启/复制后，原会话派发的异地高风险 worker 不再主动升级，仅面板聚合行可见 | 接受不处理；未决 Q-1（持久化面）保留为另案议题 |
| R-2 | 更早会话（非本进程）派发的异地高风险 worker 同样只被动可见 | 同 R-1（面板 `risk=high:K` 覆盖 + `list_tasks` 可见） |
| R-3 | 同一 task 被多个窗口同时 watch 时的升级去重（跨窗口层面） | 未决（本 key 不触碰窗口边界语义） |
| R-4 | 本次未做真模型端到端冒烟（升级投递由单测 + 独立探针覆盖；真实链路需一个真会报 risk=high 的 worker） | 由用户在需要时验证（成本高、判据为机器行，收益有限） |
| — | 全局 bundle 重建（`mw build --install`） | 收口时执行；已打开的窗口需重启才加载新逻辑 |
