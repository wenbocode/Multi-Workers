# W-03 — TS 入口：mw_run_detached 工具 + /mw run-detached 子命令

- key: mw-console-storm-hardening · type: coding · 波次 1
- ac_refs: AC-008 · vc_refs: VC-008

## 上下文

goal.md（.agenticdoc/goal.md）GC-2「不修改 pi 核心：所有功能通过 Extension API 实现」。RQ-2 结论（evidence/research/design-ts-entry-surface-20261015.md）：形态 = both（工具 + 命令共用 `runDetachedMw()`），双激活路径注册先例 `registerRagTools`（pm-orchestrator.ts:1769 + worker-mode.ts:2773），worker 可见性经 `activeToolsForType`（worker-mode.ts:167-170），esbuild 入口图自动收编（mw.py:4642/4662）无需额外构建步骤。锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1769`、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2773`、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3440`（/mw 命令注册处）。

## 要求（契约 = design.md D-005，逐条实现）

1. **新文件 `shared/run-detached.ts`**：`runDetachedMw(opts)` ——spawn `python mw.py run-detached [--cwd D] [--run-dir D] [--timeout-min N] [--heartbeat-s S] -- <cmd...>`（mw.py 路径从扩展位置解析或经现有配置约定，读现有 mw-runner.ts 的 python 调用先例对齐），解析 CLI 4 行 stdout 返回 `{pid, marker, heartbeat, log}`；spawn 失败/解析失败返回结构化错误对象（fail-open，不 throw 穿透扩展）。类型导出 `RunDetachedHandle`。
2. **工具注册**：`mw_run_detached`，typebox schema `{cmd: string[]（minItems 1）, cwd?: string, run_dir?: string, timeout_min?: number, heartbeat_s?: number}`，`additionalProperties: false`；执行 = 调 `runDetachedMw()`；结果 = content 文本（4 字段摘要）+ `details{pid, marker, heartbeat, log}`。注册在双激活路径（照 registerRagTools 先例的调用点旁）。
3. **worker 门控**：该工具加入 `activeToolsForType` 仅 shell 角色；**不进** `shared/dispatch-models.ts` 的 `TOOL_ALLOWLISTS`（T-17 parity 锁，禁止改该表）。
4. **`/mw run-detached` 子命令**：ui-bridge.ts 现有 `/mw` 命令的参数分支（同 `/worker` 用法），人/PM 手动入口，同样走 `runDetachedMw()`；USAGE 文本更新。
5. **suite 测试**（新文件，faux provider，无真 CLI/网络）：断言双激活路径工具注册存在、schema 校验（additionalProperties 拒绝）、cmd/cwd 透传到 spawn 参数（捕获 spawn 调用）、shell-only 门控、`/mw run-detached` 分支存在。
6. 硬规则：erasable TS（无 enum/namespace/参数属性）；top-level import（禁 inline `await import()`）；不碰 pi 核心（src/core 等一律不写）；禁 PowerShell 改写源文件（P-001）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（仅注册点旁一小段）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（仅注册点旁一小段）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（仅 /mw 分支 + USAGE）
- `packages/coding-agent/test/extensions/`（新测试文件）

## 写入禁止面

- pi 核心（src/core 等）、`shared/dispatch-models.ts`（TOOL_ALLOWLISTS parity 锁）、`packages/multi-workers/**`、其他扩展文件大范围重构；禁止 git add/commit；禁止 `npm run build`（构建由 PM 统一触发）

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-run-detached.test.ts 2>&1 | Select-Object -Last 6
npx tsgo --noEmit 2>&1 | Select-Object -Last 3          # 0 错
npx biome check --error-on-warnings src/extensions/agent-team-loop 2>&1 | Select-Object -Last 3
```

（套件文件名以实际新建为准，输出须含通过计数。）

## 改动历史

- 2026-10-15 W-03 首派（波次 1；mw-worker-output-contract 已提交、树干净后解扣）。

## 交付格式

- 改动文件清单 + 每文件 diff 摘要 + 验收命令原始输出（测试计数行 / tsgo 尾 3 行 / biome 尾 3 行）+ 实现说明（与 D-005 契约逐条对照）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行，长输出落临时文件后只回读 tail/汇总。
