# RQ-3：度量与灰度基线 —— 两种拆法怎么比、advisory 前后怎么取证（research）

- Key: claim-driven-review-orchestration
- type: research
- 唯一证据文件：`evidence/research/spec-rq3-metrics-baseline-20261022.md`（只写这一个文件）

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「解决单 Agent 长上下文溢出和无法并行」——成本必须可测，否则"并行省了钱"只是信念）。
- 承接上游 verify 的两条部分达成：AC-005(a)「1×20 与 4×5 两种拆法的 `tokens_per_closed_claim` 能并排比较」、
  AC-006「advisory 前后既有 review run 的退出码分布与完成率不变」。
- 已知落点：`packages/multi-workers/usage.py:926`（`parse_claims_line`）、`:957`（`_run_claims_counts`）、
  `:1007`（`claims_metrics`，已实测输出 `tokens_per_closed_claim="n/a"` + `attributable=false`）、`:1255`（`_run_detail_row`）；
  `shared/status-model.ts:1552/1717/1750/1901`。上游证据 `claim-driven-review/evidence/t07-e2e-results-20261022.md`。

## 要求

1. **token 归因现状**：`~/.mw/usage/runs.jsonl` 的 `start` 行到底有哪些字段？`session_id` 的写入点与覆盖率的真实数字
   （上游说 6/115 attempt 可 join，复核这个数是怎么算的，给出复算命令与结果）。proxy 侧（`timi-proxy-cli` 记账）
   有没有 per-session token 落盘；若有，join 键是什么。
2. **4×5 对照实验的最小可行形态**：要用同一张 20-claim 卡跑 `1×20` 与 `4×5` 各一次，需要哪些字段才能"并排比较"
   （分母口径：closed 数？子单元求和？merge 单元算不算分母？）。给出报表行的字段设计草案（字段名 + 来源文件 + 缺值语义）。
3. **归因做不到时的替代指标**：如果 token 仍然不可 join，哪些**已经有真值**的指标可以承担"拆分是否划算"的比较
   （例如 `fetches/closed`、`wall clock`、`tool_calls`、`[CLAIMS]` 行里的 closed/unverified 比）。给出取舍。
4. **advisory 基线取证方法**：全库 `.agenticdoc/**/workers/*/run.json` 有多少条可扫？按「卡里有无 `mw-claims` 块」
   分组后，`exit` 分布（0 / 2 / 超时）与完成率的样本量分别是多少（真跑一遍统计，给出数字）。
   指出 retrospective 的混杂因素（时间、模型、任务类型），以及"新窗口观察"需要多长窗口才有统计意义。
5. **可执行统计口径**：给出可直接落地的统计脚本形态（口径 + 过滤条件 + 输出列），不要写代码，只写口径与伪流程；
   并声明哪些字段当前根本不存在（不存在的不许假设）。

## 交付格式

`evidence/research/spec-rq3-metrics-baseline-20261022.md`：
① 结论表（问题 → 结论 → 复核命令/锚点）；
② 归因覆盖率实测数字（含复算命令）；
③ 对照实验字段草案 + 替代指标取舍；
④ advisory 基线样本量与混杂因素；
⑤ `## 未覆盖面`。

## 写入允许面

- `.agenticdoc/claim-driven-review-orchestration/evidence/research/spec-rq3-metrics-baseline-20261022.md`

## 写入禁止面

- 任何 `packages/**` 源码、`claim-driven-review/**`、其他 key、`dist/**`、`~/.mw/**` 的写入（只读不写）

## 验收命令

无（research 只读）；第 1、4 条必须给出**实际跑过的命令与输出数字**，不许写"大概/预计"。
