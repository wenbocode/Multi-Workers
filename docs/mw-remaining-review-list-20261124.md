# 剩余开发收尾 Review List（2026-11-24）

本轮执行 key：`mw-remaining-closeout`。原 key 保留原验收与失败历史；本轮负责接续纠错、当前源码复验、精确提交及冻结安装。

| 处理项 | 原 key | 当前结果 |
| --- | --- | --- |
| 额外可写根 | mw-dual-additional-write-roots | 已提交 4bcdbccd5 并全局安装；本轮继承该版本，不重复修改或抢占原 PM |
| 冻结签收元数据 | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff | 纳入当前源码联合验证与冻结候选；保留全部签收证据检查 |
| UE 插件框架安装 | ue-frame-install-generate | 纳入 CLI、Pi 适配与模板；修正测试夹具缺少 testcase 对应 gate，未放宽生产门禁 |
| 检查基线 | mw-repo-check-baseline | 保留 Biome 排除；TS import 检查跳过运行目录；模型检查快照固定为 90ace0f6f 的明确目录 |
| 值守 F3 | mw-duty-followup | 修正未发通知却显示可发送、reserved 崩溃后误认 queued 两类问题；30 项永久回归通过 |
| 运行版本入口 | mw-runtime-version / mw-pi-version | CLI、窗口入口与历史回归纳入统一复验及冻结候选 |
| 模型目录 | mw-zai-glm54 / mw-zai-glm54-release | 保留当前运行目录及 GLM-5.4；运行目录与检查快照各自记录来源 |
| 遗留测试 | mw-issue-feedback / mw-window-claim-isolation / mw-dp-material-pipeline / mw-dp-consolidation | 按当前配置、注册及证据合同修正夹具，不减少权限、身份和证据拒绝断言 |
| AgenticTask 签收适用性 | mw-pm-default-evidence-signoff | 原开发克隆保持 df8ecf6 + 未提交字节；独立审查克隆承载同样六个文件，54 项回归通过 |

## 验证与运行版本

- 当前根检查和定向回归的完整结果位于 `.agenticdoc/mw-remaining-closeout/evidence/`；以最终日志和命令退出码为准，早期红测保留。
- 冻结候选：`mw-remaining-closeout-20261124`；MW 扩展自检与 pi 编译通过。最终提交、激活及入口核对结果补记在本 key 的 `achieved.md`。
- 本轮为 Codex 自验；不将自验称为新的独立复核，也不将旧 SDD key 的阶段直接手改为 DONE。真实 UE/UBT、带费用模型请求及 RenderPerformance 试点不属于本次离线收尾。
- AgenticTask 新版本远端发布及八项目再次升级，遵守用户此前“发布前再确认”的约定；准备好的版本与当前已安装 df8ecf6 分开记录。

## 精确文件归属

本表对应 `evidence/scoped-files.json` 的冻结输入。生成的其他 dist、历史运行日志、临时目录及其他窗口台账不混入源码提交。

