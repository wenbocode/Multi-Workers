# 调研证据（spec 阶段）：派工 role 不可达与模型覆盖逃逸

> key: mw-dispatch-role-escape / 2026-09-20 / 来源 = 本仓源码 + H:\git\E2Feature 实际产物

## R-1 触发事实（外部项目产物）

| 证据 | 值 | 出处 |
|------|-----|------|
| 配置 | `models: {coding/main/research: timi/deepseek-v4.1-flash, review: timi/gpt-5.6.sol}` | `H:\git\E2Feature\.mw\dispatch.yml`（145B，2026-09-20 17:01） |
| 窗口模型 | 空文件 | `H:\git\E2Feature\.mw\window-model` |
| 任务产物 | 14/14 worker task.md 带 `model: gpt-5.6-sol`；其中 `review-slicing-algorithm-spec/task.md` 为 `type: coding` | `H:\git\E2Feature\.agenticdoc\slicing-algorithm-spec\workers\*\task.md` |
| 结论 | 所有实现类任务跑在 review 档模型；配置的 coding 档从未生效 | 用户 2026-09-20 审计报告 |

## R-2 role 不可达：`type:` 由 cli 推导，pi 恒为 coding

```
packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:925   (dispatch_worker)
packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:1219  (/worker)
    const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:930,1237
    const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
```

role 映射在 Python 侧按 `type` 分发（`mw_common.py:135-146`）：

```
TASK_TYPE_TO_ROLE = {coding, phase-writer, repair, roadmap-writer -> coding;
                     review, verifier, reviewer -> review;
                     research -> research}
```

pi 任务永远只能命中 `coding` → `review`/`research` 配置档不可达。worker 工具白名单同样按 `type` 取
（`worker/worker-mode.ts:36-50`：coding 含 write/edit/bash，review/research 为只读集合），因此 pi 的
review 任务**同时**拿错模型档和错误的工具集。

## R-3 覆盖无痕、无校验

```
ui-bridge.ts:859   model 参数描述："Optional model override for this worker (e.g. 'claude-sonnet-4-5')."
ui-bridge.ts:930   model 直写 task.md 的 `model:` 行（解析链最高优先级）
ui-bridge.ts:942   结果文本 `(type: ${cli} ...)` —— 回显的是 cli，不是 type
```

- 无前缀/取值校验，无理由字段，无偏离回显。
- 解析链（`mw_common.py:280-305 resolve_dispatch_model`）：task.md `model:` → dispatch.yml role →
  window model → per-cli 默认。显式值“永不静默改写”，也永不要求说明。

## R-4 非法 id 不失败：pi 的 custom model id 兜底

```
packages/coding-agent/src/core/model-resolver.ts:174-190  buildFallbackModel(provider, modelId, availableModels)
    providerModels 非空时用 provider 默认模型为模板，{...baseModel, id: modelId, name: modelId}
packages/coding-agent/src/core/model-resolver.ts:590-598
    fallbackModel 命中 → 只返回 warning: `Model "<id>" not found for provider "<p>". Using custom model id.`
```

即：`--provider timi --model gpt-5.6.sol` 不会报错，会带着 `gpt-5.6.sol` 这个 id 发请求，warning 只落在
`worker.log`（serve 每会话截断的 `launcher.log` 之外，PM 通常看不到）。

id 真值表（`packages/ai/src/providers/data/timi.json`，经 `providers/timi.models.ts` 生成）含
`gpt-5.6-sol`（连字符），**不含** `gpt-5.6.sol`（点）。故 E2Feature 的配置值是错的，PM 手填的裸
`gpt-5.6-sol` 反而是对的。

## R-5 现有可用能力（复用点）

| 能力 | 位置 | 复用方式 |
|------|------|----------|
| `parseModelValue(value) -> {prefix, modelId}` | `shared/dispatch-models.ts:42` | prefix/model 拆分 |
| `PREFIX_TO_PROVIDER_ID` / `PROVIDER_ID_TO_PREFIX` | `shared/dispatch-models.ts:29-40` | prefix → pi provider id |
| `readMainModelConfig(cwd)` 严格手写解析 `models:` 块 | `shared/dispatch-models.ts:83` | 泛化为 `readRoleModel(cwd, role)`（bundle 保持无 yaml 依赖） |
| `ctx.modelRegistry.find(provider, id)` | `core/model-registry.ts:56`，已在 `applyMainModelConfig` 使用 | 派发期 id 校验 |
| `[launcher] <key>: model=... source=...` | `launcher.py:806` | 在其后追加 override 对比行 |
| task.md 字段读取方（两处正则） | `launcher.py:135` `^type:`/`^model:`；worker `parseTaskMd` `type:` | 新键命名必须不被这两处误读 |

## R-6 已确认的边界

- `/worker` 的参数解析在 `ui-bridge.ts:1180-1210`（`--model` / `--key` 循环），新增 `--type`/`--reason`
  与 `--model` 同级；`/mw model set` 是 Python 校验的薄封装（`ui-bridge.ts:1523-1580`），
  `ctx` 为 `ExtensionCommandContext`，不保证有 `modelRegistry` → 该处校验需可选化。
- 既有测试基线：`packages/coding-agent/test/extensions/agent-team-loop.test.ts` 中 dispatch_worker 用例
  使用 `fakeCmdCtx()`（无 `modelRegistry`），故校验函数必须容忍 registry 缺失，并单独导出以便直接单测。
- 无 yaml 依赖：`readMainModelConfig` 的注释明确「bundle 必须保持无 yaml 依赖」，新增 role 读取沿用该口径。
