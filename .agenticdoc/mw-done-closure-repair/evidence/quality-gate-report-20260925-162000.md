# Quality Gate Report: mw-done-closure-repair
**时间**: 2026-09-25T16:20:00+08:00
**触发**: execute 完成 → done 前（合入前全量质检）
**范围**: 全量（AC-001..011 / VC-001..013）

**基准**: spec.md（AC 锁定 2026-09-25T11:16:40+08:00，5 处 [REVISED] 依 dcr-review-spec-design）· design.md（D-001..D-007）· evidence-requirement.md（ac_fingerprint `b944d7646135`，门禁口径 sorted-unique AC-ID sha1 前 12 位，实测一致）· 运行证据 evidence/runs/run-{closure,exec,suite,e2e-l2}-20260925.txt · 前置基线 evidence/plan-prefix-e2e-20260925.md（修复前红）· 集成回归 evidence/plan-postfix-regression-20260925.md

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | 标准词表下 verify→done 零人工达 DONE | ✅ 充分 | run-exec `VC-001: phase=DONE stalled_gates=0 gate_answered=0`；run-e2e-l2 7/7（full_chain 从修复前红转绿） | — |
| Q-AC-002 | 失败原文逐字进 reprompt prompt + 框架零词表 | ✅ 充分 | run-exec `VC-002: stderr_shape=advance_phase.py failure_lines=2` + `VC-002: prompt_contains_failure_lines=true prompt_equals_fixed_base_plus_lines=true`；run-closure 32 passed（含词表扫描用例） | 指示常量含形状约束句（P-013 修正），仍零词表字面量 |
| Q-AC-003 | 三条件覆盖授权（任一假不覆盖） | ✅ 充分 | run-closure 32 passed（真值表 4 否定例 + 全真例 + 原子性）；run-exec `VC-006: sha_mismatch_no_overwrite=true` | — |
| Q-AC-004 | 人工修稿保护 | ✅ 充分 | run-exec `VC-006: bytes_unchanged=true advance_exit=0` + `VC-006: sha_mismatch_no_overwrite=true draft_preserved=true resume_credit_used=true` | 含 stall→approve→resume 恢复链 |
| Q-AC-005 | reprompt 自持预算封顶 + verdict 保真 meets | ✅ 充分 | run-exec `VC-007: stalled=true l3_dispatches=1 verdict=meets` | dispatch 总数 ≤ l3_limit 含首轮 |
| Q-AC-006 | 非 achieved.md 失败走既有 streak 路径 | ✅ 充分 | run-exec `VC-008: l3_dispatch_delta=0 streak_stall=true` | — |
| Q-AC-007 | reprompt 在飞期零 advance | ✅ 充分 | run-exec `VC-009: advance_events_delta=0` | — |
| Q-AC-008 | 词表可移植（第二词表） | ✅ 充分 | run-exec `VC-010: stalled_gates=0 gate_answered=0 phase=DONE`（「行为影响」「未了事项」） | — |
| Q-AC-009 | 门禁应答恰一次、不洪泛 | ✅ 充分 | run-exec `VC-011: max_answered_per_gate=1 gates_growth=0`（30 tick 混合） | 4e874f5cc 回归锁 |
| Q-AC-010 | achieved.md 逐字转写 | ✅ 充分 | run-exec `VC-012: verdict=meets byte_equal=true` + `VC-012: verdict=meets qg_reports=1 achieved_bytes=587 advance_exit=0` | — |
| Q-AC-011 | marker 单文件一次性生命周期 | ✅ 充分 | run-exec `VC-013: marker_absent=true/false/true marker_count=0/1/0`（覆盖成功/重复失败/终态三态）+ run-closure L1 | — |
| Q-VC-001..013 | 各 VC 断言的 [VERIFY] PASS | ✅ 充分 | run-exec 22 条 [VERIFY]（VC-001/002/006/007/008/009/010/011/012/013）+ run-closure（VC-003/004/005） | VC 编号与本 key design §7 对应 |
| Q-COV-1 | 崩溃窗口 W1-W9+5b fail-safe | ✅ 充分 | design §6 覆盖矩阵 + dcr-review R4 逐窗重演 + closure 原子性/幂等用例 | — |
| Q-COV-2 | stall→人工批准→resume→reprompt 恢复链 | ✅ 充分 | dcr-review R4 推演 + run-exec `VC-006: resume_credit_used=true` | — |
| Q-COV-3 | e2e 全链（真实 advance + 真实门禁） | ✅ 充分 | run-e2e-l2 7/7；修复前 full_chain 红（plan-prefix-e2e §二 5 连败 stall）→ 修复后绿 | D-007 证据链闭环 |

## 汇总

- **总问题数**: 15（11 Q-AC 合并引用 + VC 批核查 + 3 交叉覆盖）
- **通过（充分）**: 15（100%）
- **有条件通过（不足）**: 0
- **未通过（无证据）**: 0

**质检结论**: ✅ 通过

## 范围外事项（登记，不阻断）

| 事项 | 判定依据 | 去向 |
|------|---------|------|
| `test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below` 失败 | HEAD/1b2a1efde worktree 独立复现（本 key 全部改动排除后仍在）| 外域 key（verdict 系列），已通报用户 |
| `test_autopilot_readcap_injection.py::test_baseline_left_end_bound` 失败 | 同上（冻结 sha vs HEAD blob）| readcap key 域既有 |
| e2e 夹具 credentials.timi 漂移（09-10 起静默断链） | plan-prefix-e2e §一根因链 + 修复验证 | 已随本 key 修复（CHANGELOG Fixed 条目 2） |

## 二次印证结论

- spec 约束（GC-1..4）逐一核过：改动面 = autopilot/ 源码 + 包根测试 + .gitignore 一行 ✓；reviewer 只读工具集未动 ✓；转写路径零改动（dcr-review R2/R3 复核）✓；词表零硬编码（VC-003 扫描）✓。
- design Function Flow 节点 ↔ VC 全对应；Coverage Matrix 异常路径（W1-W9、恢复链、TOCTOU 微窗）均有 Q-COV。
- 无 vc_refs 空绑定的功能任务卡（T-00/T-10 为前置/收尾卡，无 AC 绑定属设计内）。
- 执行期设计偏差 5 项（worker B 报告）均按任务卡授权且方向安全（fail-closed 保持）。
