# FIX-Q：`/mw decide sign` —— TUI 内确认对话框签收（用户裁定 B）

- type: coding
- owner key: mw-decision-substitution

## 上下文

用户 2026-10-21 裁定：签收入口要进 `/mw`，采用方案 **(B)**——`/mw decide sign` 先展示摘要，
`ctx.ui.confirm` 弹确认框，人在 TUI 里点确认后才写；写入时 Python 侧接受一个显式的
`--human-confirmed` 豁免 flag。护栏语义从"agent 不可能签收"降级为"要故意伪造 flag 才能签收，
且档案留痕"，用户已知悉并接受。

事实依据：

- `/mw` dispatcher 在 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4096`，子命令白名单写死；
  尾部 usage 行在 `:4280` 附近。
- 已有同类薄封装范式：`runMwModelCommand`（`ui-bridge.ts:3811`）、`runMwRagCommand`，以及 `shared/mw-runner.ts:549` 的
  `modelMw`（`runMwCli("model", ...)`）。
- 测试范式：`packages/coding-agent/test/suite/rag-window.test.ts`（`parseRagArgs` 纯函数 + 假 ctx + 计数 stub runner）。
- `ExtensionCommandContext` 有 `ui.confirm(title, message, opts?): Promise<boolean>` 与 `hasUI`
  （`packages/coding-agent/src/core/extensions/types.ts:139`、`:538`）。
- Python 侧护栏：`mw.py` 的 `_DP_AGENT_ENV_VARS = decide_signoff.AGENT_SESSION_ENV_VARS`（`mw.py:1503`），
  `decide_signoff.write_signoff` 命中即拒。
- 本 key 已有一条真 jev 决策行（`decisions.jsonl` seq 25），`mw decide sign --project .agenticdoc/mw-decision-substitution`
  预览显示 `verdict continue: ok`。

## 要求

### 1. Python：`--human-confirmed` 豁免（`packages/multi-workers/mw.py`）

- `mw decide sign` 新增 `--human-confirmed`（store_true，help 写明：仅由 `/mw decide sign` 的确认对话框设置；
  它是 tamper-evidence 不是 tamper-proof）。
- 无该 flag 且命中 agent 会话 → 保持现状：exit 2、消息 `refusing inside an agent session …`、零写入。
- 带该 flag → 允许写入，**且**把来源记进产物：`render()` 增加一行 `signed_via: tui`；不带 flag 写 `signed_via: cli`。
  档案行的 `by` 词表不变（仍 `signoff:<conclusion>`）。
- `decide_signoff.render(...)` 增加可选参数 `signed_via: str = "cli"`（其它调用点默认不变）。

### 2. TS：`/mw decide` 子命令

- `shared/mw-runner.ts` 新增 `decideMw(projectDir, args): MwCliResult`（`runMwCli("decide", projectDir, args)`）。
- `pm/ui-bridge.ts` 新增纯函数 `parseDecideArgs(argsText)`：
  - `""` / `"show"` → `{action:"show"}`
  - `sign <continue|narrow|revoke> [--reason <text>] [--allow-empty] [--key <k>]` → 对应字段；
    未知子命令/缺 conclusion/结论值非法/多余位置参数 → `{action:"usage", error}`。
- 新增 `runMwDecideCommand(ctx, projectDir, argsText, deps?)`，`deps = {runner?: (projectDir, args) => MwCliResult, watchKey?: () => string | undefined}`：
  1. `ctx.hasUI !== true` → notify warning「`/mw decide` 需要交互 TUI（headless/-p/rpc 一律拒）」并 return；
  2. `show` → 调 `runner(projectDir, ["sign", "--key", key, "--json"])`（**preview，不写**），把 facts 渲染成多行 notify：
     `counted_rows / available / acted / escalated`、`engines:` 直方图、每条 verdict（continue/narrow/revoke）、
     `rows_sha256` 前 12 位、`p0-open`；JSON 解析失败 → error notify 原文尾部；
  3. `sign` → 先跑同一条 preview；若 `facts` 的该 conclusion verdict 不通过 → error notify（列出 problems）、**不弹确认框**；
     通过则 `await ctx.ui.confirm("确认签收 " + key, <摘要一行 + rows_sha256 前 12 位>)`；
     用户取消 → info notify「cancelled, nothing written」；
     确认 → `runner(projectDir, ["sign", "--key", key, "--conclusion", c, "--human-confirmed", ...(reason ? ["--reason", reason] : []), ...(allowEmpty ? ["--allow-empty"] : [])])`
     → 成功 notify 文件路径 + 提示 `advance_phase.py` 可推进；失败 error notify 原文。
  4. key 解析：`--key` > `deps.watchKey()` > usage 错误「无法确定 key，请给 --key」。
- dispatcher 增加 `if (sub === "decide") { await runMwDecideCommand(ctx, projectDir, trimmed.slice(sub.length).trim(), { watchKey: () => watch.key }); return; }`，
  并把 `decide show|sign <continue|narrow|revoke> [--reason] [--allow-empty] [--key]` 加进尾部 usage 文案。

### 3. 测试

- Python（`test_decide_signoff.py` 追加）：带 `--human-confirmed` 在 agent 会话内**能**写且产物含 `signed_via: tui`；
  不带则 exit 2 且零写入、消息含 `refusing inside an agent session`；`render` 默认 `signed_via: cli`；门禁解析不受新行影响。
- TS（新建 `packages/coding-agent/test/suite/decide-command.test.ts`）：
  1. `parseDecideArgs` 六例（空/show/sign 全参/sign 缺结论/非法结论/未知子命令）；
  2. `hasUI:false` → 无 runner 调用、notify warning；
  3. `show` → runner argv `["sign","--key","k","--json"]`，notify 含 `counted_rows` 与 `engines`；
  4. `sign` + preview verdict 不通过（preview JSON 里 problems 非空）→ **不调用 confirm**、无写入 argv；
  5. `sign` + 确认取消 → 无写入 argv、notify `cancelled`；
  6. `sign` + 确认 → 写入 argv 精确等于 `["sign","--key","k","--conclusion","continue","--human-confirmed"]`（带 reason/allowEmpty 的变体另测）；
  7. 无 `--key` 且 `watchKey()` 返回 undefined → usage 错误。
- 全程 hermetic：`runner` 是 stub，不 spawn、不联网。

### 4. 文档

- `packages/multi-workers/README.md` decide 小节：加 `/mw decide show|sign` 用法与 `--human-confirmed` 的定位说明。
- `docs/decision-substitution.md` §5.3：说明 TUI 入口、确认框、豁免 flag 的安全边界（tamper-evidence）。
- `packages/multi-workers/CHANGELOG.md` + `packages/coding-agent/CHANGELOG.md` 的 `[Unreleased]` 各加一条（英文，指向 FIX-Q）。

## 验收命令

```bash
cd packages/multi-workers
python -m pytest -q test_decide_signoff.py test_decide_cli.py
cd ../../packages/coding-agent
npx vitest --run test/suite/decide-command.test.ts
npx tsgo --noEmit
npx biome check src/extensions/agent-team-loop/pm/ui-bridge.ts src/extensions/agent-team-loop/shared/mw-runner.ts test/suite/decide-command.test.ts
```

（`tsgo` 全仓 rc=0 即可；biome 只查本人文件。）

## 写入允许面

- `packages/multi-workers/mw.py`、`packages/multi-workers/decide_signoff.py`
- `packages/multi-workers/test_decide_signoff.py`、`packages/multi-workers/test_decide_cli.py`
- `packages/multi-workers/README.md`、`packages/multi-workers/CHANGELOG.md`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`
- `packages/coding-agent/test/suite/decide-command.test.ts`（新建）
- `packages/coding-agent/CHANGELOG.md`
- `docs/decision-substitution.md`

