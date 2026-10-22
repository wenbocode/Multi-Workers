# QG 复审 2C：MAJOR-1 / MAJOR-2 / MINOR-5 关闭判定（review）

- type: review
- owner key: mw-decision-substitution
- 拆分原因：前一次复审（`ds-qg-review-2`）用 `timi/gpt-6.1-sol` 连跑三次都死在
  `stream closed before response.completed`，实测上下文 209.8k–214.2k，超过该模型的 200k 窗口
  （压缩阈值 183,616 只在 turn 结束时才评估，工具循环中途不评估）。本卡把审计面**收窄**，
  要求全程控制上下文（见「上下文纪律」），以便配置的 review 模型能跑完。

## 审计目标

对第一轮 QG 的三条发现做**关闭判定**（只判这三条，不重做全量审计）：

1. **MAJOR-1**：`ask_decision` 工具是否已经完全不再镜像授权表、伪造 `decision_id`、由 `mode` 反推 `acted`。
2. **MAJOR-2**：`ask_decision` 对 dp1/dp2/dp3 的输入契约是否与 Python 权威一致，`escalated_reason` 是否透传。
3. **MINOR-5**：dp3 3a 超限拒发的原因值是否改成 `input-oversize`，且没有污染 Python 的 7 值词表。

每条给「关闭 / 部分关闭 / 未关闭」，判据要能证伪（有反面用例或代码级反例，不是「有改动」）。

## 上下文

- 第一轮报告 `evidence/quality-gate-report-20261020.md` §B 的 major 第 1、2 条与 minor 第 5 条定义了原始缺陷。
- 修复卡 `tasks/FIX-A-ask-decision-authority.md`（MAJOR-1+2）与 `tasks/FIX-D-dp1-disagree-oversize.md`（MINOR-5）。
- 契约：D-036（单一权威：TS 只消费，不镜像）、D-041（`acted` 是消费侧事实）、D-028（超限拒发）、D-030（7 值词表）。

## 要求

1. MAJOR-1 三项分开判：
   - 工具是否仍读 `.mw/decide-points.json`（`grep` 证据 + 是否有任何调用点残留）；
   - `decision_id` / `mode` / `acted` 是否**只**来自子进程 payload（缺键时必须 fail，不得本地补）；
   - 是否存在任何「由 `mode` 推出 `acted`」的残留（全文件搜 `acted`）。
2. MAJOR-2 两项分开判：
   - dp1/dp2/dp3 的必填字段集是否与 `packages/multi-workers/decision_points.py` 的 `REQUIRED_STATE_FIELDS` **实际一致**（把 Python 侧集合抄下来逐项对照；不要只信注释或源码文本锁）；
   - `available=false` 时 `escalated_reason` 是否原样透传给调用者，legacy `reason` 是否没有被它覆盖掉。
3. MINOR-5：3a 超限分支的 trace 原因值；该值是否属于 Python `ESCALATED_REASONS`（若是，说明是「对齐」而非「加宽」；若不是，指出谁该改）。
4. 顺带回答一个契约问题：现在 dp1/dp2/dp3 经 `ask_decision` 恒为 `input-incomplete`（零 spawn），这是否与 AC-012「工具对 worker 可用」冲突？给出你的判定与理由。

## 上下文纪律（硬要求，违反即报告失格）

- 单文件读取一律带 `offset` / `limit`，单次 ≤ 200 行；`worker-mode.ts`、`ui-bridge.ts`、`pm-orchestrator.ts`
  都是 4000+ 行，**禁止整读**，用 `grep -n` 定位后局部读。
- 目标：全程上下文 ≤ 120k tokens（子进程的 session usage 会记录；gpt-6.1-sol 的窗口是 200k，
  超过就 `stream closed`）。感觉接近上限时**先落盘报告骨架再补充**，不要攒到最后。
- `test/suite/*.test.ts` 也只读相关 describe 段，不要整读 1000+ 行的测试文件。

## 交付格式

先写报告骨架（五段标题）再填内容，落盘路径只能是
`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020c.md`：

- `## 结论`：一行判定（PASS / PASS-WITH-FINDINGS / FAIL）+ 三条各自关闭与否。
- `## 证据`：三条逐条「状态 + path:line + 反面证据」；契约问题的判定。
- `## 残留与未验证`
- `## 上下文来源`
- `## 未覆盖面声明`

## 未覆盖面声明（本卡显式不评估）

- MAJOR-3 / MAJOR-4 / MINOR-1（由并行卡 `ds-qg-review-2d` 负责）。
- AC-001..015 全矩阵复核。
- 真实启用端到端（本仓无 `.mw/decide-points.json` 真实 run）。
- `mw build --install` 之后的 L5 派发路径。
- 本仓既有的 Windows 环境类失败基线。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 待判实现：`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:640`（四键透传）、`:296`（`missingDecisionStateFields`）
- 权威对照：`packages/multi-workers/decision_points.py:626`（`REQUIRED_STATE_FIELDS`）、`:88`（`ESCALATED_REASONS` 7 值）
- 超限分支：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4888`
- 反面用例参照：`packages/coding-agent/test/suite/decision-tool.test.ts`（`missing_fields` 用例）、`test/suite/dp3-answer.test.ts`（超限用例）
- 上一轮报告：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md`

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020c.md`

## 写入禁止面

- 任何 `packages/**` 源码或测试（只审计）
- 任何 `docs/**`、`CHANGELOG`、`design.md`、`spec.md`、`pm-state.md`
- `.agenticdoc/**` 下除上面那一个报告文件之外的一切路径
- 禁止 `git` 任何写操作；禁止 `npm run check`、全量 pytest、全量 test.sh

## 验收命令

报告落盘且五段齐全；允许只读取证与对单个测试文件的 `vitest --run`。

## 改动历史

- 2026-10-20 建卡：把 `ds-qg-review-2` 拆成两张窄卡以避开 200k 上下文溢出（该轮 gpt-6.1-sol 三次死于 ~210k）。
