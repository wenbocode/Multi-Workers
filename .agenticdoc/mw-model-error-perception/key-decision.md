# KDR: mw-model-error-perception

## R（需求）
- 技术栈: TypeScript（pi 扩展 worker-mode / pm 告警消费）；测试 vitest + faux provider
- 边界: 不改 packages/ai 重试策略；不做 provider/模型自动故障转移；不处理 PM 主窗口自身模型错误
- 关键约束: Extension API only（GC-1）；证据全落文件（GC-2）；延续既有看门狗契约（GC-3）；fail-fast 退出复用 timeoutExit 同步落盘模式
- 问题机理（已取证）: agent_settled 在 error turn 上照常触发且 worker-mode 不读 stopReason ⇒ error settle 推进 phase 机/伪成功；errorMessage 不落任何证据文件；error 自旋投毒 idle 看门狗
- 阈值草案 [AI 推荐，待用户确认]: 连续 2 个 error agent run 熔断（TRQ-1 证据修正，原草案 3；PI_WORKER_MODEL_ERR_MAX 可调，0=禁用）；同 key 连续 2 个 model-error 终结记 kind=model-error 告警（挂在 pm-orchestrator.ts:1603 既有通道）；conductor 侧 _l3_stream_aborted 泛化建议拆后续 key
- review_status: pending（spec 为 DRAFT，等用户确认后锁 AC）

## PM 直执裁决记录（2026-10-15 execute 阶段）

1. **D4 判据收敛采纳（t01b 报告）**：挂起型 idle 改判采用 `lastErrorInfo !== undefined || (!sawSuccessfulAssistant && agentRunStarted)`，非字面「零成功 assistant」。依据：agent-loop.ts:109/138 证 agent_start 先于 runLoop，真实首调挂起必置位；无事件休眠 worker 保持 exit 1（generic hang）；避免翻转 worker-idle-heartbeat VC-006 既有用例。
2. **checkpoint-wiring VC-007 基线适配（PM 直执，mini-spec 快速路径）**：他窗已提交的 4980da301（mw_run_detached，shell 角色唯一，刻意不入 TOOL_ALLOWLISTS 以保 T-17 parity lock）使 agent-team-loop-checkpoint-wiring.test.ts 2 用例失败。适配：新增 `expectedActiveTools(base)` 推导（worker_file→writeless，mw_run_detached→bash），冻结表与 toolsForType 断言未动。验证：10/10 passed + biome clean。改动仅 test/extensions/agent-team-loop-checkpoint-wiring.test.ts。
3. **t06 幻影 failed run**：中间版本测试漏 mock 所致，终态金丝雀阴性，已记 _pitfalls.md（wfg-i03 续篇），修复候选后续 key。

4. **autopilot-protocol 基线适配授权（PM 直执，QG Q7 留痕补记）**：与裁决 2 同一动作、同一根因（他窗 4980da301 mw_run_detached）；test/suite/autopilot-protocol.test.ts 新增 active() 推导（worker_file→writeless，mw_run_detached→bash），冻结表 PY_REGISTRY 逐字未动；验证 10/10 passed + biome clean。
5. **QG 处置（qg-review-mep-2，⚠️ 有条件通过 11✅/6⚠️/0❌）**：AC-002 已回填 D3 语义 + spec/design 顶部加修订索引（本次）；[FLOW] 包裹、FALLBACK_MODELS 注入无 worker 消费方、attempt=槽位序——三项已登记偏差接受不处理；phased 面（AC-003/AC-010）无用例与 AC-001 性能上界未实测记为验证欠债；mwoc-matrix-t07.test.ts 经 git diff 核实为他窗 csg key 实质内容变更 + 格式化混合，归属他窗、本 key 不回退不认领。
