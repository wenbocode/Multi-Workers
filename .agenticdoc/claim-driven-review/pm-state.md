# PM State: claim-driven-review

## 1. Snapshot
- Key: claim-driven-review
- Claim-Id: WENBOZHOU-PC4:69520
- Phase: DONE
- Next Action: TASKS→EXECUTE：派发 B1（T-01 / T-03 / T-05）
- Started: 2026-10-21 15:54
- Updated: 2026-10-22 20:18
- Completed: 2026-10-22 20:18

## 2. Task Status

| 任务 | 类型 | 状态 |
|---|---|---|
| cdr-rq1-review-corpus | research | done（已 absorb/ack） |
| cdr-rq2-seams | research | done（已 absorb/ack） |
| cdr-rq3-claim-taxonomy | research | done（已 absorb/ack） |
| cdr-t01-l1-contract | coding | done（22/22 绿；`npm run check` 因 3 个既有 mwoc 告警退 1，非本卡） |
| cdr-t03-python-dispatch | coding | done（9/9 新用例；无 claims 卡 462 B 逐字节相同；3 红为另一窗口 `decision` 类型的既有红） |
| cdr-t05-metrics | coding | running |
| cdr-t05-metrics | coding | done（11 新用例 + 52 usage + 48 ledger 全绿；`n/a` 分支已锁） |
| cdr-t04a-settle-readonly | coding | done（32 it / 48 绿；`claims` 缺省时 `TerminalGaps` 逐字段不变） |
| cdr-t02-pm-dispatch | coding | done（14 新用例 + 7 零副作用，60/60 绿；PM 已改回 advisory 零拒绝） |
| cdr-t04b-worker-wiring | coding | done（22 it；三文件 70/70 + 回归 202/202） |

> PM 直改（2026-10-21 17:40）：`claimReadScope` 改为**锚点 + claims 的 `定位`（去 `:line`/`:a-b`/`#<id>`）**（D-012）。原实现只给 key 目录 + goal.md，断言指向 `packages/**` 时 review 单元一个字节也读不到。测试：新增 1 条（`16/16`），累加 7 文件 **154/154** 绿；biome 0 诊断，`tsgo --noEmit` rc=0。
| T-04b | coding | running |
| T-06 | coding | running（平价锁 + 文档） |

