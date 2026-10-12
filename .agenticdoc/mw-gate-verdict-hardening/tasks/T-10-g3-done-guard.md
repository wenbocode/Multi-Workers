# T-10: G3 done 前机械检查 + 字段物化 + 提示词硬约束

- 波次: **2** · 依赖: T-04, T-07
- 写面（独占）:
  - `packages/multi-workers/autopilot/conductor.py`（`_done_transaction` `:2089`、`_stamp_gate_defaults` `:2499-2530` / `_gate_default_fields` `:2553-2573`、三条 prompt `:1453` / `:2291` / `:2312`）
- AC: AC-010, AC-011, AC-012 · VC: VC-013, VC-014, VC-015
- 基线: `10446aefb`

## 目标

让"AC/VC 生效文本有没有被授权改写"成为 `advance *->done` 的**机械前置**，并让 worker 提示词**逐字**带上硬约束（不许自己发明）。

## 交付物

1. **done 前检查**（fail-closed）：`_done_transaction` 写终态**之前**调用 `contract_guard`（T-04）：
   - 有 freeze 且当前 AC/VC canonical sha 不一致 ⇒ 查"批准记录"（`status=="approved"` ∧ `authorizes ∋ "contract-change"` ∧ `gate.key == key`，不绑 kind）；
   - 无批准记录 ⇒ **拒绝推进** + 发 `contract-refused` 事件（`data` 带 `changed_ids` / `freeze_rel` / `carrier`）+ `reason_code="contract-unauthorized"`（12→14 的第二半边）。
2. **无 freeze 的工程**：走"无身份锚"分支（不拒、不报），保证历史 key 零扰动。
3. **字段物化**：`_stamp_gate_defaults` / `_gate_default_fields` 给新建门盖 `authorizes: []`（人应答时由 `T-12` 填值）。**不得**改 `gates.create()`。
4. **提示词硬约束**：同一条常量逐字追加到 `_repair_prompt`（`:1453`）、`_phase_writer_prompt`（`:2291`）、`_fix_writer_prompt`（`:2312`）三处。
5. `STALL_REASON_CODES` / `REASON_CODES` / `_recompute_l3_stall_code` 同步到 "`contract-unauthorized`"。

## 契约（不得重定义）

- **零扰动**：无 freeze sidecar 的工程，行为与改造前逐字节相同（AC-013）。
- 判定函数**不得**读 `gate.note` / `answered_by`，**不得**解析 design.md 里的"授权链"散文（AC-012 的构造性成立条件）。
- prompt 常量是 `T-04` 模块之外的**独立字符串**，三处必须逐字相同（VC-013 锁 `verbatim=true`）。
- 不得改 L3 判定与 `tick` 段（T-01/T-07 的写面）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_contract_guard.py test_autopilot_conductor.py test_autopilot_auto_decision.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_closure.py -q`

## 非空洞对照（必须附在回执里）

- 摘掉 done 前检查 ⇒ "AC 文本被改 + 无批准记录"用例必须**能推进**（VC-014 转红）。
- 把批准记录判据放宽（接受 `pending` 或散文 note）⇒ VC-015 必须转红。
- 三条 prompt 里删掉一处常量 ⇒ VC-013 必须转红。

## 风险与注意

- `conductor.py` 串行链第三段：开工前确认 T-01/T-07 已落、`git diff` 无混淆。
- 真实反例夹具（只读引用，不入仓）：`H:\git\E2Feature\.agenticdoc\_autopilot\gates\gate-0014.md`（散文 note 被当授权）+ 其 `design.md` 的 AC/VC 改写段。
- 若发现"批准记录"还可能是别的既有载体（例如 `xkey-authorize`），先回报 PM，不要自创第二种语义。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-10-g3-done-guard/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
