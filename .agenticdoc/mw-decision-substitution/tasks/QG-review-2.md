# QG 复审 2：修复后复核（review）

- type: review
- owner key: mw-decision-substitution
- 前序：`evidence/quality-gate-report-20261020.md`（PASS-WITH-FINDINGS：0 blocker / 4 major / 9 minor / 3 nit）——
  **本卡必须读它**，任务是核对「4 major + 2 minor 是否真的修好」，不是从零重做审计。

## 上下文

第一轮 QG 复审给出 4 条 major，随后派四张修复卡落地：

| 修复卡 | 目标 | 涉及的写面 |
| --- | --- | --- |
| `FIX-A`（`ds-fix-a-ask-authority`） | MAJOR-1 `ask_decision` 镜像授权表 + 伪 `decision_id`/`acted`；MAJOR-2 state 对 dp1/2/3 恒 `input-incomplete` 且丢 `escalated_reason` | `pm/decision-tool.ts`、`test/suite/decision-tool.test.ts` |
| `FIX-B`（`ds-fix-b-dp-mirrors`） | MAJOR-3 `pm-orchestrator.ts:2044` / `worker-mode.ts:4468` 两处表镜像与 Python L2/L3/L5 降级语义分歧；`acted` 由本地 mode 反推 | `pm/pm-orchestrator.ts`、`worker/worker-mode.ts`、`dp2-narrow.test.ts`、`dp3-answer.test.ts` |
| `FIX-C`（`ds-fix-c-signoff-file`） | MAJOR-4 签收写守卫不覆盖 `worker_file` 通道 | `shared/xkey-gate-guard.ts`、`decision-signoff.test.ts` |
| `FIX-D`（`ds-fix-d-dp1-disagree`） | MINOR-1 dp1 分歧样本被计为采纳；MINOR-5 3a 超限用 `input-incomplete` | `pm/ui-bridge.ts`、`worker/worker-mode.ts`、`decision-association.test.ts`、`dp3-answer.test.ts` |

另有 PM 侧文档改动：`design.md` §3 补 D-038/D-041 + 编号说明（MINOR-6）；`docs/decision-substitution.md` §3 补「档案 `acted` ≠ 消费侧生效」（MINOR-2）、§7 补两条边界（MINOR-3/4）。

## 审计目标

对第一轮 `evidence/quality-gate-report-20261020.md` 的 6 条发现（4 major + 2 minor）做**关闭判定**，
并对修复引入的回归做一次独立复核。具体判定对象：

1. 每条发现：关闭 / 部分关闭 / 未关闭，附 `path:line` 与该结论的反面证据。
2. 修复批次（FIX-A/B/C/D）是否引入新的 D-036 违约、fail-open、跨层漂移。
3. AC-001..015 覆盖矩阵是否仍为 12 covered / 3 partial / 0 missing。
4. 测试有效性：本轮新增用例中至少 3 条是行为级（能抓住回退），不是镜子级。
5. 文档与代码一致：`docs/decision-substitution.md` §3 与 §7 的新增内容。

## 要求（这是本轮的核心）

1. **逐条核对 4 major + 2 minor 是否真的关闭**：对每条给出「改了什么 / 在哪个 `path:line` / 有什么证据能证明现在不会重犯」。判据不是「有改动」，而是**反面用例或变异能红**：
   - MAJOR-1：工具是否**完全**不再读 `.mw/decide-points.json`（`grep` 级证据），`decision_id`/`mode`/`acted` 是否只来自子进程；`acted` 是否还有任何由 `mode` 反推的残留。
   - MAJOR-2：dp1/dp2/dp3 的缺字段清单是否与 Python `REQUIRED_STATE_FIELDS` 真的一致（跨层锁是否真跑 Python，而不是读源码文本）。
   - MAJOR-3：TS 的 `force_off` 判定逐条对 `decision_points.py::_parse_row` 的 L2/L3/L5；L4/L7 是否**没有**被误判成 off。
   - MAJOR-4：`worker_file` 写 `evidence/review/sign-final.md`、`evidence/sign-final.md` 是否真被拒；`evidence/review/<other>.md`、`evidence/research/**` 是否仍可写；write、edit、bash 三个通道是否仍拒。
   - MINOR-1：`disagree + auto` 是否 `acted=false` 且**不写** `decision:` 头行；`agree + auto` 是否仍写；`suggest` 是否仍不写。
   - MINOR-5：3a 超限 trace 是否为 `input-oversize`，且该值是否**没有**污染 Python 的 7 值 `ESCALATED_REASONS`。
