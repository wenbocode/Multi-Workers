# Quality Gate Report: mw-partition-parent-extended

**时间**: 2026-09-20T16:15:00+08:00
**触发**: Stage 1~4 全部完成（T-01~T-04 验证通过后，合入前全量质检）
**范围**: 全量（AC-001~006 / VC-001~009 / Coverage F1~F7）

## 前置门禁

| 检查项 | 结果 |
|--------|------|
| spec.md 存在 AC 编号 | ✅ AC-001~006 |
| design.md 存在 VC 编号 | ✅ VC-001~009 |
| AC→VC 映射覆盖 100% | ✅ 6/6（机械校验：spec ACs ⊆ design ACs，NONE missing） |
| evidence-requirement.md 存在 | ✅ |
| ac_fingerprint 一致 | ✅ `6a9e7040d5d2`（门禁公式重算，AC 零变更） |
| evidence/baseline/ 非空 | ⚠️ 空（见汇总：L1-only 设计，无 L2 基线要求） |
| 每个 task 非空 ac_refs/vc_refs | ✅ T-01~T-04 全绑定 |

## 问题清单与核查结果

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-AC-001 | Py 展开并入 parent（顺序/判重/legacy 零变化） | ✅ 充分 | verify-run §VC-001；test_partition_dispatch 27 passed | — |
| Q-AC-002 | worker union（门控/不作用域/wiring 双形态标签） | ✅ 充分 | verify-run §VC-002/003/004；autopilot-read-scope 28 passed | — |
| Q-AC-003 | deny 先于 union | ✅ 充分 | verify-run §VC-005（wiring + rule=deny-glob） | — |
| Q-AC-004 | 写路径零拦截回归锁定 | ✅ 充分 | verify-run §VC-006（write/edit/bash 三工具 + 既有 non-read 用例） | — |
| Q-AC-005 | 措辞/标签/golden 同步 | ✅ 充分 | verify-run §VC-007/008（golden parity + stderr 断言 + grep 审计残留 0） | — |
| Q-AC-006 | 零回归与修改面限定 | ✅ 充分 | verify-run §VC-009（hunk 级审计清单；dual/single 零修改） | check 的 packages/ai 14 错为并发 session WIP，非本 key 面 |
| Q-VC-001~009 | 各 VC [VERIFY] PASS 证据 | ✅ 充分 | evidence/verify-run-2026-09-20.md（9/9 行齐，含来源与命令） | — |
| Q-COV-F1 | Py 展开三根互异 + 判重边界 + legacy | ✅ 充分 | VC-001（dedup case 双形态：显式列 parent / parent==control） | — |
| Q-COV-F2 | union 纯函数边界（无模式行/无行/deny-only/空 scope） | ✅ 充分 | VC-002/003 矩阵 | — |
| Q-COV-F3 | wiring 边界（旧标签在途兼容） | ✅ 充分 | VC-004 用旧标签、VC-005 用新标签，双形态均过 wiring | — |
| Q-COV-F4 | deny 与 scope 同时命中 | ✅ 充分 | VC-005 | — |
| Q-COV-F5 | 写零拦截 | ✅ 充分 | VC-006 + 既有 non-read 用例 | — |
| Q-COV-F6 | 标签异常路径（无 read-only 残留） | ✅ 充分 | VC-008（grep 审计：2 处残留均为无关语义） | — |
| Q-COV-F7 | 修改面限定 | ✅ 充分 | VC-009（git diff hunk 清单逐条归类） | — |
| Q-CROSS-1 | 空 read_scope（全拒形态）不因 union 失效 | ✅ 充分 | VC-003（emptyScope 原引用返回断言） | spec §2.3 红线 |
| Q-CROSS-2 | conductor 路径 frontmatter 与 worker 允许集一致性 | ✅ 充分 | Py 展开（VC-001）+ worker union（VC-004）双层；冗余无害（containment .some()） | D-001 |
| Q-CROSS-3 | 升级在途 task.md（旧标签）union 不失效 | ✅ 充分 | VC-002 双形态解析 + VC-004 旧标签过 wiring | D-004 |

## 汇总

- **总问题数**: 21（Q-AC 6 + Q-VC 9 + Q-COV 7 + Q-CROSS 3，去重后 21 个独立问题）
- **通过（充分）**: 21（100%）
- **有条件通过（不足）**: 0
- **未通过**: 0

**质检结论**: ✅ 通过

**⚠️ 事项（非欠债，设计取舍）**:
1. evidence/baseline/ 为空——本 key 全部 VC 为 L1（design §6），不改 spawn/cwd/进程模型（GC-2 零接触），wiring 用例经 `workerModeActivate` 真实激活路径，无需 L2 基线。
2. `npm run check` 全仓 tsgo 因并发 session 的 packages/ai kimi-coding WIP（`kimi-coding.models.ts` 删除态）报 14 错；本 key 触达面（coding-agent + multi-workers）0 error / 0 warning / 0 info。该 WIP 非本 key 回归，按多 session 规则未触碰。

## 未通过问题行动计划

（无）

## 二次印证结论

- spec §2 约束（fail-closed 空 scope、P-001/P-002、parity）→ Q-CROSS-1 / VC-007 / 过程留痕覆盖 ✅
- Function Flow 两图全部节点（含 reject/blocked/no-interception 异常出口）→ VC-001~006 映射 ✅
- Coverage Matrix 异常路径行（F1 legacy / F2 无行 / F6 残留）→ Q-COV 对应 ✅
- task vc_refs 空绑定 → 无 ✅
- 无遗漏。
