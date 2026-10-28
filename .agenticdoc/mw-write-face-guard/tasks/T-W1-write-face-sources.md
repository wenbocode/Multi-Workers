# T-W1 — 写面数据源现状（RQ-W1）

- type: research
- key: mw-write-face-guard
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md`
- 角色约束: 只读。允许 read/find/grep/ls/bash；**禁止**任何写生产文件、跑 npm install、跑测试写快照。

## 上下文（种子，不是上界）

- 目标锚点：`.agenticdoc/goal.md`（多 Worker 共享同一工作树而不互相破坏）。
- 要回答的总问题：**"这个 worker 允许写哪些路径"今天有没有机器可读载体？在哪渲染、在哪解析、在哪消费？**
- 已坐实事实（可引用，但必须自己复看确认）：
  - 任务书渲染咽喉点：`packages/multi-workers/autopilot/dispatch.py::render_task_md`（读面 cap 的接线范式：`read_file_cap` / `read_byte_cap`，`dispatch.py:742-863`）。
  - 任务卡 envelope 单一判定：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts`（`TYPE_EXTRA_SECTIONS`、coding extras = 写入允许面/写入禁止面/验收命令/改动历史，`:185-200`）。
  - 上游调查结论：`write_scope` / `写面` 生产代码零命中（`.agenticdoc/mw-autopilot-slot-capacity/evidence/research/spec-worker-serialization-20260926.md`）。
- 允许并鼓励自行扩大取证范围（全仓只读，含 `packages/*/dist`、其它 `.agenticdoc/` key、`.mw/`）。

## 要求

1. **穷举"写面/读面"字段消费者**：对 `read_scope`、`deny_globs`、`write_scope`、`写面`、`写入允许面`、`写入禁止面`、`writable`、`allow_write` 逐一 grep，给出：声明处、渲染处（task.md 头 / 卡 envelope）、解析处、运行期消费处，每条 `file:line` + 原文片段。
2. **回答"机器可读性"三态**：每类字段今天是否被生产代码机械解析（是/否/仅散文），否者给出"只有散文"的证据（出现次数 + 位置）。
3. **任务书头部现有字段全集**：列出 worker 模式实际读取的 task.md 头字段（含 `read_scope` / `deny_globs` / `timeout` / `l2_read_*` / `type` 等）及每个字段的解析函数 `file:line`。
4. **运行期写拦截现状**：`worker/worker-file-tool.ts`、`worker/read-scope.ts`、`shared/implementation-gate.ts` 各自拦截什么、用什么匹配（给出判定原文），对"写在写面之外"是否命中。
5. 只读：唯一可写文件 = 上述证据文件。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-write-face-guard/evidence/research/spec-write-face-sources-20261014.md`（结论先行 + 逐条判据 + 残留与未验证 + 未覆盖面声明）
- 每条判据：`文件:行号` + 原文片段 + 计数；未找到写"未找到（命令 + 输出）"，**禁止推测补齐**。
- 末尾给 `[VERIFY]` 行，数值实测打印。
