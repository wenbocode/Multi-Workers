# 调研证据（design 阶段）：校验放置点与不可达 role 的修法选型

> key: mw-dispatch-role-escape / 2026-09-20

## R-1 放置点选型：模型 id 校验放哪里

| 候选 | 可行性 | 结论 |
|------|--------|------|
| Python launcher（spawn 时） | launcher 没有模型表：`packages/multi-workers/` 内无 provider data；timi 表在 `packages/ai/src/providers/data/timi.json`，跨包且安装形态下不保证存在 | **否**（要引入跨包耦合或新 artifact） |
| TS 派发时（`ctx.modelRegistry`） | 已在用：`shared/dispatch-models.ts#applyMainModelConfig` 用 `ctx.modelRegistry.find(provider, modelId)` 校验 `main` role；`ExtensionCommandContext extends ExtensionContext`（`core/extensions/types.ts:307,353`）故命令路径同样可用 | **是**（D-004/D-010） |
| 让 pi 侧把 custom-model-id warning 写进 trace | 需改 pi core 的 warning 出口或依赖 session 内部状态，落点不明 | 否（超出「不改 pi core」约束） |

补充：pi 对已知 provider + 未知 id 的兜底路径确认在 `core/model-resolver.ts:174-190`（`buildFallbackModel`）
与 `:590-598`（warning 文案），即不校验就会静默带错 id 发请求，故派发期拦截是本仓可用的最早确定性拦点。

## R-2 为什么「role 默认值不合法」要 fail-closed 而不是落穿

- `mw_common.resolve_dispatch_model`（`packages/multi-workers/mw_common.py:280-305`）当前语义：prefix
  **不兼容**（`model_value_compatible` 返回 False，含未知 prefix）→ 跳过该层落下一层。若沿用同语义
  处理「id 不存在」，E2Feature 的 `timi/gpt-5.6.sol` 会静默落到 window model —— 正是本 key 要消灭的
  「静默偏离策略」。
- 反向风险（坏配置锁死派发）由**显式 model 逃生口**消解：显式值走 task.md 层，role 默认值根本不参与解析。
- 该例外与 `mw-dispatch-models` 记录的「解析失败不阻断」不冲突：那条对应 unreadable/结构错/未知 role
  （parse 层），本 key 只动「parse 成功但语义无效」（`load_dispatch_config` 已保证结构合法）。

## R-3 `model-reason:` 键的安全性

既有读取方正则（不匹配 `model-reason:`）：

```
packages/multi-workers/launcher.py:135-150   _read_task_md_fields: r"^type:..." / r"^model:..."
packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:338-340  readModel: /^model:\s*(.+)$/im
packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:186-188  parseTaskMd: startsWith("type:")
```

三者都要求 `model` / `type` 后紧跟 `:`，`model-reason:` 均不命中 → 新键对既有解析零影响
（回归由 `test_dispatch_models.py` 既有 `_read_task_md_fields` 用例 + 新增 frontmatter 断言覆盖）。

## R-4 bundle 依赖约束

`shared/dispatch-models.ts:76-82` 注释明确：`readMainModelConfig` 手写解析是为了保持
「bundle 无 yaml 依赖」。故 role 读取复用同一手写解析器（D-009），不引入 `yaml` 包。

## R-5 测试基建可注入点

- TS：`test/extensions/agent-team-loop.test.ts#fakeCmdPi()`（tools/commands 收集）、`fakeCmdCtx()`
  （**无** `modelRegistry`）、`writePhaseDocs(root, key)`（满足 docs gate）。校验函数必须容忍 registry 缺失，
  并单独导出以便纯函数矩阵测试（VC-005）。
- TS 命令路径：`runMwModelCommand(ctx, projectDir, argsText, runner)` 的 `runner` 可注入
  （`ui-bridge.ts:1528`）→ 可在不触发 Python 的情况下断言「非法值不调 runner」（VC-008）。
- Python：`test_dispatch_models.py#_project(tmp_path, task_body=..., dispatch_yml=..., window_model=...)`
  已能构造 dispatch.yml + task.md 组合，launcher 观测行测试直接复用（VC-009），并已有
  `_TS_MIRROR` 双侧 parity 断言模式（`:129-145`）可扩展 role map。

## R-6 dist / 生效路径

`mw build --install` 重建扩展 bundle 并重装全局扩展（README「build」行；`mw-target-partition` 的
交付记录同样包含 dist 重建）。本 key 的改动在 TS 源码上，需在 EXECUTE 末段重建 dist 并用 tmux
冒烟验证（`./pi-test.sh` 或已安装 bundle 路径）——列入 plan 的 T-03。
