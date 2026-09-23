# Task T-2: pi 窗口 `/mw rag` 薄封装

## 元信息
- Stage: 2
- 依赖: 无（可与 T-1 并行；**与 T-3 串行**——都改 `pm/ui-bridge.ts`）
- 风险: 低-中（新增窗口命令；必须保持 Python 为解析/校验唯一源）
- Agent: coding worker
- ac_refs: [AC-303, AC-305]
- vc_refs: [VC-306, VC-307, VC-308, VC-311]

## 背景（实测）

- `/mw` 注册在 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（`registerCommand("mw", …)`），
  现有子命令 `build/init/doctor/update/status/start/stop/restart/target/partition/model/ack`，**无 `rag`**。
- 薄封装先例：`shared/mw-runner.ts` 的 `runMwCli(sub, projectDir, args)` 会追加 `--project=<dir>`，把 stdout+stderr 合并，
  非 0 一律折成 `{ok:false,error}` → **丢掉 0/1/2 区分**。而 `mw rag audit` 的 exit 1 是「有 findings」（预期内 warning），
  exit 2 才是用法/配置错误。
- `mw.py` 的 RAG 子命令：`init / list / probe / sync / audit`，共同必填 `--project`。

## 交付物

1. `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`
   - 新增内部 `runMwCliRaw(sub, projectDir, args, timeoutMs?) → { code: number, output: string, spawnError?: string }`（沿用既有 spawn 方式，追加 `--project=<dir>`，合并 stdout+stderr）；
   - 既有 `runMwCli` 改为基于它的薄包装，**行为与返回类型不变**（target/partition/model 调用方零变化）；
   - 新增导出 `RAG_SUBCOMMANDS = ["list", "probe", "audit", "sync", "init"] as const` 与
     `ragMw(projectDir: string, args: string[]): { ok: boolean; code: number; output: string }`；
   - `findMwPy()` 失败时返回 `spawnError`，由调用方转成错误通知（含 `MW_PY` 提示）。
2. `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
   - 导出纯函数 `parseRagArgs(raw: string): { sub: string; rest: string[] } | { usage: string }`：
     空/未知 sub → `usage`（文本里必须列出 5 个子命令名），**不得调用 CLI**；否则 `{sub, rest}`（rest 原样透传）；
   - 导出纯函数 `formatRagOutput(output: string, code: number): { text: string; level: "info" | "warning" | "error" }`：
     `0→info`、`1→warning`、`2→error`；超过 30 行截断并在末尾附完整命令提示（形如
     ``完整输出：python mw.py rag <sub> --project <dir>``——注意 sub 需由调用方传入或在文本里体现，实现自定但要可测）；
   - `/mw` 分支新增 `sub === "rag"`：解析 → 未知则提示 usage（不调 CLI）→ 否则 `ragMw(projectDir, ["<sub>", ...rest])` →
     `formatRagOutput` → `ctx.ui.notify(text, level)`；**不解析输出内容、不做参数语义校验**；
   - `registerCommand("mw", …)` 的 `description` 加入 `rag`。

## 测试（追加到 `packages/coding-agent/test/suite/rag-window.test.ts`，不要动 T-1 写的用例）

- VC-306：`parseRagArgs("list")` → `{sub:"list", rest:[]}`；`parseRagArgs("audit --key K")` → `{sub:"audit", rest:["--key","K"]}`；`parseRagArgs("bogus")` → usage 且文本含 5 个子命令名。
- VC-307：未知/空 sub **不调用** `mw.py`——用可注入的 runner 或断言 `parseRagArgs` 返回 usage 且 handler 分支在调用前返回（可把分支判断抽成纯函数 `ragDispatch(raw)` 便于测试，实现自定）。
- VC-308：`formatRagOutput` 的 code→level 映射（0/1/2）；>30 行输入被截断且文本含完整命令提示。
- VC-311：`/mw` 的 description 文本含 `rag`（把 description 抽成导出常量以便断言）。

## 约束

- 只改 `shared/mw-runner.ts`、`pm/ui-bridge.ts`、`test/suite/rag-window.test.ts`；不改 `rag/*.ts`（T-1 的领域）、
  `core/**`、`mw.py`/`mw_common.py`、fixture/golden、`dist/**`。
- TS 只用可擦除语法；无 `any`；无 inline `import()`；`[VERIFY]` 用 `process.stdout.write`。
- 不 commit。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts
cd H:/git/Multi-Workers && npm run check
```

## 报告要求

最终消息给出：改动文件、测试计数、`[VERIFY]` 行原文、`parseRagArgs` 三例实测返回值、`formatRagOutput` 三档 level 实测值、偏离与未覆盖项。
