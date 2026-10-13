# T-15 — gate re-attest 入口 + reject 二次确认（含措辞校正）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-008, AC-009
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D7；`spec.md` E6/AC-008/AC-009；
      `evidence/research/spec-rq2-stalled-state-machine-20261013.md`（入口 2 / 出口 3 / 回环只在 out-of-band / 真实 0 实例）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（门禁判据必须可重评，避免一个 key 因一次误判报废）。
- 已核实锚点（自行复核）：
  - `packages/multi-workers/autopilot/conductor.py:5294`（`mark_stalled` 只短路 `status == "stalled"`）、`:5271`（`mark_stalled` 入口，14 个触发点）。
  - `:3313/:3319`（`_apply_stalled_approvals` / `_apply_stalled_rejections`）、`:3340`（`closed-legacy` 的**全仓唯一写入点**，全历史仅 1 实例）、`:3326`（`closed-legacy` ⟷ `stalled` 回环注释）。
  - `:3624 _apply_review_decisions`（**不依赖 `status=="stalled"` 的独立消费者成例**）、`:3667 defer_key_to_review`、`:3701`（`pending-review` 出口，需 `auto_gate_mode≠off`）。
  - `:3008-3051 _create_gate`（`context_refs` 参与 `_gate_open` 去重维度 ⇒ **re-attest 可用 `context_refs` 承载来源，schema 零改动**）。
  - `autopilot/gates.py:44/:74-76`（kind 集合：含 `stalled`；**不得新增 kind**）。
- RQ-2 的三条结论（本卡的判据依据）：**入口 2 个**（`mark_stalled` + 声明但无生产调用者的 `apply_review_decision("escalate")`）；**出口 3 个**（approve→`running`；reject→`closed-legacy`；延后→`pending-review`）；**`closed-legacy → stalled` 回环代码级成立但无 conductor 内部路径**（14 个调用点被 `_DISPATCH_SKIP_STATUSES` 挡住，真实数据 **0 实例**）。
- 待校正的措辞：现文档/注释暗示"reject 会废掉一个 key"，实际是**状态机内不可逆**，但恢复 = 人工改 `_roadmap.md` 一行，代价是**无审计痕迹 + 轮次不退**。

## 要求

1. **re-attest 入口（AC-008）**：提供一条**新建 gate** 的路径，`context_refs` 内含 `reattest-of:<原 gate id>`；**schema 零改动**（复用既有 `context_refs`），**不得新增 kind**、不得复用/回收 gate 编号（AC 锁协议）。
2. **独立消费者**：新增/改造的消费逻辑**不得依赖 `status == "stalled"`**（照 `_apply_review_decisions:3624` 成例）；原 gate 的判定必须**留痕**（timeline 事件复用既有事件名，不新造）。
3. **可重评语义**：证据已刷新（例如原 gate 因缺 `l3-verdict.txt`/`l3-report.md` 回落）后，re-attest 出来的新判定**必须能被重新评估**（即不继承原判定结果；若满足 T-12 的 stage-close 五判据则应可自动放行，否则回落并点名缺失项）。
4. **reject 二次确认（AC-009）**：`rejected`（→`closed-legacy`）是 destructive ⟹ 必须显式二次确认（CLI/console 侧：未确认则拒绝执行并给出提示；确认则执行且留痕）。确认机制不得削弱既有审计（`answered_by`/`answered_at`/timeline 保留）。
5. **措辞校正**：把"选错就废掉一个 key"的暗示改为准确表述 —— **状态机内不可逆；恢复 = 人工改 `_roadmap.md` 一行；代价 = 无审计痕迹 + 轮次不退**。同时**记录**（注释或文档）`closed-legacy ⟷ stalled` 回环**只在 out-of-band 可达**（conductor 内部路径被 `_DISPATCH_SKIP_STATUSES` 挡住；真实 0 实例）。
6. **回归测试**：① re-attest 生成新 gate 且编号不复用、原判定留痕；② 证据刷新后新判定可重评（可自动放行 / 或回落点名缺失项）；③ 未二次确认的 reject 被拒；确认后执行且可审计；④ 断言 conductor 内部路径**不能**触发 `closed-legacy → stalled` 回环（out-of-band 才可达）。
7. 不新增 config 键（AC-011）；不放宽既有判据（P-03）；不改 `gates.py` 冻结名序与 `create()` 13 键；`contract_guard.py` 零改动。

## 写入允许面

- `packages/multi-workers/autopilot/conductor.py`（re-attest 消费路径 + reject 确认 + 措辞/注释；**不得动 T-12 已落的 stage-close 自动放行区段**）
- `packages/multi-workers/mw.py`（仅当 reject 确认需要 CLI 侧入口时，最小改动）
- `packages/multi-workers/test_mwgal_t15_reattest_confirm.py`（新增）
- 既有 Python 测试中因本卡行为而必须更新的期望（逐条在报告说明；不得改弱断言）

## 写入禁止面

- `packages/multi-workers/autopilot/gates.py` 的冻结名序与 `contract_guard.py`
- `packages/coding-agent/**`（TS 侧属 T-10b/T-11b/T-14/T-17）
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/multi-workers`：
`python -m pytest test_mwgal_t15_reattest_confirm.py test_mwgal_t12_stage_close_auto.py test_autopilot_pending_review.py -q`

## 改动历史

（填写：re-attest 的 gate 形态与 `context_refs` 取值、确认机制落点、措辞校正清单、回环不可达的证明方式。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
