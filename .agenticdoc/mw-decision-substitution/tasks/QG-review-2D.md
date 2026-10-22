# QG 复审 2D：MAJOR-3 / MAJOR-4 / MINOR-1 关闭判定 + AC 矩阵复核（review）

- type: review
- owner key: mw-decision-substitution
- 拆分原因：前一次复审（`ds-qg-review-2`）用 `timi/gpt-6.1-sol` 连跑三次都死在
  `stream closed before response.completed`，实测上下文 209.8k–214.2k，超过该模型的 200k 窗口
  （压缩阈值 183,616 只在 turn 结束时评估，工具循环中途不评估）。本卡把审计面**收窄**，
  要求全程控制上下文（见「上下文纪律」），以便配置的 review 模型能跑完。

## 审计目标

对第一轮 QG 的三条发现做**关闭判定**，并复核 AC 矩阵（不重做全量审计）：

1. **MAJOR-3**：`readDp2Authorization` / `readDp3Policy` 两处 TS 表镜像是否与 Python 的降级语义对齐，`acted` 是否改由子进程 `payload.mode` 决定。
2. **MAJOR-4**：签收写守卫是否覆盖 `worker_file` 通道，同时没有误伤正常 evidence 产物。
3. **MINOR-1**：dp1 分歧样本是否不再被计为「已采纳」。
4. **AC 矩阵复核**：AC-001..015 相对第一轮（12 covered / 3 partial / 0 missing）是否有变化；有变化就指出是哪条、为什么。

## 上下文

- 第一轮报告 `evidence/quality-gate-report-20261020.md` §B 的 major 第 3、4 条与 minor 第 1 条。
- 修复卡：`tasks/FIX-B-dp-mirror-convergence.md`（MAJOR-3）、`tasks/FIX-C-signoff-worker-file.md`（MAJOR-4）、`tasks/FIX-D-dp1-disagree-oversize.md`（MINOR-1）。
- 契约：D-011（dp2 auto 只允许 narrow）、D-036、D-041、D-014（签收固定名）、D-015（写守卫）。

## 要求

1. MAJOR-3 逐条对齐（不要只看注释，要跟 `decision_points.py::_parse_row` 的每个分支对照）：
   - 非对象行 → 该 dp 关；
   - `mode` / `note` / `tier` 类型不合法 → 关；
   - `enabled` 非布尔 → 关；
   - tier 值越界（L4）与 tier 与注册表不一致（L7）→ **不关**（这两条若被误判成关，就是过度拦截，要指出）；
   - `acted` 是否来自子进程 payload（本地读表只能做「是否 spawn」的短路）。
2. MAJOR-4 四项都要试：
   - `worker_file` 写 `evidence/review/sign-final.md` 与 `evidence/sign-final.md` → 拒；
   - `worker_file` 写 `evidence/review/` 下其它文件名 → 放行；
   - `worker_file` 写 `evidence/research/` 下任意证据 → 放行；
   - `write` / `edit` / `bash` 三通道对签收路径 → 仍拒。
3. MINOR-1 三态：`agree + auto` 采纳并写 `decision:` 头行；`disagree + auto` 不采纳且不写头行；`suggest` 不写头行。
4. AC 矩阵复核：只需给出「不变的 12/3/0」或「变化的条目 + 依据」，不需要重列每条的完整证据。

## 上下文纪律（硬要求，违反即报告失格）

- 单文件读取一律带 `offset` / `limit`，单次 ≤ 200 行；`worker-mode.ts`、`ui-bridge.ts`、`pm-orchestrator.ts`
  都是 4000+ 行，**禁止整读**，用 `grep -n` 定位后局部读。
- 目标：全程上下文 ≤ 120k tokens（gpt-6.1-sol 窗口 200k，超过就 `stream closed`）。
  感觉接近上限时**先落盘报告骨架再补充**。
- 测试文件只读相关 describe 段。

## 交付格式

先写骨架再填，落盘路径只能是
`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020d.md`：

- `## 结论`：一行判定 + 三条各自关闭与否 + AC 矩阵是否变化。
- `## 证据`：三条逐条「状态 + path:line + 反面证据」；AC 矩阵复核结论。
- `## 残留与未验证`
- `## 上下文来源`
- `## 未覆盖面声明`

## 未覆盖面声明（本卡显式不评估）

- MAJOR-1 / MAJOR-2 / MINOR-5（由并行卡 `ds-qg-review-2c` 负责）。
- 真实启用端到端、`mw build --install` 之后的 L5 派发路径。
- 本仓既有的 Windows 环境类失败基线。
- 第一轮报告里的 9 条 minor / 3 条 nit 中，除 MINOR-1 之外的部分。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待判实现：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2060`（`dp2RowForceOff`）、`:2349`（`acted` 来源）、`worker/worker-mode.ts:4475`（`dp3RowForceOff`）、`shared/xkey-gate-guard.ts:373`（`isDecisionSignoffEvidenceTarget`）、`:489`（`worker_file` 分支）、`pm/ui-bridge.ts:282`（分歧闸）
- 权威对照：`packages/multi-workers/decision_points.py:884`（`_parse_row` 的 L2/L3/L5 `force_off` 与 L4/L7 仅告警）
- 反面用例参照：`test/suite/dp2-narrow.test.ts`（非对象行、`payload.mode` 覆盖）、`test/suite/decision-signoff.test.ts`（worker_file 拒/放行）、`test/suite/decision-association.test.ts`（disagree 用例）
- 上一轮报告：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md`

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020d.md`

## 写入禁止面

- 任何 `packages/**` 源码或测试（只审计）
- 任何 `docs/**`、`CHANGELOG`、`design.md`、`spec.md`、`pm-state.md`
- `.agenticdoc/**` 下除上面那一个报告文件之外的一切路径
- 禁止 `git` 任何写操作；禁止 `npm run check`、全量 pytest、全量 test.sh

## 验收命令

报告落盘且五段齐全；允许只读取证与对单个测试文件的 `vitest --run`。

## 改动历史

- 2026-10-20 建卡：与 2C 同时拆出，避开 200k 上下文溢出。
