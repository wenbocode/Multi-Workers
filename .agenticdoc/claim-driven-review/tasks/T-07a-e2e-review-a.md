# T-07a — 断言驱动审查端到端（A 卡：常量与派发顺序）

type: review
phase: execute
key: claim-driven-review
覆盖 AC: AC-001, AC-002, AC-005, AC-007（常量面 + conductor 侧顺序）
依据: `.agenticdoc/claim-driven-review/design.md` §2.3（单源常量表）、§4（预算推导）、§6.1（conductor 三处落点）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（"审查成本与断言数量绑定、与仓库规模解绑" —— 本卡是这条目标的第一次端到端实例：你只需判定 5 条断言，不需要通读仓库）。
- 审计对象（本 key 本相位刚落地的代码）与已核实锚点：
  - TS 常量单源：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:535`（`CLAIM_TYPES`）、`:547`（`UNVERIFIED_REASONS`）、`:565`（`CLAIM_GATE_DEFAULT`）、`:573`（`CLAIM_BUDGET`）。
  - Python 镜像与 conductor 顺序：`packages/multi-workers/autopilot/dispatch.py:654`（`parse_claims_block`）、`:735`（`claim_gate`）、`:805`（`_read_scope_caps`）、`:2080-2090`（caps 计算在 `dispatch_card` 之后）。
- 本卡的断言清单在文末 `<!-- mw-claims: v1 -->` 块内，是唯一审计范围：**只判定这 5 条**。

## 审计目标

对上述 5 条断言逐条判定，给出 `成立 / 部分成立 / 不成立 / 无法判定` 之一，并附可独立复现的证据。**零写入**（唯一产物是本 worker 目录的 `report.md`）。禁止只复述断言；断言不成立时给出最小反证（`path:line` 或命令输出）。

## 要求

1. 逐条读断言指向的 `定位` 文件（`read`），用 `grep` 复核 `判据` 列的字面量是否真的存在且取值一致。
2. 每条断言的 `取数` 列填你**实际读文件的次数**（`read` 调用次数，不是 grep 次数）；`取数` 之和不得超过 `判据` 列预算之和。
3. 无法判定时必须用固定的 7 词原因之一：`budget / no-access / not-found / ambiguous / environment / out-of-scope / awaiting-input`，不得自造词。
4. 证据必须落在项目内真实文件上（`path:line` 或 `path:a-b`），**不得**把 `report.md` / `output.md` / `task.md` 当作唯一证据。
5. 若你把某条断言判为 `closed`，必须同时给出 `判定`（成立/不成立）；`closed` 不等于 PASS —— 判定"不成立"也是 `closed`。发现断言不成立**不要修复**，如实记录。

## 未覆盖面声明

必须显式声明未覆盖的范围（例如：只读了断言指向的两个文件，未读 worker/pm 侧接线；未跑任何测试；未在 enforce 模式下验证等）。

## 交付格式

`report.md` 必须含以下逐字 H2 段：`## 结论`、`## 证据`、`## 断言裁决`、`## 未覆盖面声明`、`## 上下文来源`。

`## 断言裁决` 必须是**七列表格**，表头逐字为：

```
| claim | 类型 | 裁决 | 判定 | 证据 | 取数 | 原因 |
```

- `裁决 ∈ {closed, partial, unverified}`；`判定 ∈ {成立, 不成立, 无法判定}`；两列分置。
- `unverified` 行的 `原因` 取上面 7 词之一；`closed` / `partial` 行的 `原因` 写 `-`。
- `证据` 写 `path:line` 或 `path:a-b`（相对项目根）。
- 5 条断言必须一行不少，id 与卡内 block 完全一致（`C-01`..`C-05`）。

<!-- mw-claims: v1 -->

| claim | 类型 | 陈述 | 反证条件 | 定位 | 判据 | 预算 |
|---|---|---|---|---|---|---|
| C-01 | grep | `CLAIM_BUDGET` 的五个键齐备，且 `callCap` 为 30 | 缺任一键，或 `callCap` 不等于 30 | packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:573-579 | grep: callCap: 30 | 2 |
| C-02 | grep | 门禁默认值是 `advisory`，enforce 只能靠环境变量开启 | 默认值不是 advisory，或默认里出现 enforce | packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:560-570 | grep: CLAIM_GATE_DEFAULT = "advisory" | 2 |
| C-03 | grep | Python 侧存在与 TS 同名的 claims 解析入口 | 文件内没有 `def parse_claims_block` | packages/multi-workers/autopilot/dispatch.py:650-660 | grep: def parse_claims_block | 2 |
| C-04 | grep | conductor 的 caps 用**当次卡**的 claims 定价（在 `dispatch_card` 之后取） | caps 仍在 `dispatch_card` 之前算，或用的是别的卡的 claims | packages/multi-workers/autopilot/dispatch.py:2087-2090 | grep: card_claims = card_backed.get | 2 |
| C-05 | grep | `MW_CLAIM_GATE` 在 Python 侧只有一处运行时读取 | 出现两处及以上 `os.environ.get("MW_CLAIM_GATE"` | packages/multi-workers/autopilot/dispatch.py:735-748 | grep: os.environ.get("MW_CLAIM_GATE" | 2 |

<!-- /mw-claims -->
