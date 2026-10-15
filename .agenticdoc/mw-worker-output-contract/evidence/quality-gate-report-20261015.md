# quality-gate report — mw-worker-output-contract（2026-10-15 结案）

## 全 AC 勾销表

| AC | 内容 | 兑现证据（路径/测试/输出） | 状态 |
|---|---|---|---|
| AC-001 | 契约判定跨入口一致 | `mwoc-w2` 40/40；`mwoc-matrix-t07` AC-001 8 例（checkRecovery vs readTerminalGaps 双一致） | PASS |
| AC-002 | settle 回读逐段点名缺失 | `mwoc-w2` AC-002 表逐条（40/40 内含） | PASS |
| AC-003 | 受判产物翻转（exit=2→0） | `dispatch-recovery-terminal:197`、`output-recovery-contract:301`（两次 settle 流）14/14+16/16 | PASS |
| AC-004 | 自检回合（已交付条件） | `worker-mode.ts::settleOrSelfCheck` isDelivered；T-13 交付 `woc-t13-selfcheck-r2/output.md`；ACB-V1 审计 3/3 PASS | PASS |
| AC-005 | 历史产物重放 exit=2→0 | `mwoc-matrix-t07` AC-005 3/3（mdc-rq1/mwgf-drq3/mvr-rq5 盘上文本） | PASS |
| AC-006 | no-product 裁决 | `mwds-t04:401`（undelivered ⇒ exit=2 + no-product: + 1 告警）19/19 | PASS |
| AC-010(a) | 语料两数 | `evidence/woc-t07-corpus-20261015.txt`（n=465/466，tierA 38.7-38.8%，tierB 14.0-14.2%） | PASS |
| AC-010(b) | 新产物全 exit=0 | `evidence/scripts/new-worker-exit-scan.py`：runs=6 passed=6 coverage_ok=true | PASS |
| AC-010(c) | 111 例逐条处置 | `evidence/woc-t07-flip-disposition-20261015.txt`（3 rescued/83 still-fails/25 exempt） | PASS |
| AC-014/015 | 候选集 × 判定 | `output-writer.ts::judgedProductFile`（report→slug→output）；`mwoc-matrix-t07` AC-015 三形态 settle exit=0 | PASS |
| AC-017 | 四段判据 | `mwoc-matrix-t07` AC-017(a)0 行/(b)net-file-api 各 1/(c)allow=2 deny=0/(d)unjudgeable 派生 | PASS |

## VC / 基线

- 24 文件基线差分（DR6 baseline 558 例 vs 本次）：**NEW FAILURES = 0**，STILL FAILING = 恰 5 个 HEAD 既存红（`worker-file-tool:177/:285`、`agent-team-loop:6381`、`mwds-t02:345`、`mwds-t23:295`），MISSING = 7 全为预期改名。产物：`evidence/woc-t07-baseline-diff-20261015.txt`、`woc-t07-perfile-20261015.txt`。
- `npx tsgo --noEmit` = 0（T-05/T-07/T-13 各阶段复核均 0）。
- AC-017(d) 12 个 ledger 家族既有文件全部 PASS（T-02 锁定，`mwoc-matrix-t07` + 24 文件集合内）。

## 证据链溯源

- 实现冻结：批次 A（T-01/T-03/T-06）+ B（T-02/T-04/T-05）+ T-10/T-11/T-12/T-13，各卡 `workers/*/output.md` + `evidence/`。
- 矩阵/基线：`woc-t07-matrix`（25/25 套件 + 24 文件对照 + 语料 4 数 + 111 例处置表）。
- 部署生效：T-08 PM 直执（build/restart/doctor/AC-010(b) 6/6）。**手动步骤：所有已打开的 pi 窗口需执行 `/reload` 才能加载新 bundle**（0.83.0，`bundle stale: False`；16 个 node 进程即待 reload 窗口，T-08 `output.md` 有逐窗口说明）。
- 探针独立审计：ACB-V1（settle 三条件 PASS + 三副本一致）、ACB-V2（ui-bridge 三条件 PASS + dist 一致）。

## 未覆盖面声明

- 未做「HEAD 版运行」对照（git archive 方案未实跑）；MISSING=7 的改名判定依据 DR6 登记 + 逐文件表 + T-13 交付说明三处一致。
- 动态 run 级验证（真实 worker 的 exit=2 触发/自检回合）由 AC-010(b) 6 探针覆盖，但未构造「刻意缺段触发自检」的盘上复现（由 `mwoc-w2`/`mwds-*` 套件等价覆盖）。
- 模型挂死（D-016）未在本 key 修复（去向：建议立新 key）。

## PASS 结论

全 AC（AC-001…017 兑现项）PASS；新增红 = 0；AC-010(b) 6/6；tsgo=0。**判定：通过（PASS）。**
