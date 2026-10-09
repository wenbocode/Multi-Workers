# T-21: 延后处置必须留台账行（影子与实动共用），修正影子期的失真

- 波次: **3** · 依赖: T-07（台账）、T-19（case 2 生产者）
- 写面（独占）: `packages/multi-workers/autopilot/conductor.py`（`_defer_declined_gate` + `_auto_decide_one` 的收尾段）、`packages/multi-workers/test_autopilot_pending_review.py`（追加用例）、**若 `decision` 取值在 TS 侧有镜像/呈现**：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/*.ts` 同波镜像
- AC: AC-027, AC-028 · VC: VC-039..VC-043
- **来源**：T-19 自报残留（"deliberate suppression of the T-07 escalate audit row"）+ PM 读码后认定的更重后果

## 问题（实证）

T-19 在放弃路径上接线后，命中延后时**直接 `return`**，于是：

```
conductor.py:6120  def _defer_declined_gate(...)
        if mode != "live" or not _auto_mode_active(project_root):
            return False                                   # ← 影子被排除
conductor.py:6199-6211  (# decision == "escalate" 分支)
        if _defer_declined_gate(project_root, st, gate, mode):
            return                                         # ← 在写任何台账行之前返回
```

⇒ 同一个"机器不能应答"的放弃，两种模式表现**不一致**：

| 模式 | 状态变化 | 台账行 |
|---|---|---|
| `shadow` | 无（零改动，符合 T-07 契约） | `decision="escalate", executed=false`（**旧语义**） |
| `live` | key → `pending-review`（**真状态变化**） | **无任何行** |

**两条后果**：
1. **审计断链**：design `:93` 明确台账存在的原因之一是 timeline **会被剪**（JC `gate-0008` 的教训）；而延后改变了 key-status（影响收口前置与槽位口径）——这类状态变化恰恰必须有**不可剪**的机读记录，现在只剩一条可被剪的 timeline 事件。
2. **影子失真（更重）**：design `:245` 把该事件定义为「**每次自动决策（影子与实动共用）**」，其意图是影子期呈现"live 会做什么"。现在影子记 `escalate`、live 实际 `defer` ⇒ 用户在影子期看到的**主要新行为是错的**，而用户明确决定"先影子试跑再放 live"+ 影子门槛（≥5 夜 ∧ ≥20 条影子决策）⇒ **用失真样本去满足门槛**，门槛失去意义。

## 交付物

1. `_defer_declined_gate` 改为返回**处置结果**（而不是仅 bool），让调用方能在两条路径上都写台账行：
   - **shadow**：仍然**零状态改动**（gate 文件、roadmap 逐字节不变），但**写一行** `mode="shadow", executed=false, decision="defer"`。
   - **live**：先做状态改动（`defer_key_to_review`），成功后再写 `mode="live", executed=true, decision="defer"`；状态改动失败 ⇒ `executed=false` + 一条 `config` 事件（沿用 T-19 的 fail-closed 行为，不得让 tick 死掉）。
2. **每个门每次 pass 恰一行**：延后行与既有 `escalate` 行**互斥**（不得两行都写，也不得两行都不写）。
3. `gate_file_sha256_before == after`（延后不动门文件）；`consumed_at` 仍不得写（延后不是应答）。
4. **`decision` 取值**：先查现有取值是否已含等价的 `defer`（Python 侧与 TS 侧 / 呈现层 / 任何校验器都查一遍）。若需要新增取值：**同波改两侧**（P-021），并把所有"取值计数锁"一并刷新（本 key 已有 T-15/T-17 的先例）；若两侧镜像需要新枚举，回执里逐个列出改动点。
5. **`reason_code` 必须 ∈ `REASON_CODES`**：优先复用本次放弃已算出的那个 `reason_code`（它本就在闭集内）。**禁止自创值**（T-18 已因此被驳回一次；T-20 正在为闭集加写入侧护栏——本卡不得与之冲突）。
6. 配额/熔断口径：确认延后行**进入**夜间/每 key/突发配额与影子门槛的计数，且**不重复计数**（原 escalate 行已不再写）。

## 判据（追加到 `test_autopilot_pending_review.py`）

- 影子延后：`auto_gate_mode: shadow` + 不可应答的 `stalled` 门 ⇒ 台账**多一行** `decision="defer", executed=false, mode="shadow"`；gate 文件与 roadmap **逐字节不变**（sha256 前后相等）。
- 实动延后：`live` ⇒ key 变 `pending-review`、台账一行 `executed=true`、**没有** `decision="escalate"` 的同门行。
- 门槛可见性：影子延后行**计入**"≥20 条影子决策"的窗口（贴出计数前后值）。
- 不可逆 kind（`stage-close`）⇒ 仍走 case 3，写既有 `escalate` 行，台账**不出现** `defer`。

## 契约（不得重定义）

- 不得让影子产生任何状态改动（这是 T-07 的硬契约，也是用户"影子分阶段"决策的前提）。
- 不得在延后时写 `consumed_at`/`answered_by`、不得发 `gate-auto-decision` 的"已应答"语义（`executed` 表示**状态改动是否发生**，不是"门被答复"）。
- 不得为了少改而把 `decision` 取值硬编码在 TS 与 Python 各一份却不加 parity 判据（P-021）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_conductor.py -q`
- 若改了 TS 镜像：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts`

## 非空洞对照（必须附）

- 把影子那行删掉 ⇒ 影子延后判据必须红（并贴出"影子记的是 escalate、live 干的是 defer"的原始两行台账对照）。
- 在 live 分支恢复"写行之前 `return`" ⇒ 实动延后判据必须红。
- 让影子延后顺带改一次 roadmap ⇒ 逐字节判据必须红。

## 风险与注意

- 与 T-20 同文件（`conductor.py`）⇒ **T-20 未终态前不得开工**。
- 若发现 `decision` 取值是**冻结闭集**且加成员会牵动 spec/AC 措辞，**停下来报 PM**（可能需要一张只改枚举的卡），不要顺手拓宽冻结面。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t21-defer-ledger/report.md`（含 `[VERIFY]` 原文与输出、影子/实动两行台账对照、`decision` 取值与 TS 镜像改动点清单、三条反向对照的红/绿、配额计数前后值、残留风险）。
