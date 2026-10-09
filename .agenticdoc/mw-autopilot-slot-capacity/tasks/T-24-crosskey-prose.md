# T-24: 绕门散文授权的机器判定（QC 欠债 Q-VC-048 / Q-AC-031）

- 波次: **6**（收口波）· 依赖: T-13（doctor gate 段与 `mw autopilot gates`）、T-07（`xkey-authorize` 门与 `_xkey_ensure_gate`）
- 写面（独占）: `packages/multi-workers/autopilot/conductor.py`（只加只读扫描与 issue 发射）；**新建** `packages/multi-workers/test_autopilot_crosskey_prose.py`。**若**必须有 CLI 面改动，才允许动 `packages/multi-workers/mw.py`，且须在回执里单列理由
- AC: AC-031 · VC: VC-048
- **来源**：独立 quality-gate worker 的 Q-VC-048 / Q-AC-031（`evidence/quality-gate-report-20260926-194528.md`），判定 ⚠️ 不足：研究级判据与实测样本在，但**无实现、无测试、无卡绑定**

## 问题（实证）

VC-048 要求："当跨 key 授权经**散文通道**发生时，机器判定为**未授权**（导门即未授权）"。现状：

- **机器授权路径存在**：`xkey-authorize` 门（`conductor._xkey_ensure_gate`，`conductor.py:2739-2744`，`refs=[request_id, ticket_rel]`）。当它被正常回答时，授权有机器载体。
- **散文通道是现实中的主路径**：FM 项目的唯一真实案例里，跨 key 授权**没有机器载体**，只写在 `_autopilot/evidence/cross-key-repair-request-*.md` 的**手写 `decision:` 行**里。
  - 真实样本（PM 亲读）：`E:\CLI_workspace\FeatureMigrator\.agenticdoc\_autopilot\evidence\cross-key-repair-request-20260925-n1.md`
    - `:4` `request_id     : XKEY-2026-09-25-01`
    - `:7` `status         : authorized-R1（2026-09-26T03:04:05+00:00 经人批准）`
    - `:52` 该文件自己规定："在本文件末尾追加一行，`decision: <approved|rejected> by <who> at <ts>，（注记）`"
    - `:57` `**decision: approved (R1) by user-via-pm-window at 2026-09-26T03:04:05+00:00**`
  - 设计判据：`evidence/research/design-gate-propositions-20260926.md:373`（**事实 P4（绕门）** = "该 request 没有走机器授权路径"，`[实测]` 即上文件 `:57`）；`:364` 记录"唯一真实案例的跨 key 授权**没有机器载体**…手写 `decision:` 行"。
- 现状代码里**没有任何机器判定**：`packages/multi-workers` 全仓 `cross-key-repair-request` 零命中（QG 实测）。

## 交付物

1. **doctor 只读扫描**（挂到既有 gate 体检段，不新建命令）：扫描项目 `_autopilot/evidence/cross-key-repair-request-*.md`，判定每个 request 的授权**是否有机器载体**：
   - **有机器载体** ⇒ 不报：该 request 能关联到一条**已答的 `xkey-authorize` 门**（`_xkey_ensure_gate` 写下的 `refs` 含 `request_id`；门的应答本身即机器授权）。
   - **只有散文载体** ⇒ **报 I 类 issue + fail-closed「视为未授权」**：识别手写 `decision:` 行（形状如 `decision: <approved|rejected> by <who> at <ts>`，允许 `**…**` 包裹）；作者不是机器（例如 `by user-via-pm-window`）且无对应已答门 ⇒ issue。
2. **fail-closed 语义必须真的"不放开"**：判定为未授权时，**不得**因此解锁任何依赖/阶段、不得因此放行任何动作；issue 只做"可见化 + 视为未授权"。若既有代码里有任何"读到该文件即当作已授权"的读取点，**必须一并堵住**（先 grep 证明是否存在；存在则堵并留痕，不存在则在回执里明写"全仓无此读取点 + grep 证据"）。
3. **测试**（新建 `test_autopilot_crosskey_prose.py`）：
   - **正例（必须红/必须报）**：以 **FM 真实文件形状**（`request_id` + `status: authorized-…` + 手写 `decision:` 行）为夹具，断言 doctor 报出该 request 且判为未授权、`mw autopilot gates` 段可见。
   - **反例（必须不报）**：同一 request **关联到一条已答的 `xkey-authorize` 门** ⇒ 断言无该 issue。
   - **反例 2**：`_autopilot/evidence/` 下无 request 文件 ⇒ 无该 issue（防止把所有项目都判成绕门）。
   - 夹具**不得**自创字段或闭集外的值；issue code 必须落在既有常量里（见契约）。
4. **`[VERIFY]` 行（数值必须实测，禁字面量 —— P-023）**，至少含：`requests=<n> machine_authorized=<n> prose_only=<n> issues=<n> fail_closed=true`。
5. 回执给**非空洞对照 ≥2 条**：临时把散文判定摘掉 ⇒ 正例必须转绿（证明是这条判据在抓）；临时给 request 关联一条已答门 ⇒ 必须不报。逐条贴原始输出。

## 契约（不得重定义）

- **只读**：不得写 `_autopilot/**`、不得新建门、不得自动回答任何门、不得改 `xkey` 的授权语义。
- **不得新造 issue code / 闭集外的值**：先 grep 既有 `_GATES_ISSUE*` / doctor issue 常量集，用既有值；确需新增则**先在回执里报告并说明**，不许静默加。
- 跨语言：本卡只动 Python 侧判据。**若**新增了会出现在 `mw autopilot gates --json` 输出里的字段/枚举，必须检查 TS 镜像面是否需要同步（P-021）；不需要则在回执里明写"TS 侧不消费该字段"的证据（grep）。
- 不得放宽任何既有断言；不得用 `>=`/skip/空实现充数。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_crosskey_prose.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_doctor_gates.py test_autopilot_pending_review.py test_autopilot_auto_decision.py -q`（回归面）
- 贴出 `[VERIFY]` 行与两次运行的原始输出

## 回执

写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t24-crosskey-prose/report.md`（含：改动点 file:line、扫描判据、正/反例原始输出、非空洞对照、issue code 来源 grep 证据、是否存在"读到即授权"读取点的 grep 结论、残留风险）。
