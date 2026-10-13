# T-05 — DRQ-1｜字段注册与三读面贯通（冻结名序 / 序外注册 / fail-closed）

type: research
phase: design
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq1-field-registration-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守并行开发；门禁字段必须贯通三读面才能被看见）。
- 已核实事实（RQ-4 的结论，须自行复看确认）：
  - 存量 gate 共 **34** 个 = v1 29 / v2 5（E2Feature 26 / JCodingAss 8 / Multi-Workers 0），`blocker_class` 缺字段率 **34/34 = 100%**，其中 **29/34 连 `gate_schema` 都没有**。
  - **`blocker_class` 不能进冻结的 40 名序**（4 处测试硬红）⇒ 必须复刻 `authorizes` 的"序外注册"先例；漏注册一处即 fail-closed，**整条队列**在 console/doctor/conductor 一起坏。
  - 最小写入面 = `packages/multi-workers/autopilot/conductor.py` 的 `mark_stalled` `machine_fields` + `_stamp_gate_defaults` 闭集守卫；`gates.create()` 的 13 键与 `gate-writer.ts` 都不动；`contract_guard.py` 零改动（不枚举字段名）。
  - 解析面：Python `autopilot/gates.py:159-174` / `:507` / `:537`；TS 三处 `status-model.ts:751-766` / `:830` / `:796` + `monitor.ts:234 scanPendingGate`；**TS 第 3 个解析面会静默忽略未加分支的新字段**。
  - 缺省语义：**parser 保留 `None`，仅判定层折成 `judgment`**。
- 允许并鼓励自行扩大取证（全仓只读，含 `E:\CLI_workspace\FeatureMigrator`、`H:\git\E2Feature` 的真实 gate 文件）。

## 要求

1. **冻结 40 名序的精确边界**：名序定义在哪个文件/哪一行、包含哪些名、4 处硬红测试分别是什么（`path:line` + 断言形态）。
2. **序外注册先例的完整做法**：`authorizes` 是怎么登记的、有哪些登记点（Python + TS + 测试），照抄时**必须逐个改的清单**（漏一处 = fail-closed，请明确列出"哪些地方漏了会怎样"）。
3. **三读面改动清单**：Python（写入端 + 解析端）、TS 状态模型、monitor 各需改什么，逐条 `path:line`；并回答"如何加一个测试来证明漏注册会 fail-closed"（设计该测试的形态）。
4. **缺省语义的落点**：parser 保留 `None` 与判定层折 `judgment` 分别该在哪一层实现（给行号），并说明为何不能在解析层直接折。
5. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

证据文件必须含以下**四个 H2 段**（逐字）：
`## 结论`（结论先行，3-6 条）、`## 证据`（命令 + 原始输出片段 + `path:line`）、`## 残留与未验证`（没查什么、为什么、风险）、`## 上下文来源`（读过哪些文件的哪些行）。
