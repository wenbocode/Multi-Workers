# design 调研：开关放在哪一层、manifest 为什么必须是文件（2026-10-22）

本 note 支撑 `design.md` 的三项架构选择。所有结论来自本 key 的三份 spec 阶段 research，
不新增实测。

## 1. 开关放在派发层，不放在 worker 层

- 事实：claims 的判定面与定价面**只在 TS 侧存在**，Python 服务层只拿 claims 定价、不认 claims
  （`dispatch.py:2095-2098`；RQ-1 §1.3 字段级差异表）。若把开关放在 worker 侧，则
  "不拆"这个决定要在 Python spawn 之后才能生效 —— 此时队列行、taskDir 已经写了，违反 GC-3 的零副作用。
- 结论：开关必须由**派发前的规划器**读取（TS `pm/ui-bridge.ts` 与 Python `autopilot/dispatch.py` 各一个读取点），
  形态照抄已验证的 `claimGateMode()` / `claim_gate()`（D-006：常量 + env + 平价锁）。

## 2. manifest 必须是独立文件，不能只嵌在 task.md

- 事实：子/母卡的 `card_sha256` 今天**没有链**（RQ-1 §6.3）；`task_graph` 在 `<task>-u1` / `<task>-u2`
  这类共享数字核心的命名上会报 ambiguous 并让整 key 退化串行（RQ-1 §6.5）。
- 推论：merge 的"母卡 id 集"若从 task.md 现场重建，母卡被改过就无从发现；若从 manifest 读，
  manifest 自身可被钉 sha（母卡 sha + 各子卡 sha + 本文件 sha）。
- 结论：`evidence/split/<task>-manifest.json` 是唯一真相，merge 只对账；manifest 内嵌
  `parent_sha256` / `unit_sha256[]` / `ids[]` / `packing[]`（簇原子性证据）。

## 3. `plan` 档先于 `on`：把决定成本压到"只读一次产物"

- 事实：一次 A/B 需要 20-claim 卡，而语料里**最大 6 条**（RQ-1 §3.3、RQ-2 §4）；20 条卡目前不存在。
- 推论：直接上 `on` 会在"卡本身造不出来"上卡住；而 `plan` 档能先用真实 diff 产出 manifest 给人看
  （单元数、每单元 id、cap 膨胀比），**零派发成本**。
- 结论：`off → plan → on` 三档，默认 `off`。`plan` 的产出就是 §5.2 判据 1（保真）的纸面版。

## 4. 与既有判据的冲突（必须豁免）

- RQ-2 §3.2 已证：`claims:fetches:<sum>><cap>` 与 `>trace:<n>` 在 merge 模式必然误报
  （20 claim 拆 4×5：`Σ取数 52 > cap 30 > trace 4`），必须显式豁免，不能"改判据值"掩盖。
- RQ-3 §3.3 已证：merge 单元的 `closed` 不进分母，否则比值腰斩。

## 4 个来源

- `evidence/research/spec-rq1-orchestration-seams-20261022.md`
- `evidence/research/spec-rq2-split-fidelity-20261022.md`
- `evidence/research/spec-rq3-metrics-baseline-20261022.md`
- `claim-driven-review/achieved.md`（真实基线 52 / 110,666）