## 写入禁止面

- `packages/multi-workers/decision.py`、`decision_backends.py`、`decision_points.py`、`decide_archive.py`
- 既有 `packages/multi-workers/test_decide_*.py`（`test_decide_signoff.py` / `test_decide_cli.py` 除外）
- `packages/ai/**`、`packages/agent/**`
- `.agenticdoc/**`、`.agents/**`、`.claude/**`（门禁脚本本卡不动）
- 禁止 `git` 写操作、`npm run check`、`npm run build`、`mw build --install`、全量 pytest/vitest、真实网络调用、`Set-Content`

## 交付格式

`report.md`：结论 / 落点（文件:行）/ 五条验收输出原文 / 残留 / 未覆盖面。
禁止声称"已在 TUI 真跑过"——本卡不 build，真跑由 PM 在用户放行 build 后执行。

## 种子

- 目标锚点：`.agenticdoc/goal.md`
- 已落地的事实：`.agenticdoc/mw-decision-substitution/evidence/runs/jev-live-20261021/transcript.md`（engine 三元组、
  `mw decide sign` 预览输出）、本 key `decision-scope.md`、`decisions.jsonl` seq 25
- 锚点代码：`pm/ui-bridge.ts:4096`（dispatcher）、`:3811`（`runMwModelCommand` 范式）、`:4280`（usage 行）、
  `shared/mw-runner.ts:549`（`modelMw`）、`core/extensions/types.ts:139`（`ui.confirm`）、
  `packages/multi-workers/mw.py:1503`（`_DP_AGENT_ENV_VARS`）、`decide_signoff.py:368`（`render`）、`:504`（`write_signoff`）
- 测试范式：`packages/coding-agent/test/suite/rag-window.test.ts:126-160`（假 ctx + stub runner）

## 改动历史

- 2026-10-21 建卡：用户裁定 `/mw decide sign` 采用 (B) 确认对话框 + `--human-confirmed` 豁免。
