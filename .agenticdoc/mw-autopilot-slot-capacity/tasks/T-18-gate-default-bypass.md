# T-18: 时效默认字段的旁路创建点修补（T-08 遗留）

- 波次: **3** · 依赖: T-08（已交付 `_gate_default_fields`）
- 写面（独占）: `packages/multi-workers/autopilot/conductor.py`（goal-change 建门点 `:2365` 邻域）、`packages/multi-workers/test_autopilot_pending_review.py`（追加用例）
- AC: AC-019 · VC: VC-024
- **来源**：PM 复算发现（用**生产 API**建门后跑 doctor，仍 `healthy=False`）

## 问题（实证）

T-08 把时效默认值盖在咽喉点 `_create_gate`（`conductor.py:2439`，内部 `gates.create()` + `_gate_default_fields()` + `_rewrite_gate_fields()`）。但生产路径**不止一个创建点**：

```
conductor.py:2365   goal_gate = gates.create(...)     # 直接调用，绕过 _create_gate
conductor.py:2470   path = gates.create(...)          # 在 _create_gate 内部（已盖章）
```

`:2365`（goal-change 门）绕过了咽喉点 ⇒ 该类门**永远缺** `expires_at`/`default_action` ⇒ `_gate_missing_fields` 非空 ⇒ doctor `healthy=False` + 打印 `gates:` 行 + 退出码 1。
**goal-change 门恰恰就是"等人答复"的那类门**，所以这是最该有 TTL 的一类，却唯独漏了。

## 交付物

1. `:2365` 建门点补盖同样的默认值：在建门后、**`snapshot_gate_created` 之前**调用既有 `_gate_default_fields(goal_gate)` 并写回（复用 `_create_gate` 里同一套机制；**不得**复制一份默认值逻辑，若现结构不便复用则抽成一个薄 helper 供两处共用）。
2. 新增用例（追加到 `test_autopilot_pending_review.py`）：**驱动真实 goal-change 路径**（不是手搭 gate 文件）产生门，断言：
   - `mw_common._gate_missing_fields(gate) == []`；
   - `doctor_report()["summary"]["healthy"] is True`（该项目除该门外无其它问题）；
   - `expires_at` 与 `created_at` 相差 48h。
3. **咽喉点唯一性的 grep 证据**（写进回执）：枚举全仓 `gates.create(` 的所有**生产**调用点，逐个说明"是否已盖默认值 / 为什么不需要"；仅测试文件可直接调用。这条是 P-023 硬规则 4 的要求。

## 契约（不得重定义）

- 默认值口径**不变**：`default_action: escalate-to-human`、`expires_at = created_at + 48h`（design `:208`）；`created_at` 不可解析时宁缺勿造（保持 `unknown (no field)` 的 fail-closed 语义）。
- 盖章必须在 `created` 证据快照**之前**（否则击穿 T-06 的 `gate_file.sha256` 重放绑定）。
- 不动 goal-change 的锁与 create-once 结构；不动 doctor 判据；不把 `_GATE_PENDING_DECISION_FIELDS` 改空。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py test_autopilot_gate_guards.py test_autopilot_closure.py -q`

## 非空洞对照（必须附）

- 去掉 `:2365` 的盖章 ⇒ 新用例必须红（并贴出修复前 `missing_fields=[...]` / `healthy=False`、修复后 `[]` / `True` 的**同一被测**前后对照）。
- 把盖章挪到 `snapshot_gate_created` 之后 ⇒ T-06 重放绑定判据必须红（`replay-misbound`）。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t18-gate-default-bypass/report.md`（含 `[VERIFY]` 原文与输出、生产创建点枚举表、前后对照、两条反向对照的红/绿、残留风险）。
