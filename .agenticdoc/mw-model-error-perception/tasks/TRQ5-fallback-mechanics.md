# TRQ-5: 备用模型热切换机制（design 前置调研）

type: research

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（LLM 代理 + 任务调度；按任务类型工具白名单；worker 进程级隔离）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md` AC-008/009——按任务类别配置 `fallback_models` 数组，主模型连续 N=2 error run 后 `pi.setModel` 热切换并重置计数重发当前 prompt；全部耗尽才熔断。
- 已知锚点（须核验）：扩展 API `setModel(model): Promise<boolean>`（`packages/coding-agent/src/core/extensions/types.ts`，handler 实现 `agent-session.ts:2403`，无凭证返回 false）；launcher 组装命令 `["pi","--provider",provider,"--model",model,"-p",starter]`（`packages/multi-workers/launcher.py:1372-1388`）。

## 要求

1. 模型解析路径：worker-mode 扩展内如何把模型 id（如 `timi/glm-5.3`、provider+model 二元组）解析为 `Model<any>` 实例（model-registry / models-store / getScopedModels / ctx 可用面）；`pi.setModel` 对未配置凭证/不存在模型的确切行为（false 之外的 throw 路径）。
2. setModel 副作用面：ModelSelectEvent 发射、session 持久化（model change entry）、thinking level clamp（agent-session.ts:1586-1600）、切换后下一次 prompt 的事件序列（message_start 的 model 字段等）；切换必须发生在两个 run 之间是否充分（本设计如此）。
3. 配置与注入链：`.mw/dispatch.yml` 角色/任务类型配置结构（Python resolveDefaults：`packages/multi-workers/mw_common.py` / `mw.py` 相关段）、任务卡 `model:` 头与 dispatch 参数对主模型的优先级（mw-dispatch-role-escape 的 model 校验）、launcher._build_env 注入点（launcher.py:280-368）——给出 `fallback_models` 键的落点与 `PI_WORKER_FALLBACK_MODELS` 注入格式建议（逗号分隔 provider/model？）。
4. worker 启动时如何知道当前主模型（env/flag 回读路径），以及任务卡 `model:` 覆盖时 fallback 数组是否仍然适用。
5. 结论→决策映射：design 的切换状态机（per-model 计数、切换点、耗尽判定）应基于哪些 API 事实；配置 schema 与注入格式建议。

## 写入允许面

- 仅允许写：`.agenticdoc/mw-model-error-perception/evidence/research/design-fallback-mechanics-2026-10-15.md`

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-model-error-perception/evidence/research/design-fallback-mechanics-2026-10-15.md`（只写此一个文件）
- 结构：调研方法与出处（文件:行号）→ 五问逐一事实 → 结论→决策映射
