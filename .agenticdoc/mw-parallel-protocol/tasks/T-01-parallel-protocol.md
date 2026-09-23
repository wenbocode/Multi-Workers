# T-01: PM 窗口常驻「并行优先协议」注入

> Key: mw-parallel-protocol
> 类型: coding（PM 本窗口直执——单点小改动，跨文件语义耦合在 pmActivate 注册序列中，不宜派 worker）
> 状态: done

## 目标

PM 模式注册 `before_agent_start`，把静态并行优先协议追加进每轮系统提示。

## 交付物

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
  - `PARALLEL_PROTOCOL_MARKER` / `PARALLEL_PROTOCOL` 常量（导出，供测试断言）
  - `pmActivate()` 内注册 `pi.on("before_agent_start", handler)`：追加式、标记判重幂等、空基串容错
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`
  - `pmActivate parallel protocol (mw-parallel-protocol)` 两个用例（PM 注入 + worker 不注入）
- `packages/coding-agent/CHANGELOG.md`（Unreleased / Added）

## AC 映射

- AC-001 → 用例 1（前缀保留 + 追加）
- AC-002 → 用例 1（四类动作文本断言）
- AC-003 → 用例 1（回喂自身输出 → undefined）
- AC-004 → 用例 1（`{}` → 纯协议文本）
- AC-005 → 用例 2（`workerModeActivate` 的 before_agent_start 不产协议）
- AC-006 → 证据账本（`npm run check` + 该测试文件 170 passed）

## 实施要点

- 只追加不替换：`base === "" ? PARALLEL_PROTOCOL : base + "\n\n" + PARALLEL_PROTOCOL`，链式系统提示的前序修改不被破坏。
- 静态文本（无时间戳/动态数字）：系统提示前缀确定性，不破坏 prompt cache。
- 不注入持久 message：避免每 run 往 session 累积 token。
- PM-only 结构性保证：`index.ts` 的 `PI_WORKER_TASK` if/else 分支，worker 窗口不会走到 `pmActivate`。

## 未做（范围内明确排除）

- 不改 `.pi/APPEND_SYSTEM.md` / `AGENTS.md`（项目侧可另加，与本 key 正交）。
- 不改 `core/pm-mind.md`、`core/workflows/*.md`（跨仓库 AgenticTask，另计）。
- 不加开关/配置。
