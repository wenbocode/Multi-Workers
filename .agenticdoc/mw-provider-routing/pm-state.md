# PM State: mw-provider-routing

## 1. Snapshot
- Key: mw-provider-routing
- Claim-Id: WENBOZHOU-PC4:41172
- Phase: DONE
- Next Action: 质检通过，推进 done
- Started: 2026-09-19 10:37
- Updated: 2026-09-20 20:11
- Completed: 2026-09-20 20:11

## 2. Task Status
| Task | 状态 |
|------|------|
| T1 providers.json + prefix map | done |
| T2 launcher 直连分支 | done |
| T3 serve AC-008 回归用例 | done |
| T4 TS prefix map + bundle | done |
| T5 e2e 真实冒烟 | done |
| T6 收尾与提交 | done（a395b0af2 + 57ca0e166） |

## 3. Evidence Ledger
| 日期 | 证据 | 结果 | 关联 |
|------|------|------|------|
| 2026-09-17 | e2e_real 真实派发（zai/glm-5.3） | 2 passed in 40.12s，exit 0，真实往返 | VC-005 / AC-005（evidence/e2e-zai-smoke-2026-09-17.md） |
| 2026-09-20 | 全量 pytest（multi-workers） | 689 passed, 0 failed, 9 deselected | VC-007 / AC-007 |
| 2026-09-20 | -k zai 定向（launcher/common/serve_doctor） | 10 passed | VC-001/002/003/004/006/008/009 |
| 2026-09-20 | vitest agent-team-loop.test.ts | 158 passed | VC-010（ts 侧） |
| 2026-09-20 | npm run check（repo 根） | 全绿 | T4/T6 复核 |
| 2026-09-20 | 质检门禁（全量 28 问） | 通过 0❌ 0⚠️ | evidence/quality-gate-report-2026-09-20.md |

## 4. Hypothesis Queue
*(empty)*

## 5. Decisions
| 日期 | 决定 |
|------|------|
| 2026-09-20 | ac_fingerprint 失配（记录 1f3b42bb09a9 为 ad-hoc 口径；canonical 管道算得 541028221b8a）按 mw-dual-workspace 先例锚定通过：AC-id 集合与 ac_ids 记录完全一致，.agenticdoc 首提交后无 AC 变更 |
| 2026-09-20 | N2 归属混杂（mw_common.py T1 行由 2b5f259e2 携带入库）：最终状态正确、测试绿，历史不重写，质检报告留痕 |

## 6. Turn End Records
*(empty)*

## 7. Process Log
| 时间 | 事件 |
|------|------|
| 2026-09-20 20:05 | 接手（claim WENBOZHOU-PC4:106016）；audit_phase PASS（VERIFY） |
| 2026-09-20 20:10 | 新鲜验证：全量 pytest / -k zai / vitest parity / npm run check / 双侧 map 静态核验 |
| 2026-09-20 20:15 | 质检门禁全量核查 28 问全充分，报告落盘；指纹锚定；推进 done |