> 已知基线红（**不属于本 key，不要修**）：另一窗口 `ds-w8-decision-type` 的未提交改动新增了 `decision` 类型，导致 `test_autopilot_dispatch.py::test_registry_types_and_tools` 与 `test_autopilot_l0.py::test_vc014_pm_dispatch_awareness_texts` 红；`test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 是冻结基线漂移（HEAD 已非 75298ee4e）。

## 3. Evidence Ledger

| 文件 | 内容 | 关键数字 |
|---|---|---|
| `evidence/research/spec-rq0-research-plan-20261020.md` | 调研计划 + 已确认事实边界 | 3 个 RQ 单元 |
| `evidence/research/spec-rq1-review-corpus-20261020.md` | review 类 run 成本标定（41 KB，T1/T2 机读表） | 115 attempt / 47 dir；取数 p50 53 / p90 99.6；tokens/次 p50 3,230 / p90 4,854；chars/4 est=0.795×实测；判定单元 p50 11、与取数 r=0.136；安全带 <400k chars，必降级 >650k |
| `evidence/research/spec-rq3-claim-taxonomy-20261020.md` | 断言分类法 + 反例集 + schema（66 KB） | 104 单元：cmd 21 / grep 28 / struct 29 / manual 26；分类器一致率 63.5%（dangerous 1、保守 29）；9 条误拒 + 10 条绕过；21 个 cmd 单元中 11 个无执行串；46 次 review 派发 12 次只有 output.md、0 份带 [VERIFY] |
| `evidence/research/spec-rq2-seams-20261020.md` | 五层接缝盘点 + 破坏面（47 KB） | gate 插入点 `ui-bridge.ts:2585`（可 stat）、拒绝码 `dispatch-card`（2188）、零副作用测试 `dispatch-card-injection.test.ts:344-483`；结算挂 `readTerminalGaps`（`output-writer.ts:357-425`）在 `worker-mode.ts:3872` 之前；`allowedCalls` 计调用不计去重文件、仅 read 计字节；PM 侧无 read_scope 渲染；不需新类型（T-17 绿）；度量用独立 `[CLAIMS]` 行；`dist/` tracked |
| `design.md` | 四层设计 + D-001…D-008 + 测试矩阵 | 预算式、门禁表、P1–P4 落地顺序 |

## 4. Hypothesis Queue

- H1（已证实）：review 成本与仓库规模绑定、与断言数量无关 → `r=0.136`（RQ-1 §4）。
- H2（待 RQ-2）：`read_scope` 仅有累计字节口径，无单次口径 → 单次 12 KiB 约束需另找落点。
- H3（待测）：将 p90 卡片（20 claim）拆 4×5 后，`tokens_per_closed_claim` 显著低于 1×20（需 AC-005 落地后实测）。
- H4（已证实）：四分之一判定单元天然只能 manual → manual 不得被当作失败，但必须有上限与双倍记账（RQ-3 §6）。
- H5（已证实）：门禁会被“自证 / 兜底 / 自动填充”三类写法绕过，故 AC-001 必须校验卡文而非渲染后 task.md。

## 5. Decisions

- D-001：AC-003/AC-004 的预算常数改用 RQ-1 标定值（30 次 / 393,216 B / 5 claims per worker），放弃初稿的 60 次 / 512 KiB / 2 claims。依据：RQ-1 §5 的 p90 推导与历史撞墙样本 209,761–214,200。
- D-002：合并单元与取证单元分派但**不共享预算**；merge 单元只读裁决文件，不重读取证面。
- D-003：`断言裁决` 采用七列（`裁决` 与 `判定` 分置），`unverified` 用 7 词闭集单源；分类器只做筛查（一致率 63.5% 不足以拒绝），判据类由卡自报、只校前缀一致。依据 RQ-3 §2.4/§5。
- D-004：新增 AC-008 反绕过判据集（自证集合 / unverified 比例 / 取数上界 / 双向 id / 兜底标记 / carried-from），全部零成本且各带一条负例测试。
- D-005（待用户确认）：不给 review 加 `bash`；`cmd` 类断言由 PM 在派发前预执行并落盘 `evidence/claims/<run>.md`，review 单元只引用 `path:line`。依据：GC-2 且 `verifier`/`reviewer` 同为 `_REVIEW_TOOLS`，无 bash 可借。
- D-006（待用户确认）：灰度用 `CLAIM_GATE_DEFAULT` 常量 + `MW_CLAIM_GATE` 环境变量，不做 per-key 配置键（避开 21-key 平价锁）。
- D-007：预算取 RQ-1 标定（30 次 / 393,216 B / K=5），否决 RQ-2 并行期写的占位值 `min(3n,60)`/512KiB。
- D-008：`fetches` 口径写死为 `[FLOW] tool_call` 读类计数（与 `allowedCalls` 不等价）。
- D-009：`run.json` 是 **worker 侧** `recordEnd` 写的（launcher 只读），故 `claims` 子对象归 T-04b，不单开 launcher 卡。依据：`launcher.py:990-1003` 注释 “The worker-written run.json is the product”。
- D-010：T-03 实测的 3 条 pytest 红全部归因于另一窗口的未提交 `decision` 类型与冻结基线漂移，**不在本 key 修复**；本 key 只保证新增用例与无 claims 卡字节不变。
- D-011：**advisory 零拒绝**（PM 直接修正 T-02 的偏差）。理由：P-048 实测过 schema 过严导致的连续误拒；灰度门禁若仍能拒绝，表格里一个拼写错误就能丢掉一次派发。落地：`claimsMissing = enforce ? [...errors, ...audit] : []`，advisory 的 `warnings` 收全部 findings。
- D-012：**`read_scope` 由 claims 的 `定位` 推导**（锚点 + 去 span 的文件路径），不是只有 key 目录 + goal.md。T-02 的原实现会让断言指向 `packages/**` 的 review 单元读不到任何东西（`read` 被 scope 拦），整条链退化成“全部无法判定”；这是 T-07 前必修项。

## 6. Turn End Records

- T1 (2026-10-21 15:54)：建 key + spec + research plan；派 3 张并行 research 卡（首次被 SPEC 相位文档门禁与写面门禁拦截，补 rq0 计划与 `## 写入允许面` 后放行）。
- T2 (2026-10-21 16:03)：吸收 RQ-1；按标定值重写 AC-003/004/005；rq2/rq3 仍在跑。
- T3 (2026-10-21 16:12)：吸收 RQ-3；重写 AC-001/002、新增 AC-008、补 §4 三条实测风险与 §5 四项可复用资产；rq2 仍在跑。
- T4 (2026-10-21 16:20)：吸收 RQ-2；写 `design.md`（D-001…D-008）；spec→design 完成。两项待用户拍板（D-005 / D-006）。

## 7. Process Log

| 时间 | 事件 |
|---|---|
| 2026-10-21 15:54 | `claim-driven-review` init → SPEC（advance_phase） |
| 2026-10-21 16:03 | cdr-rq1-review-corpus done（108 tool calls, 9 min） |
| 2026-10-21 16:12 | cdr-rq3-claim-taxonomy done（77 tool calls, 10 min） |
| 2026-10-21 16:20 | cdr-rq2-seams done（160 tool calls, 13 min）；相位 SPEC→DESIGN |
| 2026-10-21 17:20 | PLAN→TASKS→EXECUTE；B1 派发 T-01/T-03/T-05 |
| 2026-10-21 17:25 | T-01 done（54 tool calls）；探测到另一窗口 `ds-w8-decision-type` 在写 `worker/worker-mode.ts` 与 `pm/*`，→ T-04 拆分、T-02/T-04b 暂缓、改派 T-04a |
| 2026-10-21 16:20 | 框架缺陷：`advance_phase.py:697` 在 Windows 上 `text=True` 解非 UTF-8 输出导致 `stdout=None` 崩溃（相位已正常推进，仅 DecisionReview 未写） |

## 8. Quality Gate / 收口（2026-10-22 17:05）

- QG 结论: **PASS（scope=narrow）** —— evidence/quality-gate-report-20261022.md
- AC 底账: AC-001/002/003/007/008 已充分；AC-005/006 部分；**AC-004 未达成（移交新 key）**
- §0 预期收益: B1 达成（52→16）/ B2 达成（253k→41k 峰值）/ B3 达成（降级 0）/ **B4 未达成（n/a，移交）**
- 测试: TS 159 passed（8 套）/ Python 27 passed（3 文件）/ 	sgo --noEmit rc=0 / 
pm run check 仅 5 条已知基线
- 待人工签收: 由 mw decide sign 生成 review 签收记录（conclusion 预期 
arrow），agent 无权写该通道
