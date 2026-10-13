# T-12 — `stage-close` 自动收证并自动 approve（中档，含回落可见）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-015（D-011 中档、D-014 ①）
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D8、§1（两级主闸）；`spec.md` §0.1 ③、AC-015；
      `evidence/research/design-drq4-auto-approve-20261013.md`（56 gate 普查：stalled 31 / stage-close 14 / stage-confirm 10 / goal-change 1）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（autopilot = 自动驾驶，派发不得因"没人答门"而停）。
- 为什么是 `stage-close`：它是**主闸**（`_stage_closure` 不闭合 ⇒ 下一 stage 永不 `running` ⇒ `_stage_activation` 返回 False ⇒ **全项目零派发**），且是唯一同时满足"证据可确定性机器收集 + 非 policy"的 kind。
- 已核实锚点（自行复核）：
  - `packages/multi-workers/autopilot/conductor.py:853 _stage_closure`（前置：全 key 终态 + 无在飞 + `evidence_reconciliation_blocks:7156` 未阻断 ⇒ 写 dossier 并开 stage-close 门）。
  - `:979 _closure_dossier_md`（dossier 生成）、`:1853 _done_credentials_present`（key 终态凭据）。
  - `:6350 _AUTO_AUTHORITY_KEYS`（自动裁决权威字段白名单）、`:6193/:6219`（`answered_by`/`answered_at` 的读取形态）、`:3244 _apply_stalled_approvals`（既有自动批准成例）、`:3624 _apply_review_decisions`（独立消费者成例）。
  - `:3400 GATE_DEFAULT_TTL_SEC = 48 * 3600`；`:3542 _process_deferred_reviews`（**48h 兜底只是升级信号**，文档串明写 "It NEVER closes the stage and NEVER rewrites a key"）。
  - `autopilot/gates.py:44/:74-76`（kind 集合）、`:355`（stage 字段类型校验）。
- 现实基线（可复核）：全机 `auto-decisions.jsonl` 中 `phase:"decide"` = **0 行**（自动裁决从未在生产跑通），自动批准占比 **0/53 = 0%**，等待中位 2.56 h / 均值 20.28 h / 最大 300.6 h。

## 要求

1. **自动放行判据（全部满足才放行）**：该 stage 全部 key 终态（`_STAGE_TERMINAL_STATUSES`）+ 该 stage 无在飞 worker 行 + `evidence_reconciliation_blocks` 未阻断 + dossier（`stage-N-close.md`）已写 + 每个 key 的终态凭据齐备（`_done_credentials_present`）。**不许只看"门开着"就放行**。
2. **留痕零新字段**：写入 `answered_by="conductor-auto:<rule_id>"`（`rule_id` 用封闭枚举字符串），并填 `_AUTO_AUTHORITY_KEYS` 允许的既有字段（如 `answer_source`/`auto_policy_id`）；**timeline 事件名复用既有**，不得新造事件名。
3. **落 `phase:"decide"` 台账行**（当前该 phase 在生产为 0 行，本次改动后应 > 0 且可审计：含 gate id、stage、rule_id、依据摘要）。
4. **回落必须可见且不静默**：任一判据不满足或证据收集失败 ⇒ **不自动放行**，回落人工门，并在状态面/台账留下"为何未自动"的可见记录（含缺失项，例如"缺 `l3-verdict.txt`/`l3-report.md`"）。T-08 已验证：JCodingAss `gate-0007`（stage-close、key 为空、静置 25.6 天）应可自动放行；`gate-0008` 因缺 `l3-verdict`/`l3-report` **必须回落**。
5. **幂等**：重复 tick 不得重复批准、不得重复写台账（按文件真相判幂等）。
6. **不得与 48h 兜底重复**：不得改动 `_process_deferred_reviews` 的语义（它只升级不闭合）；**必须新增一条回归测试**断言"48h 兜底不会闭合 stage / 不重写 key-status"。
7. **`stage-confirm` 不自动**（D-014②）：不得对 `stage-confirm` 做任何自动批准；本卡只允许对 `stage-close` 生效。
8. **不新增 config 键**（AC-011）；不得放宽既有判据（P-03）；不得改动 `gates.py` 的冻结名序与 `create()` 的 13 键。

## 写入允许面

- `packages/multi-workers/autopilot/conductor.py`（仅 stage-close 自动放行 + 回落可见 + 台账/留痕相关区段；`autopilot/**` 其他文件不动）
- `packages/multi-workers/test_mwgal_t12_stage_close_auto.py`（新增）
- 既有 Python 测试中与 stage-close 直接相关的用例（仅允许更新**因新行为而必须更新**的期望/夹具，且须在报告中逐条说明；不得改弱断言）

## 写入禁止面

- `packages/multi-workers/mw.py`、`mw_common.py`（T-13/T-11 已落定的区段）
- `packages/coding-agent/**`（TS 侧属 T-10b/T-11b/T-14/T-17）
- `autopilot/gates.py` 的冻结名序与 `contract_guard.py`（零改动，属 T-14 才碰的注册面）
- 其他 key 目录、其他项目仓库只读（`H:\git\JCodingAss` 只作只读取证）

## 验收命令

从 `packages/multi-workers`：
`python -m pytest test_mwgal_t12_stage_close_auto.py test_autopilot_pending_review.py test_mwds_t08_doctor_blocked.py -q`

## 改动历史

（填写：自动放行判据的最终形态、`rule_id` 取值、回落可见性的落点，以及"为什么 48h 兜底与本卡不重复"。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
