# T-06: 证据快照 sidecar 与取证源解析（D-007 落地）

- 波次: **1** · 依赖: T-03
- 写面（独占）: 
  - `packages/multi-workers/autopilot/evidence.py`（新建模块）
  - `packages/multi-workers/test_autopilot_evidence.py`（新建）
- AC: AC-029 · VC: VC-044, VC-045
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

让"自动放行"有条件：值层 `meets` **且** 绑定层 `bound`；并让"应答窗口内证据被改写"可被机器检出（实测 E2 三 key 的 `l3-verdict.txt` 于 2026-09-24T16:47:33Z 被带外批量改写，同秒 timeline 全是 beat、`l3-verdict` 事件 0 条）。

## 交付物

- `snapshot(paths) -> [{path, sha256, mtime_ns, bytes}]`（单模块、纯函数式、无全局状态）。
- sidecar 读写：`<gates>/gate-NNNN.evidence.json`，schema 字符串固定 `gate-evidence/1`；在建门与消费两个时点各写一份。
- `changed(before, after) -> [path]`（按 sha256 比差集）。
- 取证源解析：verdict-producing 源**取最小**（fail-closed）；correction 为**单向 dispute**；`bound` = 值层 `meets` ∧ 绑定层（sha/锚点存在且匹配）；缺绑定 ⇒ `not bound`（**不是**默认 bound）。

## 契约（不得重定义）

- **不就地改写任何既有证据文件**（`l3-verdict.txt` 等只读）。
- 不存在单一线性优先级（三命题不可比）——这句话要写成模块 docstring。
- `_create_gate`（`conductor.py:2159`）与消费点的接线由 T-07 完成；本卡只交付模块 + 单测。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_evidence.py -q`

## 非空洞对照（必须附在回执里）

- 应答窗口内改写证据文件 ⇒ `changed[]` 必须非空（VC-045）。
- 无 provenance / 无 sha 绑定 ⇒ 必须判 `not bound`（若默认 bound 则用例红）。
- correction 写 `corrected_value: "below"` 而 verdict 为 `meets` ⇒ 取证结果必须 `below`（单向 dispute；E2 `feature-l3-readcap-injection` 是真实形态）。

## 风险与注意

- E2 反例（verdict `meets` + correction `below` + roadmap `done` + stage `closed`）是**最硬反例**，用例必须逐字锚定该 key 的真实文件内容。
- sidecar 是新文件：只允许写在 `<gates>/` 下，不得创建其它目录。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-06-evidence-provenance/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