| 文件 | 原 key / 收尾 key |
| --- | --- |
| `AGENTS.md` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `biome.json` | mw-repo-check-baseline / mw-remaining-closeout |
| `packages/ai/CHANGELOG.md` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/README.md` | mw-repo-check-baseline / mw-remaining-closeout |
| `packages/ai/dist/providers/data/.manifest.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/amazon-bedrock.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/anthropic.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/azure-openai-responses.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/baseten.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/cerebras.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/cloudflare-ai-gateway.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/cloudflare-workers-ai.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/fireworks.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/github-copilot.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/google-vertex.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/google.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/groq.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/huggingface.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/kimi-coding.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/minimax-cn.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/minimax.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/mistral.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/moonshotai-cn.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/moonshotai.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/nvidia.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/openai.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/opencode-go.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/opencode.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/openrouter.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/qwen-token-plan-cn.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/qwen-token-plan.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/together.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/vercel-ai-gateway.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/xai.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/xiaomi-token-plan-ams.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/xiaomi-token-plan-cn.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/xiaomi-token-plan-sgp.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/xiaomi.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/zai-coding-cn.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/dist/providers/data/zai.json` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/model-data-check-snapshot.json` | mw-repo-check-baseline / mw-remaining-closeout |
| `packages/ai/package.json` | mw-repo-check-baseline / mw-remaining-closeout |
| `packages/ai/scripts/generate-models.ts` | mw-zai-glm54 / mw-zai-glm54-release |
| `packages/ai/scripts/restore-model-data-snapshot.mjs` | mw-repo-check-baseline / mw-remaining-closeout |
| `packages/coding-agent/CHANGELOG.md` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | mw-signoff-freeze-metadata / ue-frame-install-generate / mw-pi-version |
| `packages/coding-agent/test/extensions/agent-team-loop-codex-local.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/test/extensions/agent-team-loop-engine-policy.test.ts` | mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs |
| `packages/coding-agent/test/extensions/agent-team-loop-pm-state-sync.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/test/extensions/agent-team-loop-pm-state.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/test/extensions/agent-team-loop-trim.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/test/extensions/agent-team-loop-version.test.ts` | mw-runtime-version / mw-pi-version |
| `packages/coding-agent/test/extensions/file-evidence-cache.test.ts` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/coding-agent/test/extensions/golden/target-baseline/dual.json` | mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs |
| `packages/coding-agent/test/extensions/issue-command.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-lock-preflight-toctou.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-model.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-question-link-fix.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-root.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-store-review-fix.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/extensions/issue-store.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/decision-window-claim-contract.test.ts` | mw-window-claim-isolation |
| `packages/coding-agent/test/suite/dp-consolidation-materials.test.ts` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/coding-agent/test/suite/dp-consolidation-pm-followup.test.ts` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/coding-agent/test/suite/dp-consolidation-worker.test.ts` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/coding-agent/test/suite/material-validation-diagnostics.test.ts` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/coding-agent/test/suite/mw-duty-followup.test.ts` | mw-duty-followup |
| `packages/coding-agent/test/suite/mw-issue-feedback.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-inbox-fix.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-inbox-identity.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-inbox-timeline.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-project-identity.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-text-boundary.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-text-safety.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-viewport-fix.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/mw-issue-window.test.ts` | mw-issue-feedback |
| `packages/coding-agent/test/suite/pm-feedback-owner-binding.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/coding-agent/test/suite/worker-crosskey-readonly.test.ts` | mw-window-claim-isolation |
| `packages/coding-agent/test/suite/worker-dispatch-guard.test.ts` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/CHANGELOG.md` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/README.md` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/autopilot/contract_guard.py` | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff |
| `packages/multi-workers/decision_signoff_result.py` | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff |
| `packages/multi-workers/docs/dual-engine-policy.md` | mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs |
| `packages/multi-workers/docs/mw-window-duty.md` | mw-duty-followup |
| `packages/multi-workers/duty_followup.ts` | mw-duty-followup |
| `packages/multi-workers/fixtures/dp-continuity-offline-key-l2/README.md` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/fixtures/dp-continuity-offline-key-l2/fake-reviewer.cjs` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/fixtures/dp-continuity-offline-key-l2/fake-worker.cjs` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/fixtures/dp-continuity-offline-key-l2/review-card.md` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/fixtures/dp-continuity-offline-key-l2/worker-card.md` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/mw-version.cmd` | mw-runtime-version / mw-pi-version |
| `packages/multi-workers/mw.py` | mw-signoff-freeze-metadata / ue-frame-install-generate / mw-pi-version |
| `packages/multi-workers/mw_version.py` | mw-runtime-version / mw-pi-version |
| `packages/multi-workers/pm_duty.ts` | mw-duty-followup |
| `packages/multi-workers/templates/ue-continue-develop-frame/README.md` | ue-frame-install-generate |
| `packages/multi-workers/templates/ue-continue-develop-frame/install.py` | ue-frame-install-generate |
| `packages/multi-workers/templates/ue-continue-develop-frame/package/AGENTS.md` | ue-frame-install-generate |
| `packages/multi-workers/templates/ue-continue-develop-frame/tests/test_template.py` | ue-frame-install-generate |
| `packages/multi-workers/test/engine_policy_probe.py` | mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs |
| `packages/multi-workers/test/test_dual_engine_policy.py` | mw-dual-engine-policy / mw-dual-build-artifacts / mw-dual-ue-runtime-outputs |
| `packages/multi-workers/test_active_projection_workflows.py` | mw-window-claim-isolation |
| `packages/multi-workers/test_autopilot_contract_freeze.py` | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff |
| `packages/multi-workers/test_decide_signoff.py` | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff |
| `packages/multi-workers/test_decision_context_contract.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_decision_context_workbench.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_decision_dashboard_playground.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_dispatch_models.py` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/test_dp_consolidation_materials.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_dp_consolidation_registry.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_dp_continuity_offline_key_l2.py` | mw-dp-material-pipeline / mw-dp-consolidation |
| `packages/multi-workers/test_duty_followup.ts` | mw-duty-followup |
| `packages/multi-workers/test_mdc_e2e.py` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/test_mw_version.py` | mw-runtime-version / mw-pi-version |
| `packages/multi-workers/test_pm_default_evidence_signoff.py` | mw-signoff-freeze-metadata / mw-pm-default-evidence-signoff |
| `packages/multi-workers/test_prepared_fixture_support.py` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/test_serve_doctor.py` | mw-remaining-closeout（共享接线、原格式调整与回归收尾） |
| `packages/multi-workers/test_ue_frame_install.py` | ue-frame-install-generate |
| `packages/multi-workers/test_window_claim_final_acceptance.py` | mw-window-claim-isolation |
| `packages/multi-workers/test_window_claim_framework_boundaries.py` | mw-window-claim-isolation |
| `packages/multi-workers/test_window_claim_isolation.py` | mw-window-claim-isolation |
| `packages/multi-workers/test_window_claim_projection_boundaries.py` | mw-window-claim-isolation |
| `packages/multi-workers/test_window_claim_python_fixes.py` | mw-window-claim-isolation |
| `packages/multi-workers/window_duty_extension.ts` | mw-duty-followup |
| `scripts/check-ts-relative-imports.mjs` | mw-repo-check-baseline / mw-remaining-closeout |

AgenticTask 独立审查克隆：`.mw/agentictask-signoff-review`。其六个文件为 `scripts/`、`claude/scripts/`、`core/scripts/` 下各自的 `advance_phase.py` 与 `test_advance_phase.py`。
