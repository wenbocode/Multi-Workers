# T-C1 — 派发链与串行点（RQ-C1）

- type: research
- key: mw-dynamic-concurrency
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-dispatch-chain-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**并发今天在哪些点被串行化？要放开 per-key 与 key 层，必须改哪些点？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - key 层闸：`packages/multi-workers/autopilot/conductor.py:744`（`len(in_flight_keys) >= max_parallel_keys` → continue）。
  - per-key 串行：`conductor.py:742-745`（`if key in in_flight_keys: continue`）+ `execute_loop` 的 per-key serial（`:1771`）。
  - 队列唯一消费者：`packages/multi-workers/launcher.py:819-841`；PM 通道入口 `pm/ui-bridge.ts:2201`。
  - 上个 key 的串行点清单：`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md`（`serialization_points=7`）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 dist、其它 key、`.mw/`）。

## 要求

1. **`orchestrate` 每 tick 的派发链**：从进入 key 循环到 `_advance_key` 返回，逐段给 `file:line` + 判定原文，标注"本轮最多派 N 个"的点。
2. **per-key 串行点穷举**：任何使"同一 key 同一时刻只有一个在飞 worker"成立的判断（含 `_phase_artifact_present` 分支、`execute_loop` 的 `return False`、`_verify_loop`），每条给 `file:line` + 触发条件 + 是硬顺序还是可并行。
3. **两条通道共享证据**：给出"PM 手工派发行被 conductor 计入 key 在飞"的逐行证据（`_is_in_flight` / `_row_belongs_to` / `mw_common.row_belongs_to`）。
4. **放开点清单**：列出要放开 key 层与 per-key 并发必须修改的确切函数，每项给：当前判定原文、改后需要的输入（前沿/写面）、并发安全性（是否需持锁）、首个失败模式。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-dynamic-concurrency/evidence/research/spec-dispatch-chain-20261014.md`（结论先行 + 逐条判据 + 放开点表 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
