# W-03a — TS 入口(上):runDetachedMw 共用模块 + 工具双激活注册

- key: mw-console-storm-hardening · type: coding · 波次 2.5（W-03 首派 wall timeout 后分拆：上/下半）
- ac_refs: AC-008 · vc_refs: VC-008(工具半)
- timeout: 120

## 上下文

goal.md（.agenticdoc/goal.md）GC-2「不修改 pi 核心：所有功能通过 Extension API 实现」；design.md D-005（契约已冻结，无需再论证形态）。**前次失败教训（必须遵守）**：W-03 首派 60min 读 361 次、0 写入——本卡要求 **write-first**：前 10 次写工具调用内必须已创建 `shared/run-detached.ts` 初版（哪怕只含类型与函数骨架），后续边写边对照；单文件研读 ≤3 遍，锚点直奔下述行号，禁止全局漫游 grep。

已研读结论（直接引用，无需重验，来源 evidence/research/design-ts-entry-surface-20261015.md）：
- 双激活路径注册先例 = `registerRagTools` 的两次调用：`pm/pm-orchestrator.ts:1769` 旁与 `worker/worker-mode.ts:2773` 旁
- worker 可见性门控 = `activeToolsForType`（`worker/worker-mode.ts:167-170`），**仅 shell 角色激活**；**不进** `shared/dispatch-models.ts` 的 TOOL_ALLOWLISTS（parity 锁，禁改）
- 工具注册写法参照同文件既有 registerTool 调用（RQ-2 清单已列 14 处，就近照抄一个 typebox 工具的完整形态）
- python 调用先例 = `shared/mw-runner.ts`（spawn python 的参数/解析风格）

锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1769`、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2773`、`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:167`、`packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:1`

## 要求（契约 = design.md D-005，工具半）

1. **新文件 `shared/run-detached.ts`**：`runDetachedMw(opts)` ——spawn `python mw.py run-detached [--cwd D] [--run-dir D] [--timeout-min N] [--heartbeat-s S] -- <cmd...>`（mw.py 定位与 python 解析照抄 mw-runner.ts 先例），解析 CLI 恰 4 行 stdout（`[mw run-detached] pid=<n>` / `marker=` / `heartbeat=` / `log=`）返回 `{pid, marker, heartbeat, log}`（导出类型 `RunDetachedHandle`）；spawn 失败/解析失败返回结构化错误对象（fail-open，不 throw 穿透扩展）。
2. **工具注册**：`mw_run_detached`，typebox schema `{cmd: string[]（minItems 1）, cwd?: string, run_dir?: string, timeout_min?: number, heartbeat_s?: number}`，`additionalProperties: false`；执行调 `runDetachedMw()`；结果 content 文本（4 字段摘要）+ `details{pid, marker, heartbeat, log}`。
3. **双激活路径注册**（照 registerRagTools 两调用点先例）+ **worker 门控**：`activeToolsForType` 仅 shell 角色。
4. 硬规则：erasable TS、top-level import、不碰 pi 核心；**不做** /mw 子命令、**不做** suite 测试（W-03b 领地）；禁 PowerShell 改写源文件。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（仅注册点旁一小段）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（仅注册点旁一小段 + activeToolsForType 门控行）

## 写入禁止面

- pi 核心、`shared/dispatch-models.ts`、`pm/ui-bridge.ts`（W-03b 领地）、`packages/multi-workers/**`、测试文件；禁止 git add/commit；禁止 `npm run build`

## 验收命令

```bash
cd packages/coding-agent
npx tsgo --noEmit 2>&1 | Select-Object -Last 3          # 0 错（新文件与两注册点无类型错）
npx biome check --error-on-warnings src/extensions/agent-team-loop/shared/run-detached.ts src/extensions/agent-team-loop/pm/pm-orchestrator.ts src/extensions/agent-team-loop/worker/worker-mode.ts 2>&1 | Select-Object -Last 3
```

（suite 测试由 W-03b 补——本卡验收 = 类型/biome 干净 + 注册代码在场。）

## 改动历史

- 2026-10-15 W-03 首派（csg-w03-ts-entry）wall timeout 60min/361reads/0writes，分拆为 W-03a/W-03b。
- 2026-10-15 W-03a 重派（本卡，write-first 硬约束 + 双倍预算）。

## 交付格式

- 三文件 diff 摘要 + 验收命令原始输出（tsgo/biome 尾 3 行）+ 与 D-005 契约对照。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
