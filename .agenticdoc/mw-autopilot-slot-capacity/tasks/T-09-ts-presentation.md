# T-09: 三层呈现（层 A/B + 字段镜像 + DRIFT + 禁 LLM）

- 波次: **1** · 依赖: T-02, T-03
- 写面（独占）: 
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`（字段镜像段）
  - `packages/coding-agent/test/suite/autopilot-gate-presentation.test.ts`（新建）
- AC: AC-007, AC-012, AC-021, AC-026 · VC: VC-008, VC-014, VC-027, VC-028, VC-037, VC-038
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

门"没有内容量"（人审看不到判断所需信息）的第一个补面：三层呈现全部**机器可判**，缺字段一律唯一哨兵，禁用 LLM 生成。

## 交付物

- 层 A `monitor.ts`：`MonitorGate` 补 `created_at`（`:89-96` 现缺，导致面板不显示时效）；每门 1 行、`len ≤ MONITOR_LINE_MAX=110`（`:61`）；超长截断**头保留**（`:531-533`）；渲染含 `DRIFT(` 标记（`mtime > created_at`）。
- 层 B `console.ts` `cmdGates`：每门**恰好 13 行**、序固定、每行 ≤110 列 ⇒ 总行数 `1 + 13*N`；L6 证据、L8 同 scope 已答门（重放可见性）、L9 `expires_at`/`default_action`、L12 `open_items`、L13 `answer_source`。
- 字段镜像：`GATE_FRONTMATTER_FIELDS`（`status-model.ts:572-587`）与 Python `FRONTMATTER_FIELDS` **逐项同序**（含 28 新字段与 `gate_schema` 位置）；`GateRecord`（`:587-597`）按需扩。
- 禁 LLM 源码断言：`monitor.ts` / `cmdGates` / `_doctor_gates` 三个渲染函数体内 `dispatch`/`model`/`provider` 零命中。
- 自动决策可见性：面板/conductor 行显示 `auto=off|shadow|live`（键由 T-03 提供）。

## 契约（不得重定义）

- 唯一缺失哨兵字面量 = `unknown (no field)`（全仓唯一，逐字）。
- **禁止**从 `question`/`note` 散文反解字段；`note` 只作逐字引用。
- `missing` 只对 **pending 门**报（34 个历史门不得刷屏）。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-gate-presentation.test.ts`

## 非空洞对照（必须附在回执里）

- N=1/3 个 pending 门 ⇒ 行数必须分别 `14`/`40`（`1+13N`）；改一处渲染就会红。
- 字段全缺 fixture ⇒ 对应行**逐字**含 `unknown (no field)`，且不含"大概/可能/推测"。
- 删掉 DRIFT 标记 ⇒ 漂移 fixture 必须红。
- 渲染行超 110 列 ⇒ 行长断言必须红。

## 风险与注意

- `status-model.ts` 与 T-02 同文件 ⇒ T-02 先提交；`worker-store.ts` 属 T-12，本卡不碰。
- 行数固定契约（`1+13N`）修正了 RQ-14 的"≤N 行"矛盾：13 行是**每门**。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-09-ts-presentation/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
