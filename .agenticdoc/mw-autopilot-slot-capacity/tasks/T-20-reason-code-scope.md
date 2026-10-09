# T-20: `reason_code` 必需集按 kind 收敛 + 冻结闭集写入护栏（T-13/T-18 契约冲突）

- 波次: **3** · 依赖: T-07（45 个闭集）、T-13（doctor 判据）、T-18（盖章助手）
- 写面（独占）: `packages/multi-workers/mw_common.py`（`_GATE_PENDING_DECISION_FIELDS` / `_gate_missing_fields` 邻域）、`packages/multi-workers/autopilot/conductor.py`（`_stamp_gate_defaults` 邻域 + goal-change 盖章行）、`packages/multi-workers/test_doctor_gates.py`、`packages/multi-workers/test_autopilot_pending_review.py`
- AC: AC-019, AC-026 · VC: VC-024
- **来源**：PM 复算（生产盖章路径逐 kind 实测）

## 问题（实证，两条）

**① doctor 对 6 类门里的 4 类无条件误报。** 用生产盖章路径（`gates.create()` + `_gate_default_fields()` + 写回）逐 kind 实测：

```
stage-confirm      missing=['reason_code']     reason_code=None
stage-close        missing=['reason_code']     reason_code=None
goal-change        missing=['reason_code']     reason_code=None
budget-exhausted   missing=['reason_code']     reason_code=None
stalled            missing=[]                  reason_code='l2-budget-rejected'
```

⇒ 除 `stalled` 外的每类待答门都会让 `doctor_report()["summary"]["healthy"] is False`（打印 `gates:` 行、退出码 1）。这直接违反本 key 的零扰动词条（AC-019 / I7）。

**根因不是"没人写"，而是规则过宽**：`reason_code` 在设计里是**判定类字段**（design `:254`「判定类：`reason_code` / `machine_evidence` / `cause_class` / …」= **由机器判定写入**）。`stage-confirm`/`stage-close`/`goal-change`/`xkey-authorize` 是**纯待人裁决**的门，机器**不做判定** ⇒ 本就没有 reason_code 可写；`budget-exhausted` 的规则（"used == limit + credits 且仍有阻塞缺口"）也不需要它。**只有 `stalled`** 由 `mark_stalled` 的 12 个调用点必盖 reason_code（T-07）。

**② 该过宽规则已经诱发契约外的自创值。** T-18 为了满足 `_gate_missing_fields == []`，给 goal-change 门盖了 `reason_code="goal-md-mtime-moved"`——**不在 T-07 冻结的 45 个 `REASON_CODES` 里**（实测 `in REASON_CODES = False`；goal 相关只有 `goal-sha-unchanged`/`stage-confirm-goal-drift`/`goal-ok`/`goal-non-normative`）。闭集被无声撑开，且写入侧无任何校验。

## 交付物

1. **必需集按 kind 收敛**（`mw_common.py`）：
   - 通用必需（所有 schema-2 pending 门）：`expires_at`、`default_action`（两个创建点均已盖，实测已成立）。
   - **仅 `stalled`** 额外必需 `reason_code`。实现为显式冻结常量，例如：
     `_GATE_UNIVERSAL_DECISION_FIELDS = ("expires_at", "default_action")`
     `_GATE_REASON_CODE_REQUIRED_KINDS = ("stalled",)`
     并加注释写明依据（design `:254` 判定类 + `mark_stalled` 12 调用点）。
   - `_gate_missing_fields(gate)` 相应改造：**保持**"仅 schema-2 pending 才报"与"缺字段 = 问题"的既有语义（不得降级为 note、不得整条清空）。
2. **撤销 T-18 的自创值**：删掉 goal-change 盖 `reason_code="goal-md-mtime-moved"` 的那一行（该 kind 不再要求 reason_code ⇒ 无需凑值）。
3. **写入侧闭集护栏**（新机制，薄）：在**唯一盖章助手** `_stamp_gate_defaults` 内校验 `machine_fields["reason_code"]` ∈ `REASON_CODES`；不合法则**丢弃该字段**并把被丢弃的名字返回给调用方，由调用方记一条 `config` 时间线事件（不得抛异常让建门失败，也不得放行非法值）。这条把"冻结闭集"从文档约定升级为可执行约束。
4. 判据（`test_doctor_gates.py` / `test_autopilot_pending_review.py` 追加）：
   - 逐 kind 表：`stage-confirm`/`stage-close`/`goal-change`/`xkey-authorize`/`budget-exhausted` 在**生产盖章后** `_gate_missing_fields == []`；`stalled`（无 reason_code）仍报 `['reason_code']`；`stalled`（有合法 reason_code）报 `[]`。
   - 护栏判据：塞一个非法 `reason_code` ⇒ 字段被丢弃 + 有 `config` 事件 + 门仍被创建（不是失败）。
   - 保留既有锁：v1 门不报（34 个历史门不泛滥）。

## 契约（不得重定义）

- **不得**为了让判据变绿而把 `_GATE_PENDING_DECISION_FIELDS` 改成空集、或把 doctor 的 I2/I6 降级为 note（那会毁掉"有人绕过创建器"的探测力）。
- `expires_at`/`default_action` 的默认值口径与盖章时机**不变**（`_gate_default_fields`，必须在 `created` 快照之前）。
- **不得**把 `goal-md-mtime-moved` 之类的新值加进 `REASON_CODES` 来"就地扶正"（闭集是 T-07 依 design 冻结的；如需扩集必须走设计变更 + 同波两侧 + 计数锁刷新，属另一张卡）。
- 不动 T-07 的规则表、不动 T-08 的 `pending-review` 不变量。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py test_autopilot_auto_decision.py test_autopilot_conductor.py -q`

## 非空洞对照（必须附）

- 把 `_GATE_REASON_CODE_REQUIRED_KINDS` 改成"所有 kind" ⇒ 逐 kind 表必须红（复现 4 类误报）。
- 去掉写入侧护栏 ⇒ 非法 reason_code 判据必须红（并贴出"非法值真的进了门文件"的原始证据）。
- 逐 kind 前后对照：同一被测在修复前 `missing=['reason_code']`/`healthy=False` → 修复后 `[]`/`healthy=True`（每类一行，别只给一类）。

## 风险与注意

- 与 T-19 同文件（`conductor.py`）⇒ **T-19 未终态前不得开工**。
- `_gate_missing_fields` 是 T-13 与 doctor 的共同判据，改动会牵动 `test_doctor_gates.py` 里既有的 I2/I6 用例——逐个核对是"期望值收敛"而非"放宽断言"，并在回执里逐条列出改了哪些期望值。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t20-reason-code-scope/report.md`（含逐 kind 前后对照表、`[VERIFY]` 原文与输出、三条反向对照的红/绿、改动到的既有期望值清单、残留风险）。
