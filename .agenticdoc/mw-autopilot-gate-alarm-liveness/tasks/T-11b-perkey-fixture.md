# T-11b — 项目级夹具改 per-key 语义（`mwds-t12-regression.test.ts`）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-002
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/spec.md` §0.1 ①、AC-002；`design.md` §2 D2；本卡由 T-11 的卡外遗留触发

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（阻塞必须可感知；提醒不得被无关在飞工作整体压掉）。
- **本卡要修的具体遗留**（T-11 报告指出，PM 采纳）：`packages/coding-agent/test/suite/mwds-t12-regression.test.ts` 有一个用例的夹具编码的是**项目级**语义 —— worker 行挂在 `t-1`，而 gate 挂在其 `k1` 上；per-key 语义下该 gate **不应**被抑制，故该用例的期望需按新语义更新。该文件不在 T-11 的写入允许面内，故未改。
- 新语义的代码落点（可自行复核）：`packages/multi-workers/autopilot/conductor.py` 的逐 gate 按自身 key 判在飞（原全项目级 `if any(_is_in_flight(row) for row in rows): return []` 已被删除）；观测槽 `remind-suppressed`；`packages/multi-workers/mw_common.py:2012 worker_owner_key` 与 `:3323` 的 per-key 轴。
- 相关需求原文（AC-002）："仅在'该 gate 所属 key 存在在飞工作'时抑制；**key/stage 不可解析的 gate 一律不抑制**；被抑制也必须留一条可见记录"。

## 要求

1. **更新该用例的期望**为新语义：`t-1` 在飞、gate 挂 `k1` ⇒ **该 gate 的提醒必须照常发射**（不得被抑制）；断言改为验证"他 key 在飞不抑制"。
2. **必须同时保留另一分支的测试**：**同 key** 在飞 ⇒ 该 gate 被抑制**且留下 `remind-suppressed` 可见记录**（不得只测放行侧而丢掉抑制侧的覆盖）。
3. **不得放宽既有判据**（P-03）：这是"旧断言编码了被用户明确改变的行为"，只允许改期望/夹具数据，不得把断言改弱（例如不得改成 `expect(...).toBeDefined()` 之类）。
4. 报告中列出**旧期望 vs 新期望**的逐字对照，并说明为什么新期望与新语义一致。
5. 若该文件内还有其他依赖项目级语义的用例，一并按同口径更新并在报告中列出；若发现与 AC-002 冲突且无法用新语义解释的用例，**停下来在报告中说明**，不要强行改绿。

## 写入允许面

- `packages/coding-agent/test/suite/mwds-t12-regression.test.ts`
- 如需补充，可新增 `packages/coding-agent/test/suite/mwgal-t11b-perkey-fixture.test.ts`

## 写入禁止面

- 任何 `src/**` 实现文件（本卡只改测试期望/夹具；实现已由 T-11 落地）
- `packages/multi-workers/**`（T-12 即将开跑）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t12-regression.test.ts test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts`

## 改动历史

（填写：旧夹具的语义、新期望、以及"为什么这不是放宽判据而是修正编码了旧行为的期望"。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
