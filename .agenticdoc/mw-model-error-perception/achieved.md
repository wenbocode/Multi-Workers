# achieved.md — mw-model-error-perception

## 系统行为变化

1. **worker 模型错误感知（原问题：假 done）**：worker 遇到持续模型错误（HTTP 500/连接受限/流断开）时，此前 `agent_settled` 无条件触发、错误轮被稳定推进 phase、写假 "Phase N complete"、以 `done(0)` 终结、errorMessage 不落盘、错误自旋污染空闲钟。现在：error agent run（run 内 auto-retry 耗尽后）→ trace 追加 `[MODEL_ERR]`（[FLOW] 包裹，model/run/err 字段）→ 直接 `modelExhaustedExit`：exit 3 + `run.json model_exhausted: true` + output.md `## Exit Reason` 以 `model unavailable: tried=<链> last=<err>` 开头（含中间产物 Deliverables）；error settle 不推进 phase 机、不进 finishSuccess（AC-003 拦截保留）；error 边界事件不喂活动钟，`[IDLE_KILL]` 增加 `last_model_error=yes|no`。影响面：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`worker/output-writer.ts`（exitCode 3 渲染）。
2. **进程级重试 + 备用模型链（launcher）**：exit 3 → launcher 先按 `PI_WORKER_MODEL_ERR_MAX`（默认 2，0=直切备）对同模型进程重派（`[MODEL_RETRY] model=<m> attempt=<k>`，INDEX/TRIED 不变、新 run_id），预算耗尽 → 按 `.mw/dispatch.yml` 顶层 `fallback_models`（按任务类别，1..4 个 `prefix/model`）顺序切备（`[MODEL_FALLBACK] from= to= attempt=`，`--model` + `PI_WORKER_FALLBACK_MODELS/_INDEX/_TRIED` env 注入）；候选预校验失败 `[MODEL_FALLBACK-SKIP]`；链耗尽 reap 为 failed。全部以 trace.log 为事实源、重启安全、复用并发槽。挂起型 idle 击杀（无在飞工具 + lastModelError 或首调零成功 + agentRunStarted）同样 exit 3 进备用链；在飞工具挂死保持 exit 1。影响面：`packages/multi-workers/launcher.py`。
3. **配置层**：`fallback_models` 顶层 schema/校验（`mw_common.py`：格式/上限 4/`*_cli` 拒绝/读软失败）+ doctor 检查（格式→issue、路由/凭证缺失→suggestion）；`mw model set/clear` 改读改写保留非 `models` 顶层键（`mw.py` `_dispatch_extra_keys`）。
4. **PM 感知告警**：pm-orchestrator 双源识别（run.json `model_exhausted` ∨ Exit Reason 前缀），同 key 连续 K=2 → `kind=model-error` 感知告警（非 model-error 终态清零），不改变 autopilot 决策。影响面：`pm/pm-orchestrator.ts`。
5. **测试与文档**：新 TS 套件 13 用例（`test/suite/worker-model-error-perception.test.ts`）+ Python 70 用例（`test_mep_fallback_config.py`/`test_mep_launcher_redispatch.py`）；README 新增 fallback 节 + 4 env 契约；双包 CHANGELOG [Unreleased]；`evidence/quality-gate-report-20261015.md`。
6. **附带基线适配**：checkpoint-wiring VC-007 与 autopilot-protocol VC-023/GC-8 快照补 `mw_run_detached`（他窗 4980da301 引入的基线回归，冻结表未动）。

抖动保护层级（对用户问题的最终答案）：① run 内 auto-retry（3 次）→ ② 同模型进程重试（≤2）→ ③ 备用模型链 → ④ failed 熔断；run 内恢复（error 后 success）正常 settle 不 exit（AC-005）。

## 遗留

1. **print-mode 队列语义框架缺陷**（TRQ-2/D3 修订根因）：settle 期入队的 followUp 在 print mode 下无人消费（phased 机冻结同机理）——本 key 以进程级化绕开；框架级修复（print-mode drain 或 session 续跑 API）立新 key 候选。
2. **幻影 failed run（wfg-i03 续篇）**：worker 子进程继承 `PI_WORKER_TASK` + worker-mode 无活 run 防护 → 幻影失败行污染 widget；已记 `_pitfalls.md`，修复（active-run guard / spawn env 剥离）立新 key 候选。
3. **print-mode 阶段冻结缺陷**：同 1，未在本 key 修复（spec §0 明示 out of scope）。
4. **conductor `_l3_stream_aborted` 通用化**：用户已裁定后续 key。
5. **低危观察（接受不处理）**：launcher 预校验跳过槽位以 index+1 计 attempt/INDEX（配置槽位序 vs 已消费数，终止语义正确，仅审计呈现）；mw_common.py 3 字节 BOM 移除（验收门所需，保持现状）；`[MODEL_ERR]` 落盘为 `[FLOW]` 前缀（appendTrace 语义，测试已按 includes 适配）。
6. **运行时激活待用户执行**：`npm run build`（dist 重建）+ `/mw restart`——未执行前生产 worker 走旧 bundle，行为不变。
7. **dispatch 卡渲染器单反引号路径缺陷**：`## 写入允许面` 每个 bullet 只取第一个反引号路径，多路径 bullet 的后续路径掉出机器写面（T-07 受阻根因）；已在本 key 以 PM 直执绕过，修复立新 key 候选。
