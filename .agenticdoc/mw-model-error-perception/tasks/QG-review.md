# QG: mw-model-error-perception 质量门禁审计（证据链闭合性）

type: review

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（GC-1 不改 core / GC-2 文件证据 / GC-3 看门狗语义）。
- 审计对象：已 DONE 的 key `mw-model-error-perception`（worker 模型错误感知 + 进程级 fallback 链）。
- 基准文档：`.agenticdoc/mw-model-error-perception/spec.md`（AC-001~010 + §2.2 阈值 + §4 风险）、`design.md`（D1-D7 决策 + §3.1/§3.2/§3.3 + §4 契约）、`achieved.md`、`key-decision.md`（含 D3 修订与 PM 直执裁决）、`tasks/T-01~T-07`、各 `workers/*/report.md|output.md`。
- 门禁执行证据（只读引用，不重跑）：`evidence/quality-gate-report-20261015.md`（T-07 产出：check/test.sh/pytest 输出摘要 + 7 条 pytest 豁免 + 基线噪声清单）。
- 代码锚点：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3294`（modelExhaustedExit）、`worker/worker-mode.ts:3855` 附近（agent_settled error 分支）、`worker/output-writer.ts`（exitCode 3 渲染）、`pm/pm-orchestrator.ts`（model-error 告警）、`packages/multi-workers/launcher.py:735`（_model_retry_count）、`launcher.py:777`（_try_model_redispatch）、`mw_common.py`（fallback_models 校验）、`mw.py`（_model_write 读改写）。
- 测试锚点：`packages/coding-agent/test/suite/worker-model-error-perception.test.ts`（13 用例）、`packages/multi-workers/test_mep_fallback_config.py` + `test_mep_launcher_redispatch.py`（70 用例）。

## 审计目标（QG 问题清单，按 workflow-quality-gate 三态判定 ✅/⚠️/❌）

1. **AC 逐条证据链**：AC-001~010 每条 → 找到充分证据（测试用例名 + 实现锚点 + 门禁输出/worker 回执），三态判定；任何 AC 无充分证据即 ❌。
2. **契约实现一致性**：design §4 契约（env 三键语义、trace 行格式 `[MODEL_ERR]`/`[MODEL_RETRY]`/`[MODEL_FALLBACK]`/`[MODEL_FALLBACK-SKIP]`、Exit Reason 形状、run.json 字段）与实现逐字段核对（读码验证，非引用报告自述）。
3. **D3 修订落实核查**：worker 侧确认无 followUp 重发残留、无 `PI_WORKER_MODEL_ERR_MAX` 消费（预算已移 launcher）；挂起型判据（lastModelError ∨ (agentRunStarted ∧ ¬sawSuccessfulAssistant)）与 tool-in-flight 分流实现正确。
4. **测试覆盖面缺口**：AC/契约 ↔ 测试用例映射是否存在未覆盖路径（如：restart-safe 计数、预算 0/边界、AC-006 清零语义、AC-007 配置上限、挂起型 vs 工具型分流）。
5. **文档与实现漂移**：README fallback 节 + 4 env 契约行、双包 CHANGELOG 条目 vs 实际实现。
6. **豁免清单抽验**：quality-gate-report 的 7 条 pytest 豁免 + biome/anchor 基线豁免是否确实非本 key 产物（抽验 2-3 条：git log/文件状态核对）。
7. **跨 key 写面纪律**：本 key 变更是否越写面（src/test 改动均应有对应任务卡授权；特别核对 PM 直执的两个测试适配 checkpoint-wiring/autopilot-protocol 是否最小且不动冻结表）。

## 要求

- 报告写入 `.agenticdoc/mw-model-error-perception/evidence/qg-review-20261015.md`（唯一证据文件）。
- 结论三态：✅ 通过 / ⚠️ 有条件通过（列欠债项）/ ❌ 未通过（列修复项 + 根因 + 所需动作）。
- 每个判定给出证据引用（文件:行 或 测试用例名）。
- 只读审计：不修改任何文件（唯一例外=上述报告文件）。

## 未覆盖面声明（审计边界）

- 本审计不重跑任何测试/门禁命令（review 角色无 bash；门禁执行证据取自 T-07 的 quality-gate-report-20261015.md 与各 worker 回执）。
- 不审计其他并行 key（mw-console-storm-hardening 等）的未提交改动；mw.py 中混入的他窗 run-detached 改动仅在「跨 key 写面纪律」条目下做归属区分，不审计其质量。
- 不覆盖运行时激活验证（npm run build + /mw restart 由用户执行，见 T-07 报告生效步骤）。

## 交付格式

- `evidence/qg-review-20261015.md`：问题清单判定表（Q-ID/描述/状态/证据引用/备注）+ 汇总（通过率/欠债/未通过）+ 结论 + 未通过项行动计划。
- 交付说明：三态计数与结论一句话。
