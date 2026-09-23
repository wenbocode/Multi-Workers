# Achieved: mw-provider-routing

## 系统行为变化
- 新增功能：`zai/` 模型前缀路由（task.md `model: zai/glm-5.3`、`/worker pi --model zai/glm-5.3`、`dispatch_worker(model="zai/glm-5.3")`）解析为 pi 原生 `zai-coding-cn` provider——worker 进程直连 `open.bigmodel.cn`，不经 mw proxy。
- 新增功能：providers.json 声明 `zai-coding-cn` 无 port 路由 + 凭证链（env `ZAI_CODING_CN_API_KEY` → auth.json `zai-coding-cn.key` 双源）；`mw doctor` / serve 预检自动列出该路由可用性。
- 派发语义：zai-coding-cn 无默认模型（缺 `--model` 即 RuntimeError 要求显式指定）；不进默认/回退链——不指定 provider/model 时仍走 timi 默认（glm-5.3）；zai 家族固定 zai-coding-cn，裸 `zai` 国际端点不引入。
- 凭证隔离：zai worker env 仅含 `ZAI_CODING_CN_API_KEY` + `PI_WORKER_TASK`，其他 provider 凭证（ANTHROPIC/DEEPSEEK/TIMI）全部剥离，无任何 localhost base_url。
- 附属修复：launcher 派发日志行 `flush=True`（stdout 重定向块缓冲导致 e2e 期间不可见）。
- 影响面：多 provider 并行调度能力——PM 可显式派发 glm-5.3 worker，摆脱单一 timi 路由单点依赖；timi/anthropic/deepseek/openai-codex 现行路径零触碰（D-001 裁定，diff 验证）。

## 关键决策
- D-001 方案 C（第 5 个硬编码直连分支）— 否决 A（pi_providers 数据驱动泛化，回归面大，拆后续 key）/ B（无 port 启发式，deepseek 键双重身份不可行）：LLM 调用链是框架命脉，风险最小化。
- D-002 zai-coding-cn + prefix `zai` — 否决裸 `zai` 双路由：消除 glm-* 裸模型 ID 重名歧义（用户裁定）。
- D-003 派发入口零改动复用 prefix 机制 — 否决新增 `--provider` 旗标：入口已完备，避免第二条指定路径。
- D-004 无 port 语义确认现状即用（泛化推迟）— 否决本 key 顺手泛化：与 D-001 风险裁定冲突，README Backlog 登记。

## 触达面
- `packages/multi-workers/providers.json`（credentials + providers 段 zai-coding-cn 条目）
- `packages/multi-workers/mw_common.py`（`MODEL_PREFIX_TO_PI_PROVIDER` + `"zai"`；`_DEFAULT_CONFIG` 同步条目——注意：此部分改动被 mw-partition-parent-extended 键的提交 2b5f259e2 携带入库，本键主提交 a395b0af2 无 mw_common diff，归属混杂留痕质检报告 N2）
- `packages/multi-workers/launcher.py`（`_build_env` pi+zai-coding-cn 分支；`_build_command` 直连元组 + zai-coding-cn；docstring；dispatch 日志 flush）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts`（`PROVIDER_ID_TO_PREFIX` + `"zai-coding-cn": "zai"`）+ bundle/dist 重建
- 测试：`test_launcher.py`（TestPiZaiRouting 8 用例）、`test_common.py`（precheck 翻转 + file 源）、`test_serve_doctor.py`（VC-008）、`test_dispatch_models.py`（parity 锁）、`test_e2e_real.py`（TestRealZaiDispatch）、`test/suite/../agent-team-loop.test.ts`（TS parity）
- 提交：a395b0af2（主）+ 57ca0e166（models.dev kimi 改名跟进，测试模型 id 刷新）

## 遗留
- `docs/zai_guider.md` 含明文 API key，保持 untracked（硬性要求满足）；「落地后脱敏」为建议项，后续清理跟进（质检报告 N3）。
- pi_providers 数据驱动泛化（消灭硬编码分支）拆后续 key，README Backlog 已登记。
- `mw serve` 重启后 Py 侧变更才在常驻进程生效（JS bundle 对新 spawn worker 即时生效）——与 mw-partition-parent-extended 遗留同源，用户择机重启。
- AC-007 括注「deselect 维持 8」→ 实际 9（本键新增 1 条 e2e_real 用例所致，design VC-007 已按 9 定稿，不变量 0 failed 成立；质检报告 N1）。

## 沉淀
- Pattern：直连 provider 接入五步式（providers.json 凭证链 + 无 port 路由 → prefix 双侧 map → `_build_env` 照 timi 模式分支 → `_build_command` 直连元组 → e2e_real 真实往返冒烟）——下一个直连 provider 可复制；硬编码分支到第 6 个时触发 pi_providers 泛化 key。
- 记忆更新：已完成（2026-09-20，用户确认）——首次创建 `.agenticdoc/_arch_snapshot.md`（架构快照 + 可复用资产清单，含本 key 五步式 Pattern 与 §1.6 路由现状）。