2. **回归审计**：修复是否引入新的 D-036 违约、新的 fail-open、新的跨层漂移（尤其 FIX-B 删掉了 `Dp2Authorization.mode` 这类收窄式 API 变更的所有调用点是否真的干净）。
3. **AC 矩阵复核**：AC-001..015 是否仍全部 covered/partial 状态不变；若某条因修复从 partial 变 covered（或反过来），明确指出。
4. **测试有效性抽样 ≥3**：从本轮新增用例里挑 3 条，证明它们是**行为级**而非镜子级（能抓住回退）。重点抽查 `decision-tool.test.ts` 里替换掉的那条「derives mode/acted from the table」以及 `decision-association.test.ts` 的 disagree 用例。
5. **文档-代码一致性**：`docs/decision-substitution.md` 新增的 §3 说明与 §7 两条边界是否与代码一致。

## 交付格式

- `## 结论`：一行判定（PASS / PASS-WITH-FINDINGS / FAIL），并说明 6 条是否全部关闭。
- `## 证据`：6 条逐条的「关闭/未关闭 + path:line + 反面证据」；AC 矩阵复核结果；测试有效性抽样 3 条。
- `## 残留与未验证`：本轮没覆盖到的面（明确写出来，不要沉默）。
- `## 上下文来源`：实际读过的文件清单。
- `## 未覆盖面声明`：显式列出不评估的范围（例如真实启用端到端、`mw build --install` 之后的派发路径、本仓既有的 Windows 环境失败基线）。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 上一轮报告：`.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020.md`（§B major 四条 + minor 前两条）
- 修复卡：`.agenticdoc/mw-decision-substitution/tasks/FIX-A-ask-decision-authority.md`、`FIX-B-dp-mirror-convergence.md`、`FIX-C-signoff-worker-file.md`、`FIX-D-dp1-disagree-oversize.md`
- 契约：`.agenticdoc/mw-decision-substitution/design.md`（D-028/D-030/D-036/D-038/D-041）、`spec.md` §8（AC-001..015）
- 关键实现锚点：`packages/multi-workers/decision_points.py:626`（`REQUIRED_STATE_FIELDS`）、`:884`（`_parse_row` L2/L3/L5）、`packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:640`（四键透传）、`pm/pm-orchestrator.ts:2060`（`dp2RowForceOff`）、`worker/worker-mode.ts:4475`（`dp3RowForceOff`）、`shared/xkey-gate-guard.ts:373`（`isDecisionSignoffEvidenceTarget`）、`:489`（`worker_file` 分支）、`pm/ui-bridge.ts:282`（分歧闸）

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/quality-gate-report-20261020b.md`（**只此一个**；不要改上一轮的 `quality-gate-report-20261020.md`）

## 写入禁止面

- 任何 `packages/**` 源码或测试（本卡只审计，**禁改代码、禁改测试**）
- 任何 `docs/**`、`CHANGELOG`、`design.md`、`spec.md`、`pm-state.md`
- `.mw/**`、`.agenticdoc/**` 下除上面那一个报告文件之外的一切路径
- 禁止 `git` 任何写操作；禁止 `npm run check` / `biome --write`

## 验收命令

本卡无代码改动，验收 = 报告落盘且五段齐全（`## 结论 / ## 证据 / ## 残留与未验证 / ## 上下文来源 / ## 未覆盖面声明`）。
允许运行只读命令取证（grep、read、find、ls，以及对单个测试文件的 vitest --run）。
**禁止**运行 `npm run check`、全量 `test.sh`、`pytest` 全量（耗时且会与并行会话冲突）。

## 改动历史

- 2026-10-20 建卡：修复批次（FIX-A/B/C/D）落地后，按用户要求用配置的 review 模型重跑一次 QG 复核。
