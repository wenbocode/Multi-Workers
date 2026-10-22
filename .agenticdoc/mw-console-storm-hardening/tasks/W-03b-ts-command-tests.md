# W-03b — TS 入口(下):/mw run-detached 子命令 + suite 测试

- key: mw-console-storm-hardening · type: coding · 波次 2.5 下半（W-03a 已终态）
- ac_refs: AC-008 · vc_refs: VC-008
- timeout: 90

## 上下文

goal.md（.agenticdoc/goal.md）GC-2「不修改 pi 核心」；design.md D-005。W-03a 已落地：`shared/run-detached.ts`（`runDetachedMw(opts)` → `{ok:true,handle:{pid,marker,heartbeat,log}}` / `{ok:false,error}`、`registerRunDetachedTool`、`MW_RUN_DETACHED_TOOL` 常量、typebox schema）+ 双激活路径注册 + shell-only 门控。本卡只做命令入口与测试。**write-first**：锚点直奔下述行号；`/mw` 命令处理分支照同函数内既有子分支形态抄，20 次写工具调用内完成分支初版。

锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3440`（/mw 命令注册处）、`packages/coding-agent/src/extensions/agent-team-loop/shared/run-detached.ts:1`（W-03a 产物，导入 `runDetachedMw` 与 `MW_RUN_DETACHED_TOOL`）、`packages/coding-agent/test/extensions/agent-team-loop-vision-gate.test.ts:1`（faux provider suite 测试范式参照）

## 要求

1. **`/mw run-detached` 子命令**：ui-bridge.ts 的 `/mw` 处理函数加 `run-detached` 分支（参数 `--cwd/--run-dir/--timeout-min/--heartbeat-s` + `--` 后命令，解析照同命令既有参数分支先例），调 `runDetachedMw()`，输出 4 字段摘要（工具同款文案）；错误路径输出结构化错误不抛。USAGE 文本补 `run-detached`。
2. **suite 测试**（新文件 `packages/coding-agent/test/extensions/agent-team-loop-run-detached.test.ts`，faux provider，无真 CLI/网络）：
   - 双激活路径注册存在（PM 与 worker 激活各断言 `mw_run_detached` 注册；worker 侧断言 shell-only：非 shell 角色工具集不含 `MW_RUN_DETACHED_TOOL`）
   - schema 校验：`cmd` 空数组被拒、additionalProperties 拒未知键
   - 参数透传：cwd/run_dir/timeout_min/heartbeat_s → `runDetachedMw` 收到的 argv 正确（monkeypatch spawn 或注入 seam，断言拼出的 python 命令含对应旗标与 `--` 后原样 argv）
   - `/mw run-detached` 分支存在且走 `runDetachedMw`（同款 seam）
   - 输出 `[VERIFY] VC-008: ...` 行（`process.stdout.write`）
3. 硬规则：erasable TS、top-level import、不碰 pi 核心、`shared/dispatch-models.ts`、`shared/run-detached.ts`（只读 import）、`pm/pm-orchestrator.ts`、`worker/worker-mode.ts`；禁 PowerShell 改写源文件；禁 git add/commit；禁 `npm run build`。允许 `npm run build` 的替代验证：不跑，以 tsgo 为准（构建由 PM 统一触发）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（仅 /mw 分支 + USAGE）
- `packages/coding-agent/test/extensions/agent-team-loop-run-detached.test.ts`（新建）

## 写入禁止面

- pi 核心、`shared/dispatch-models.ts`、`shared/run-detached.ts`、两注册点文件、`packages/multi-workers/**`；禁止 git add/commit

## 验收命令

```bash
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-run-detached.test.ts 2>&1 | Select-Object -Last 8
npx tsgo --noEmit 2>&1 | Select-Object -Last 3
npx biome check --error-on-warnings src/extensions/agent-team-loop/pm/ui-bridge.ts test/extensions/agent-team-loop-run-detached.test.ts 2>&1 | Select-Object -Last 3
```

期望：新套件全绿 + tsgo 0 错 + biome 干净。对照 Windows 基线（既有环境失败不追）。

## 改动历史

- 2026-10-15 W-03b 首派（W-03 分拆下半；上半 W-03a 已终态）。

## 交付格式

- ui-bridge diff 摘要 + 测试文件全文要点 + 验收原始输出（≤8 行/命令）+ `[VERIFY] VC-008` 行。
- 输出卫生（硬性）：每条命令 stdout ≤30 行。
