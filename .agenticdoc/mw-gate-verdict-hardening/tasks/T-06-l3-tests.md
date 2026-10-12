# T-06: G1 用例集（正/负/边界 + 非空洞对照）

- 波次: **0** · 依赖: T-01
- 写面（独占）:
  - `packages/multi-workers/test_autopilot_l3_aborted.py`（**新建**）
- AC: AC-001, AC-002, AC-003, AC-004, AC-014 · VC: VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-017
- 基线: `10446aefb`

## 目标

把 `T-01` 的每条判据钉成**可复算**的用例，并且每条都带"摘掉判据就转红"的非空洞对照。

## 交付物

用例清单（命名用 P/N/X 前缀，回执里逐条列绿/红）：

- **P1-P7（正例）**：marker 命中 + 无合格源 ⇒ aborted；`data` 键集逐字等于固定八元组；预算未耗尽 ⇒ 重掷且 `abort_used=1`；共享预算耗尽仍重掷；重掷出裁决 ⇒ 正常推进；`report.md` 合格 ⇒ **不**判 aborted；`output.md` 两节齐备 ⇒ **不**判 aborted。
- **N1-N6（负例）**：无 marker；marker 在尾窗之外；provider 403（有 marker 但不属本类）；真 FAIL 标记行；散文 `report.md`（第四类，design 已声明归属）；两节齐备 + 有 marker。
- **X1-X2（非空洞对照）**：X1 摘掉指纹判定 ⇒ P1 转红；X2 把 marker 移出尾 64 KiB ⇒ 必须**不**判 aborted。
- **夹具**（关键约束）：**真实语料不可入仓**（路径在本机外部项目根）⇒ 按实测**最小形状**复刻：`worker.log` 160~179 B、marker 距文件尾 ≤ 40 B、`[worker] done exit=0` 行、队列行 `status=failed`。

## 契约（不得重定义）

- 夹具必须**逐字**含 `stream closed before response.completed` 才能命中（子串匹配，不断言出处）。
- 队列行必须写成 `status=failed`（**不得**为了"好看"写成 done，否则与真实 6/6 语义不符）。
- 断言必须走**真实代码路径**（调用 `conductor._l3_round_verdict` 或等价的生产入口），不得只测一个被抽出来的 helper（P-023）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_l3_aborted.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py -q`（回归）

## 非空洞对照（必须附在回执里）

见 X1/X2；回执要贴"摘掉判据后 X1 的实际失败输出"，不许只写"已验证非空洞"。

## 风险与注意

- `test_autopilot_auto_decision.py:301/333/338` 的 `== 12` 计数锁不在本卡写面（归 `T-14`）：本卡只需保证新原因码不引入 drift 类失败。
- 与 `T-01` 同波但依赖它：`T-01` 提交后再开工，或同会话内先落 T-01 再写用例。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-06-l3-tests/report.md`（含 `[VERIFY]` 命令原文与输出、X1/X2 的实际红/绿），写完立即复制到 `evidence/runs/`。
