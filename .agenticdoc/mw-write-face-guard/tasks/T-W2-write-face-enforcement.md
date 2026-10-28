# T-W2 — 派发层插入点与重叠判定可行性（RQ-W2）

- type: research
- key: mw-write-face-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-enforcement-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**写面重叠拒绝应该插在哪？两条派发通道各自的入口在哪？判定所需数据今天是否已经在队列行里？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - conductor 派发入口：`packages/multi-workers/autopilot/conductor.py` 内多处 `dispatch.dispatch(...)`（`:1196`、`:1605`、`:1643`、`:2369` 等）；`dispatch.dispatch` 定义在 `packages/multi-workers/autopilot/dispatch.py:964` 起。
  - PM 派发入口：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2201`（`dispatch_worker` 工具）。
  - 队列唯一消费者：`packages/multi-workers/launcher.py:819-841`。
  - 行渲染/解析：`packages/multi-workers/mw_common.py`（`parse_workers_file` / 槽位保持写）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 dist、其它 key、`.mw/`）。

## 要求

1. **两条通道的派发入口清单**：每处 `file:line` + 触发条件 + 该处能看到的输入（owner key、task 类型、任务书路径、卡路径）+ 是否共用同一底层函数。
2. **`_workers.parallel` 行的现有列与语义**：逐列给出解析函数 `file:line` + 是否有承载写面的列/载荷；若没有，给出"新列/新载荷"对现有读者（launcher / conductor / TS monitor / worker-store）的影响面清单。
3. **读面 glob 的既有匹配语义**：`read_scope` / `deny_globs` 的实际匹配实现（大小写、`**`、Windows 分隔符、绝对/相对根），给判定原文；据此评估"写面 glob 交集"能否复用同一语义，指出分歧点。
4. **插入点候选**：列出 ≥3 个候选插入位置（conductor dispatch 前 / PM dispatch_worker 前 / launcher spawn 前），每个给：能看到的在飞行集合、并发安全性（是否需持 `.mw/workers.lock`）、首个失败模式。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-enforcement-20261014.md`（结论先行 + 逐条判据 + 候选表 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
