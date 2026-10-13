# T-02 — RQ-2｜`stalled` 状态机的全部出口与可逆性

type: research
phase: spec
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/spec-rq2-stalled-state-machine-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守 ⇒ key 不能因一次误判而永久报废）。
- 已核实事实：
  - `packages/multi-workers/autopilot/conductor.py:264-268` —— `_apply_stalled_approvals`（→续跑）/ `_apply_stalled_rejections`（→`closed-legacy`）。
  - 同文件 `:3319-3345` —— reject ⇒ `closed-legacy` 的实装；`:3326` 注释暗示存在 `closed-legacy ⟷ stalled` 的**回环**（语义待你核实）。
  - `:63` `_DEP_SATISFIED`、`:70` `_DISPATCH_SKIP_STATUSES`、`:77` `_STAGE_TERMINAL_STATUSES` —— 终态/跳过语义的既有定义。
  - `:1139-1160`、`:1244-1280` —— `mark_stalled` 的两处触发（advance 连续失败、L2 回路轮次耗尽）与提示文案。
  - `packages/multi-workers/autopilot/gates.py:44/:76` —— kind 集合（含 `stalled`）；全仓 `blocker_class` 与 `re-attest`/`reattest` 零命中。
- 允许自行扩大取证（全仓只读 + `H:\git\E2Feature` 的真实 gate 文件）；给上下文来源清单。

## 要求

1. 列出 `stalled` 的**全部入口与出口**（谁把它置成 stalled、approve 后状态如何变、reject 后如何变、有无第三条路径），每条给 `path:line` 与状态机前后值。
2. **核实 `:3326` 的回环语义**：`closed-legacy` 是否能回到 `stalled`（或反之）？在真实数据（`H:\git\E2Feature\.agenticdoc\_autopilot\gates\`、`_roadmap.md`、`auto-decisions.jsonl`）里找实例或反例。
3. 回答：**reject 是否真的不可逆**？"选错就废掉一个 key" 的风险描述是否成立？若不成立，给出准确描述（含恢复路径与代价）。
4. 给出 **re-attest（证据变更 ⇒ 重评）最自然的落点**：是重开原 gate、新建 gate，还是给 `stalled` 加一个与 approve/reject 并列的第三出口？各方案对 `gates.py` schema、台账、AC 锁协议的影响。
5. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

结论先行（含"回环是否存在"的明确 yes/no + 证据）＋逐条 `path:line` 判据＋真实数据实例＋上下文来源清单＋未覆盖面声明。
