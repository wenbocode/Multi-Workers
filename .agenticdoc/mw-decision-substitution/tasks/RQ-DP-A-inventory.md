# RQ-DP-A：dp1..dp6 决策点清单（说明文档素材）

- type: research
- owner key: mw-decision-substitution

## 上下文

PM 要写一份给用户看的「全部决策点说明文档」：每个 dp 对应什么、什么条件触发、传给 jev 的 state 长什么样、
代码在哪。本卡负责 dp1..dp6 这 6 个 dp 的事实采集，只读、不改代码。

事实入口：

- 注册表：`packages/multi-workers/decision_points.py` 的 `DP_REGISTRY`（每个 `DecisionPoint(id, tier, default_enabled, default_mode, questions, build_state, executor, questions_version, description, p0_consequences)`），`DecisionPoint` 定义在 `:280` 附近。
- 泛型 state 组装：`packages/multi-workers/decision_points.py:349 _state_builder`（`v`/`dp`/`trigger.data`/`key`/`task_key`/`questions_version`）。
- 未接线执行器：`decision_points.py` 的 `_unwired_executor`。
- TS 侧触发/组装：`packages/coding-agent/src/extensions/agent-team-loop/`（`worker/worker-mode.ts`、`pm/pm-orchestrator.ts`、`pm/triage-client.ts`、`pm/decision-tool.ts`）。
- 人用通道：`packages/multi-workers/mw.py`（`decide run` / `decide ask`），`decide_for` 在 `decision_points.py`。

## 要求

对 dp1..dp6 每个 dp 都给出下面 6 项，每项必须带 `path:line`：

1. 注册身份：`id`、`tier`、`default_enabled`、`default_mode`、`description`（逐字短摘 + 行号）。
2. 触发点：**谁在什么条件/阈值下调用它**。给调用点 `path:line` 和判定条件原文。找不到就写
   `未接线（已查 <你实际搜过的关键词>）`，**不要猜**。
3. state 形状：由谁组装（泛型 `build_state` / TS 手工组装 / 调用方 request file）、字段清单（字段名 + 含义 + 是否必需）、
   以及 state 里是否带 `local_candidates` / `rendered` 这类动态键。dp3 若有专门 shape 请完整列出。
4. questions：每个题的 `id`、`type`（noul/choice/score）、`choices`/`dynamic_choices`、`labels` 是否有、
   `criteria` 是否有、`instructions` 一句短摘，以及 `questions_version` 值。
5. 答案怎么被采纳：`acted` 的含义、写入点（steer / narrow / escalate / 只留痕）、置信阈值常量（给 `path:line`）；
   若执行器是 `_unwired_executor`，明确写「注册但无执行器，只有 `mw decide run` 可手工调用」。
6. 风险语义：该 dp 的 tier（P0/P1/P2）与 `enabled` 默认值/`--i-understand-p0` 的关系，一句话。

禁止：跑 `mw decide run/ask/probe`（联网归 PM）、改任何代码、跑测试、`git` 写操作。

## 唯一证据文件

`.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-A-20261021.md`

结构：先一张 6 行汇总表（`dp | tier | 默认 enabled/mode | 触发点 path:line | questions 类型 | 采纳落点 path:line`），
再每个 dp 一小节（`## dpN-…`六项要点）。所有行号取自你实际读到的文件版本。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/dp-inventory-A-20261021.md`（唯一）

## 写入禁止面

- 其它任何文件；特别是 `packages/**`、`.agenticdoc/**` 除上面那一个文件、`.agents/**`、`.mw/**`

## 交付格式

返回给 PM 的正文 = 那张 6 行汇总表 + 每个 dp 一行"未接线/已接线 + 采纳落点"。细节留在证据文件里，
不要在正文重复长段。若某 dp 找不到触发点，单独列一节「未接线清单」并写明你搜过哪些关键词。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 已知事实：24 个 dp 全部是 noul/choice（无 score）；`dp1/dp2/dp3` 在本仓 `enabled=true mode=auto`；
  dp4/dp6/dp8/dp10/dp11/dp12 在本仓 `enabled=false`（`mw decide dp list` 输出，2026-10-21）
- 参照文档：`docs/decision-substitution.md`、`.agenticdoc/mw-decision-substitution/spec.md`（AC-001..015）
- 已知锚点：`decision_points.py` 的 `DP_REGISTRY` / `_state_builder:349` / `_unwired_executor`；
  `worker-mode.ts:4434 DP3_MIN_MATCH_SCORE`、`:4440 DP3_MIN_CONFIDENCE`、`:4444 DP3_ANSWERABLE_MIN`；
  `mw.py` 的 `_decide_run` / `_decide_ask`

## 改动历史

- 2026-10-21 建卡：为用户版决策点说明文档采集 dp1..dp6 事实。

本轮范围（逐个 dp 都要覆盖）：`dp1-dispatch-type`、`dp2-checkpoint-split`、`dp3-worker-clarify`、`dp4-failure-handling`、`dp5-test-triage`、`dp6-qg-verdict`
