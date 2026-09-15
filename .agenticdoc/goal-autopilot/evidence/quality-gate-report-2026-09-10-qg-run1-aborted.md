# Quality Gate Report: goal-autopilot

**时间**: 2026-09-10
**触发**: 合入前
**范围**: 全量
**结论状态**: 前置门禁失败，按工作流 Step 1 中止；未进入问题机械生成、逐 VC 证据核查及二次印证。

## 前置门禁

| 检查项 | 状态 | 证据引用 | 备注 |
|--------|------|---------|------|
| spec.md 存在 AC 编号 | ✅ 通过 | `spec.md` §3；AC-001~AC-025 | 共 25 个唯一 AC。 |
| design.md 存在 VC 编号 | ✅ 通过 | `design.md` §7；VC-001~VC-027 | 共 27 个唯一 VC。 |
| AC→VC 映射覆盖 100% | ✅ 通过 | `design.md:569-593` | AC-001~AC-025 每项均有非空 VC 映射。 |
| evidence-requirement.md 存在 | ✅ 通过 | `evidence-requirement.md` | 文件存在且含 AC/VC 充分性矩阵。 |
| ac_fingerprint 一致 | ❌ 失败 | `evidence-requirement.md`「锁定指纹」；机械命令输出 `ccc2c018e052` | 记录值为 `475a2958a5ca`，与任务指定命令 `grep -oE 'AC-[0-9]{3}' spec.md \| sort -u \| sha1sum` 的当前前 12 位不一致。 |
| evidence/baseline/ 非空 | ❌ 失败 | `evidence/` 目录清单 | 要求的 `evidence/baseline/` 目录不存在。现有 `evidence/baseline-manual-suites.md` 是相邻单文件，不满足任务及工作流指定的目录前置条件。 |
| 每个 task 有非空 ac_refs/vc_refs | ✅ 通过 | `tasks/T-01-baseline-freeze.md:8-9` 至 `tasks/T-18-final-wrap-up.md:8-9` | 18 个 T-01~T-18 任务均有非空绑定。 |

## 问题清单与核查结果

> 工作流规定前置门禁任一失败即报告 ❌ 并中止，因此未生成 Q-AC-001~025、Q-VC-001~027、Q-COV-* 或交叉问题，也未使用 `final-verification.md` 的结论替代独立核查。

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|--------|------|------|---------|------|
| Q-PRE-001 | 当前 spec 的 AC 指纹是否与 evidence requirement 锁定指纹一致？ | ❌ 无证据链闭合 | 当前值 `ccc2c018e052`；记录值 `475a2958a5ca` | 锁定基准与当前机械计算结果不一致，后续 AC/VC 证据不可据此判定充分。 |
| Q-PRE-002 | 冻结 PASS 基线是否位于要求的非空 `evidence/baseline/`？ | ❌ 无证据链闭合 | `evidence/` 仅有 `baseline-manual-suites.md`、`research/`、`runs/` | 指定基线目录缺失，无法按工作流目录约定执行 runs 对 baseline 的逐项比较。 |

## 汇总

- **总问题数**: 2（仅前置门禁阻断问题；正文问题清单未生成）
- **通过（充分）**: 0（0%）
- **有条件通过（不足）**: 0（验证欠债 0 项，0%）
- **未通过（无证据链闭合）**: 2（100%）

**质检结论**: ❌ 未通过（2 项前置门禁需修复）

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|------|------|---------|---------|
| Q-PRE-001 | `evidence-requirement.md` 记录的 ac_fingerprint 与当前 spec 机械指纹不一致 | 审核 spec 锁定内容及指纹生成口径；确认 AC 不应变更后，按 system-design Step 6 重新生成并锁定 evidence requirement；不得仅手改哈希以绕过门禁 | PM reopen system-design / T-18 |
| Q-PRE-002 | T-01 基线产物保存为 `evidence/baseline-manual-suites.md`，而门禁要求 `evidence/baseline/` 非空 | 明确并统一基线存储契约；若工作流目录约定为权威，将冻结基线按受控任务落入 `evidence/baseline/`，保留来源与冻结 commit，然后重新执行全量 quality gate | PM reopen T-01 / T-18 |

## 二次印证结论

未执行。前置门禁失败后按 `workflow-quality-gate.md` Step 1 强制中止；因此性能、平台、安全约束覆盖，Function Flow 节点覆盖，Coverage Matrix 异常路径覆盖，Error Fingerprint 关闭状态及 7 项遗留是否构成验证欠债均未获准进入核查。修复上述两项后必须从 Step 1 重新运行全量质检，不得复用本报告作为 AC/VC 通过证据。
