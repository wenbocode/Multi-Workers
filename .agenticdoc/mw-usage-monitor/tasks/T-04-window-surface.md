# T-04: `/mw stats` 窗口面（mw-runner 包装 + ui-bridge 分支 + vitest）

type: coding
phase: execute
key: mw-usage-monitor
覆盖 AC: AC-006
依据: `.agenticdoc/mw-usage-monitor/design.md` §3.4/§8；`evidence/research/spec-rq4-surface-storage-20261019.md`（§1/§6）

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（agent-team-loop 扩展：PM 模式 + Worker 模式；不修改 pi 核心）。
- 已核实起点（自行复核）：
  - `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3676` `registerMwCommands` →
    `:3684 pi.registerCommand("mw", ...)`；**if-链分发**，首 token 决定子命令（:3687-3688）；
    参数用 `trimmed.slice(sub.length).trim()` 原样下传（如 `:3813` 的 `model`）。
  - `:3514` `MW_COMMAND_DESCRIPTION`（命令描述文本）；`:3859` 附近的 usage 尾行（可发现性文案）。
  - stdout/stderr 在 `runMwCliRaw`（`shared/mw-runner.ts:508-528`）合并为一段文本，统一
    `ctx.ui.notify(text, level)` 回显（info/warning/error），无面板。
  - 现成 `/mw model show` 全链是最佳可复制模板（ui-bridge 包装函数 + mw-runner 包装）。
  - 测试入口先例：`packages/coding-agent/test/suite/rag-window.test.ts:129-237`（纯 parse/format + 注入 runner
    + 断言 `MW_COMMAND_DESCRIPTION` 含子命令）、`test/extensions/agent-team-loop.test.ts:3030,4965-5216`
    （fake pi 注册 + `runMwModelCommand` 注入 runner）。
- 依赖：T-03 已交付 `mw stats`（`packages/multi-workers/mw.py`）；本任务只加转发，**不改 mw.py**。

## 要求

1. `shared/mw-runner.ts`：新增 `statsMw(projectDir: string, extraArgs: string[]): Promise<string>`，
   走 `runMwCliRaw(["stats", ...extraArgs], projectDir)`（与既有包装同形态；`--project` 由 `runMwCliRaw` 追加）。
2. `pm/ui-bridge.ts`：新增 `runMwStatsCommand(ctx, args)`：把 `args` 拆分后透传（不解析、不改写），
   成功 `ctx.ui.notify(text, "info")`，失败 `ctx.ui.notify(text, "error")` 且**不吞 stderr**。
3. `registerMwCommands` 的 if-链加 `stats` 分支（与 `model`/`doctor` 同级），并更新
   `MW_COMMAND_DESCRIPTION`（:3514）与 usage 尾行（:3859）各加 `stats`。
4. 新增测试 `packages/coding-agent/test/suite/mw-stats-surface.test.ts`：注入 fake runner，
   断言 (a) `/mw stats` 转发 argv 含 `stats` 且 `--project` 被追加一次；(b) 带参 `--since 24h --source pm` 原样透传；
   (c) runner 抛错时 notify level 为 error 且文本含原始 stderr；(d) `MW_COMMAND_DESCRIPTION` 含 `stats`。
5. 不改 pi 核心、不改 mw.py、不改 usage.py、不新增依赖、不引入内联 `import()`/动态类型导入。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/test/suite/mw-stats-surface.test.ts`（新建）

## 并发警告（必读）

上述两文件当前带有**其它会话的未提交改动**（`git diff --stat`：`ui-bridge.ts` +123 行，最后一块 hunk 在
`~3096` 的 `registerWorkerCommands` 区域；`mw-runner.ts` 当前干净）。因此：
- 只在 `registerMwCommands`（~3676）、`MW_COMMAND_DESCRIPTION`（~3514）与 `runMwCliRaw` 调用层锚定插入；
- **禁止**重写整文件、禁止格式化整文件；禁止 `git checkout|restore|stash|reset`、禁止 `git add`；
- 若锚点文本因其它会话改动而找不到，**停下并在 `output.md` 报告**（不要猜位置、不要改动别处）。

## 写入禁止面

- `packages/multi-workers/**`（属 T-01/T-02/T-03）
- 其它扩展文件、`packages/coding-agent/src/**` 中除上述两文件外的任何位置
- 其它 key 目录、`.mw/**`

## 验收命令

```powershell
cd H:\git\Multi-Workers\packages\coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mw-stats-surface.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts   # 相邻用例零回归
cd H:\git\Multi-Workers
npm run check
```

## 改动历史

（首次改动，填写：改了两文件哪几处、分支插在哪个子命令之后、被否决的替代方案（如"新建独立 `/stats`
命令"为何不选）。）
