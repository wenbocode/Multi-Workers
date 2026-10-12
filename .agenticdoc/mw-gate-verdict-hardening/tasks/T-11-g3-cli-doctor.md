# T-11: G3 CLI + doctor 面（fail-closed issue 与零扰动段）

- 波次: **2** · 依赖: T-04, T-10
- 写面（独占）:
  - `packages/multi-workers/mw.py`（autopilot 段）
  - `packages/multi-workers/mw_common.py`（`_doctor_issues` `:2780` 附近；插点 `:2887` 前）
- AC: AC-011, AC-013 · VC: VC-016
- 基线: `10446aefb`
- **⚠️ 前置门禁（plan R3 / pm-state D-009）**：`mw.py` 与 `mw_common.py` 当前有**另一 key 的未提交改动**。开工前必须确认对方已提交或书面释放；**不得**单方面覆写对方工作。未确认前不得开工。

## 目标

把 G3 的机械检查暴露成人可调用 + doctor 可发现的形态，同时保证**零扰动**（没有 freeze 的工程输出逐字节不变）。

## 交付物

- `mw autopilot contract-guard` 子命令（**注意**：`mw autopilot advance` 不存在，只有 `{gates, verify}`；`advance.py` 是纯 spawn 包装，不是 CLI 面）：
  - `--project <dir>`、`--key <key>`（可选）、`--json`；
  - 产出：freeze 状态、变更 AC/VC id、批准记录命中与否、判定结论（fail-closed）。
- doctor：`_doctor_issues` 新增一条 fail-closed issue（插在 `mw_common.py:2887` 前，与既有 I9「report but keep fail-closed」同口径）。
- doctor JSON/文本：新增 `gates["contract_guard"]` 段，**仅在存在 freeze sidecar 的 key 上产出**（否则键不出现）。
- 同步既有告警状态与文本格式化：`_gates_text_alerted` / `format_doctor_text` 两个消费点。

## 契约（不得重定义）

- 只读：doctor 路径**不得创建**任何文件或目录。
- 零扰动：无 freeze 的工程，`mw doctor --json` 与文本输出**逐字节**同改造前（P-018）。
- 与 `T-04` 共用 `contract_guard` 判定函数，**不得**在本卡复制一份判定逻辑。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_mw_autopilot_cli.py test_doctor_gates.py test_autopilot_contract_guard.py -q`
- `cd packages/multi-workers && python -X utf8 mw.py doctor --project H:\git\Multi-Workers --json > .tmp/doctor-after.json`（并与改造前输出做逐字节对比）

## 非空洞对照（必须附在回执里）

- 用一个**无 freeze** 的工程跑 doctor ⇒ 输出必须与改造前逐字节相同（零扰动对照）。
- 造一个"有 freeze + AC 文本被改 + 无批准记录"的 key ⇒ doctor 必须报 issue 且 `--json` 里出现 `contract_guard` 段（摘掉该段 ⇒ 用例转红）。

## 风险与注意

- **本卡是本 key 唯一与外部 key 共享写面的卡**：开工前跑 `git status --porcelain -- packages/multi-workers/mw.py packages/multi-workers/mw_common.py`，把结果贴进回执作为"开工时对方改动快照"。
- 若对方正在改同一区域，**停下来回报 PM**，不要并行施工。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-11-g3-cli-doctor/report.md`（含 `[VERIFY]` 命令原文与输出、开工时 `git status` 快照、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
