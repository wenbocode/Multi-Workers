# W3：TS 侧 state 字段去缩写（与 W2 同一映射）

- type: coding
- owner key: mw-decision-substitution

## 上下文

`decide_registry.json` 的 `required_state_fields` 里有 `v`/`dp`/`scope.ext`/`progress.elapsed_min` 这类缩写，用户要求改名。
Python 侧由 W2 同时改，**映射表完全一致**，两边必须一起改完才算通过。

TS 侧现状（行号基于 2026-10-21 工作区）：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:265`：`const state = { v: 1, dp: input.dp }`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`：dp1 state 组装 + `validateStructuredState`
  （`REQUIRED_STATE_FIELDS` 的 TS 镜像，`:365` 附近）+ `scope.ext` 字段
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:2150-2153`：dp2 state（`v: 1`，`progress.elapsed_min`/`budget_min`）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:4993`：dp3 state（`v: 1`、`ambiguity`、`local_candidates`）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:446`：dp1 state 构造（`v: 1`）

## 字段重命名映射（本次唯一口径，禁止自行发挥）

| 旧 | 新 | 说明 |
| --- | --- | --- |
| `v` | `schema_version` | 值从 `1` 升到 `2`（字段名变了就是新 schema） |
| `dp` | `decision_point` | 决策点 id |
| `scope.ext` | `scope.file_extensions` | 允许扩展名 |
| `progress.elapsed_min` | `progress.elapsed_minutes` | 已消耗分钟 |
| `progress.budget_min` | `progress.budget_minutes` | 预算分钟 |
| `key` | `key`（不改） | 与 `decisions.jsonl` 的 `key` 列保持一致，别改成 `agentic_key` |
| `risk_source` / `authority_tier` / `task_summary` / `phase` / `task_type` / `requested_type` / `questions_version` / `ambiguity.kind` / `ambiguity.question` / `local_candidates` | 不改 | 已经是完整词 |

同义清理：代码里 `qid` 仍是内部变量名，不用改；state 里的 `key` 在注释/文档里写成 "AgenticTask key"。


## 要求

1. 按映射表改 TS 侧所有构造/校验这些字段的位置，`schema_version` 的值改成 `2`；`validateStructuredState` 的必填清单同步改名。
2. 不留兼容（不读旧名、不双写）；`docs` 不改（PM 统一改）。
3. 测试：`packages/coding-agent/test/suite/` 下所有涉及这些字段的用例同步改名，包括
   `triage-client-state.test.ts`、`dp2-narrow.test.ts`、`dp3-answer.test.ts`、`decision-tool.test.ts`、
   `decision-association.test.ts` 等（用 rg 找全）。断言语义不能弱化。
4. 若存在 Python/TS 字段一致性测试（例如比对 `REQUIRED_STATE_FIELDS`），同步更新并保证仍能双向发现漂移。

## 验收命令

```bash
cd packages/coding-agent
npx tsgo --noEmit
rg -n 'v: 1|\bdp: |elapsed_min|budget_min|scope\.ext' src/extensions/agent-team-loop --glob '*.ts' | wc -l
npx vitest --run test/suite/triage-client-state.test.ts test/suite/dp2-narrow.test.ts test/suite/dp3-answer.test.ts test/suite/decision-tool.test.ts
```

（`rg` 计数应为 0；`tsgo` rc=0。）

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`
- `packages/coding-agent/test/suite/*.test.ts`（只改字段名与相关断言）

## 写入禁止面

- `packages/multi-workers/**`（W2 在改）
- `packages/ai/**`、`docs/**`、`.agenticdoc/**`、`.agents/**`、`.mw/**`
- 禁止 `git` 写、`npm run check`、`npm run build`、`mw build --install`、全量 vitest、真实网络、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 三条验收原文（tsgo 全量输出尾部 + rg 计数 + vitest 汇总）/ 改过的测试清单 / 残留。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 跨语言契约：Python `decision_points.REQUIRED_STATE_FIELDS:872` 是权威（W2 正在改名），TS 侧只是镜像，
  改完两边键名必须逐字一致；dp3 的 `local_candidates` 与 `ambiguity` 结构不变
- 已知常量：`DP3_MIN_CONFIDENCE=0.7`、`DP3_ANSWERABLE_MIN=0.5`、`DP3_MIN_MATCH_SCORE=0.75`（`worker-mode.ts:4434/4440/4444`）

## 改动历史

- 2026-10-21 建卡：与 W2 同批，TS 侧 state 字段去缩写。
