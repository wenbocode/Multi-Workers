# T-C-D3 — 在飞判定进锁的可行设计（RQ-D3）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-lock-critical-section-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（PM 管多 Worker 并行；文件驱动协调 + 文件锁）。
- 总问题：**"该 task_key 是否已在飞"的判定今天在 `.mw/workers.lock` 之外（判据用 tick 起始快照），两个进程可同时通过判定 → 同一 `task_key` 双写，且 `upsert_worker_row` 的覆盖语义把第二次写掩盖。要放开并发，这个窗口必须先关。**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 判定读快照：`packages/multi-workers/autopilot/conductor.py:620`（`rows = mw_common.parse_workers_file(...)`），在飞集合在 `:698-704` 算出，key 层闸在 `:744`。
  - 写队列的锁：`packages/multi-workers/autopilot/dispatch.py:1155-1156`（`mw_common.acquire_lock(lock)`），写经 `mw_common.upsert_worker_row`（`packages/multi-workers/mw_common.py:2152`，覆盖语义在 `:2161-2171`）。
  - `task.md` 的创建早于取锁：`packages/multi-workers/autopilot/dispatch.py:1132`（`task_dir.mkdir`）区段，取锁在 `:1156`。
  - PM 侧：`packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts:190`（`async upsert(...)` 内 `await acquireLock(this.lockPath)`），锁路径同 `.mw/workers.lock`。
  - 重复写被掩盖的证据：`dispatch.py:1185-1196` 的读回校验只查"恰好 1 行"。
  - 队列列上限：`packages/multi-workers/mw_common.py` 的 `WORKER_COLS_MAX = 9`（TS 镜像 `shared/worker-store.ts`），实测 10 列行两侧判 unparsable。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `dist/`、其它 key、`.mw/`）。

## 要求

1. **临界区边界设计**：给出"读行 → 判在飞 → append 行"必须在同一把锁内完成的最小改动形状（伪码级）。必须回答：谁持锁（调用方还是 dispatch 内部）？PM 侧 `WorkerStore.upsert` 是否已经满足（它内部取锁，但判定在调用方锁外）？两条通道是否要共用一把锁还是引入每 key 独立锁？
2. **`task.md` 先于锁创建**：列出把 `task.md` 创建移到锁内会牵动什么（`dispatch_card` 返回值、`card_path`/`card_sha256` 记录、孤儿 reconcile、PM 侧 `ui-bridge` 的 taskDir 创建），并给最小改法；说明"拒绝路径零副作用"如何满足（不建目录）。
3. **重复派发防护的可证伪测试**：给出一个能在本机跑的双进程对拍方案（例如两个 `python -c` 并发调用同一 dispatch 入口，或注入 `sleep` 到判定与写入之间），说明如何判定"同 task_key 只 append 一行"，以及今天该测试的**期望结果**（应复现双写/覆盖）。
4. **锁粒度与吞吐**：估算锁内新增工作量（在飞集合重算 = O(队列行数)），指出在队列 400+ 行、launcher 每 poll 周期的场景下是否可接受；如不可接受，给出更小的临界区方案（例如先锁内轻量读、再重判）。
5. **与 stage 关闭/提醒抑制的交互**：`_stage_closure`（`conductor.py:1288`）、`pending_gate_reminders`（`conductor.py:3001`）、`_defer_declined_gate`（`conductor.py:7986`）也用同一个在飞谓词；说明进锁后的判定是否要让这三处也同步（还是保持读快照即可），并给出理由。
6. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件: `.agenticdoc/mw-dynamic-concurrency/evidence/research/design-lock-critical-section-20261014.md`（结论先行 + 临界区设计 + 改动清单 + 对拍方案 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印（例：队列行数、某次双写复现的输出）。
