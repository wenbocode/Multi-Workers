# T-05: 度量层 —— `[CLAIMS]` 行解析、run.json 子对象、tokens_per_closed_claim（coding）

- Key: claim-driven-review
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「Worker 执行过程中追踪 goal 一致性」；度量把"审了多少断言"变成可比较的数字）。
- 设计依据：`design.md` §3.4、§7 D-004/D-008。
- 上游实测：
  - `[END]` 行两侧都有锚定正则（`heartbeat.ts:93`、`mw_common.py:2768`），**不得扩 `[END]`**（`evidence/research/spec-rq2-seams-20261020.md` §5.4）。
  - token 归因唯一可靠通路是 `runs.jsonl` 的 `start.session_id` → pi 会话 header `id`（`packages/multi-workers/usage.py:268/427/1010-1014`）；现语料仅 6/115 attempt 可 join（`spec-rq1-review-corpus-20261020.md` §2），**不可近似**。
  - `fetches` 口径固定为 `[FLOW] tool_call` 的读类计数（`design.md` D-008）。
  - `run.json` 现有键集合：`{artifacts, ended_at, exit, kind, last_heartbeat_at, model_exhausted, owner_key, pid, run_id, schema, started_at, status, task_key}`（RQ-1 §2.1）。
- 依赖：T-04 会写 `[CLAIMS] ts claims=<n> closed=<n> partial=<n> unverified=<n> fetches=<n>` 行；本卡按此格式解析，**不等待 T-04 合并**（格式已由 design 固定）。行不存在时必须走 `n/a` 分支。

## 要求

1. `packages/multi-workers/usage.py`：
   - 新增 `parse_claims_line(line) -> dict | None`（严格正则，字段顺序固定；多余字段忽略；缺字段返回 `None`）。
   - 新增 `claims_metrics(run, session) -> dict`，输出 `{claims, closed, partial, unverified, fetches, tokens, tokens_per_closed_claim, attributable}`：
     - `tokens` 来自既有 session join；不可归因时 `tokens=None`、`attributable=False`、`tokens_per_closed_claim="n/a"`；
     - `closed == 0` 时同样 `"n/a"`（不得除零，不得填 0）；
     - 无 `[CLAIMS]` 行 → 整个字典为 `None`（不推断）。
   - 在既有报告构造处把该字段挂到每个 run 上（键名 `claims`），不改变既有键。
2. `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`：
   - `KeyRounds`（`:1541-1546` 附近）旁新增可选 `claims?: {total, closed, partial, unverified, fetches, tokensPerClosedClaim: number | "n/a"}`；
   - `deriveStatusModel` 读 run.json 的 `claims` 子对象（缺失即不设字段，保持既有输出形状）；
   - 面板一行 `claims <total>/<closed>c <partial>p <unverified>u` 只在 `claims` 存在时追加，110 列内不挤掉既有字段。
3. `run.json` 的 `claims` 子对象由 launcher 写入——**本卡不改 launcher**；只消费该键（缺失走上面第 1 条的空分支）。在 `output.md` 里注明这一依赖。
4. 新增测试 `packages/multi-workers/test_claim_metrics.py`：① `[CLAIMS]` 行解析（正常/字段缺/字段乱序/重复行取最后一个）；② 不可归因 → `n/a` 且 `attributable=False`；③ `closed=0` → `n/a`；④ 无 `[CLAIMS]` 行 → `None`；⑤ 同一任务两种拆法的聚合结果可并排（构造两行数据，断言 `tokens_per_closed_claim` 各自独立）。
5. 不改任何既有测试断言；`usage.py` 既有 CLI 输出在无 `[CLAIMS]` 行时逐字节不变。

## 写入允许面

- `packages/multi-workers/usage.py`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- `packages/multi-workers/test_claim_metrics.py`

## 写入禁止面

- `packages/multi-workers/launcher.py`、`autopilot/*.py`（除 usage.py 外）、`packages/coding-agent/src/extensions/agent-team-loop/{pm,worker,shared}/**`、`dist/**`

## 验收命令

```
cd packages/multi-workers
python -m pytest test_claim_metrics.py -q
python -m pytest test_usage_report.py -q
cd ../..
npm run check
```

`test_usage_report.py` 若文件名不存在，用 `Get-ChildItem test_*usage*.py` 找到实际文件名并写明。三条都必须 0 fail。

## 改动历史

- 2026-10-21 创建（无既有改动）

## 交付格式

`output.md` 四段：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。证据段给：新增函数签名 + 行号、五类测试用例计数、pytest 与 `npm run check` 的输出摘要。残留段必须写明"launcher 尚未写 run.json 的 claims 子对象"这一依赖，以及未覆盖的报表形态。
