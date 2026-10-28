# 调研声明 — spec（mw-write-face-guard）

- **key**：mw-write-face-guard
- **日期**：2026-10-14
- **类型**：本 key 需要外部/代码事实调研（非零调研声明）

## 目的

写面门禁的 spec 关键决策（§1 范围 / §2 约束 / §4 风险）需要现状事实：写面今天有没有载体、在哪渲染、在哪消费、
派发层能不能插入、历史多写事故给了什么最小护栏。三项调研**只读**、互不重叠、各写唯一文件。

| RQ | 问题 | 产出文件（唯一写者） |
|---|---|---|
| **RQ-W1** | 写面数据源现状：任务书 / 任务卡里今天有哪些写面相关字段（`read_scope` / `deny_globs` / `write_scope` / 写入允许面 / 写入禁止面），在哪渲染（`render_task_md`）、在哪解析（`dispatch-card.ts`）、在哪消费（worker 运行期），各自是否机器可读 | `evidence/research/spec-write-face-sources-20261014.md` |
| **RQ-W2** | 派发层插入点与重叠判定可行性：两条通道（`autopilot/dispatch.py::dispatch`、`pm/ui-bridge.ts::dispatch_worker`）的派发入口、`_workers.parallel` 行现有列/载荷、写面 glob 交集判定的既有语义（读面 glob 实现）、可插入点清单 | `evidence/research/spec-write-face-enforcement-20261014.md` |
| **RQ-W3** | 历史同文件多写事故与最小充分护栏：`_pitfalls.md` P-018/P-019、PM 手工通道并发重叠实测（同 key 峰值 6）、已有护栏（implementation-gate / worker-file-tool / xkey-gate-guard / protected-config）覆盖面与缺口；哪些护栏已被上一个 key 否决/接受 | `evidence/research/spec-write-face-safety-20261014.md` |

## 事实基线（可直接引用，须自行复看确认）

- key 层唯一并发闸：`packages/multi-workers/autopilot/conductor.py:744`；per-key conductor 串行 = 1（`:742-745`、`:1771`）。
- 两条通道共用队列与唯一消费者：`packages/multi-workers/launcher.py:819-841`。
- 写面纪律现状：`write_scope` / `写面` 生产代码零命中（上个 key `mw-autopilot-slot-capacity` AC-014/RQ-5）。
- 任务卡 envelope 单一判定：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:418`（`inspectEnvelope`）。

**约束**：三项 RQ 全为**只读**；不得改任何生产文件；结论必须给 `file:line` + 原文片段，未找到写"未找到（命令 + 输出）"，
禁止推测补齐；推算值必须标注。
