# D2 设计调研：决策档案写入器（4 类行）+ 读侧折叠 + 幂等

- type: research
- 唯一证据文件: `.agenticdoc/mw-decision-substitution/evidence/research/design-decision-archive-20261019.md`
- goal 锚点: `.agenticdoc/goal.md`（"文件驱动的去中心化协调"）
- 超时: 30m

## 上下文（已冻结）

spec §6：`.agenticdoc/_autopilot/decisions.jsonl`，一行一事件，`kind ∈ {decide, override, settle, authority-change}`，append-only + `prev_sha` 哈希链 + 单写者；`decision_id = "<dp>:<trigger_id>"`；与既有 11 字段传输行并存不升级。

可复用先例：`packages/multi-workers/decision.py:945-961`（`_append_evidence`，只 `open("a")`）、`mw_common.py:1620-1642`（`decide_last_evidence` 尾扫 + 坏行返回 None）、`mw.py:845-878`（`_decide_show_payload`）、`packages/multi-workers/autopilot/conductor.py:7638-7647`（`_append_auto_decision_row`）、`:7650-7664`（正向行 + 负行集合运算）、`:7683-7703`（`revoke_auto_decision` 负行四字段）、`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:645-664`（`recordDispatchAlarm` 只 append）。

## 要求（逐条回答，每条带 path:line）

- **RQ-1 写入器接口**：单个模块（建议 `packages/multi-workers/decide_archive.py`）的公开函数签名：`append_decide / append_override / append_settle / append_authority_change / iter_rows / fold`。每个函数的入参校验与返回。给出代码骨架。
- **RQ-2 seq 与 prev_sha**：`seq` 如何取（读尾行 vs 计数）、并发下的正确性证明（锁的持有范围必须覆盖"读尾 → 算 sha → 追加"）、首行约定、坏尾行（半行 JSON）如何恢复（直接追加新行会断链，给方案）。`prev_sha` 的规范化输入具体是什么 JSON 序列化（`sort_keys` / `separators` / `ensure_ascii`），必须与 `decision.py:402-417` 一致或明确说明不同。
- **RQ-3 幂等**：同一 `trigger_id` 重复写 `kind=decide` 的拒绝实现（扫全文 vs 尾 N 行 vs 辅助索引）；冲突时的行为（exit 码/异常类型/是否落一行 `note=duplicate-suppressed`）；性能上限（档案 1 万行时的扫描代价与可选优化）。
- **RQ-4 4 类行的字段矩阵**：逐 kind 列出必填/可选字段与取值域（含 `authority-change` 的 `by ∈ {human, human:p0-confirm, signoff:continue|narrow|revoke, refresh}`、`escalated_reason` 5 值、`outcome` 5 值）。给一张可直接落代码的字段表。
- **RQ-5 读侧折叠 `fold(rows)`**：按 `decision_id` 分组、组内按 `seq` 排序的折叠规则；`outcome` 取最后一条 settle（无则 pending）；override 只在有行时置 true；坏行跳过计数；`orphaned` dp 的行是否仍折叠（应保留，说明理由）。
- **RQ-6 与 11 字段行对账**：同一决策在两文件各一行时如何对账（`(ts,dp)` + `state_digest`）；`state_digest` 只在档案行有、传输行没有的情况下具体算法；对不上时报告什么。

## 写入允许面

- `.agenticdoc/mw-decision-substitution/evidence/research/design-decision-archive-20261019.md`

## 写入禁止面

- 任何源码（`packages/**`）、配置（`.mw/**`）、其它 key 目录、其它 evidence 文件
- 禁止 `git add` / `git commit` / `git checkout` / `git stash`

## 交付格式

- 只写唯一证据文件；`## Q1..Q6` + 末尾 `Q-answered: 6/6`；结论带 `path:line`；未确认写"未验证"。
- 不修改源码/配置；不做 git 操作。

## 验收命令

```
grep -c '^## Q' .agenticdoc/mw-decision-substitution/evidence/research/design-decision-archive-20261019.md
```
期望 6。
