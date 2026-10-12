# T-01: G1 中止指纹 `l3-aborted` + 专用有界重掷

- 波次: **0** · 依赖: —
- 写面（独占）:
  - `packages/multi-workers/autopilot/conductor.py`（L3 回路段 `:1556-1940`）
- AC: AC-001, AC-002, AC-003, AC-004 · VC: VC-001, VC-002, VC-003, VC-004, VC-005, VC-006
- 基线: `10446aefb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

给"provider 流提前关闭"这一中止一个**机器指纹**，与"reviewer 写错文件"、"真 FAIL"互不重合，并在轮预算内有界自动重掷（D-001/D-002/D-003/D-004）。

## 交付物

- 指纹谓词：`worker.log` **尾 64 KiB** 含子串 `stream closed before response.completed` **且**该轮无两节齐备的合格源 ⇒ 判 `l3-aborted`。
- 谓词落点：`_l3_round_verdict` 的**状态门之前**（`conductor.py:1585-1586` 之前）——挂在其后会被 failed 短路，6/6 真例全漏。
- 持久化（D-002）：timeline `l3-aborted` 事件 + `data` 固定键集（八元组），**不动** `l3-verdict-provenance.json`。
- 专用计数（D-003）：loop 标签 `l3abort:{key}`；轮次 stem 与共享链同号 `l3-a{used + abort_used}`；上限读 `cfg["l3_abort_retry_limit"]`（默认 1）；**不占** `l3_limit` 共享预算（`:1858` 不变）。
- 分支位置：重掷分支插在 `:1886`（`if verdict == "no-verdict":`）**之前**；预算耗尽 ⇒ `mark_stalled(reason_code="l3-aborted", loop=l3abort)`。
- 复算接线：`STALL_REASON_CODES` 增 `l3-aborted`（12→14 的本卡半边），`_recompute_l3_stall_code`（`:5348`）与 `_stall_family`（`l3abort:` → `l3`）同步，否则判 `stalled-reason-drift`。

## 契约（不得重定义）

- **不改** L3 严格性：`_L3_SOURCE_ORDER`、FAIL 判据、`_l3_provenance_record` 语义零改动；本卡只做"新增分类 + 回退既有路径"。
- **不得**要求队列行 `status=done`（实测 6/6 真例为 `failed`，由 launcher 按真实退出码回写）。
- 尾窗字节常量复用既有先例（`mw_common.parse_end_exit:2029` 的 64 KiB 口径），不得新造第二种尾读语义。
- `T-02` 的配置键由本卡**读取**、不定义；`T-03` 的事件名由本卡**发射**、不定义。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_l3_aborted.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py -q`

## 非空洞对照（必须附在回执里）

- **X1**：摘掉指纹判定（回归旧行为）⇒ `VC-001` 必须转红。
- **X2**：把 marker 放在尾 64 KiB **之外** ⇒ 必须**不**判 aborted（fail-closed 方向明确），`VC-001` 边界例转红即为判据生效。
- **X3**：同一输入造 A/B/C 三类 ⇒ `VC-003` 两两不同（任一谓词被合并即红）。

## 风险与注意

- `conductor.py` 三段串行链（T-01 → T-07 → T-10）：开工前 `git diff --stat 10446aefb.. -- conductor.py` 确认另两段未被动。
- 若发现指纹必须同时在**非 failed** 路径生效，先回报 PM，不要顺手扩大谓词。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-01-l3-aborted/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。写完立即复制到 `evidence/runs/`（防 launcher 重跑覆写，见 plan R7）。
