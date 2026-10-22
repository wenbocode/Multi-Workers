# RQ3 — 窗口 `/mw decide sign` 的 TS 面与测试面

- type: research
- owner key: mw-signoff-decide-only
- 唯一证据文件：`.agenticdoc/mw-signoff-decide-only/evidence/research/spec-tui-surface-20261022.md`

## 上下文

项目目标见 `.agenticdoc/goal.md`。本 key 要把窗口签收从"必须人工点确认框"改为"转发给决策模型决定"，headless（`-p` / rpc / worker）下同样可用。

现状锚点：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4730` `decidePreviewArgs`（`["sign","--key",k,"--json"]`，无 `--dry-run`）
- 同文件 `:4776-4910` `runMwDecideCommand`（`hasUI` 硬门在 `:4823`，确认框 `:4871`，写参数 `:4884`）
- 同文件 `:4558` `parseDecideArgs`、`:4491` `DECIDE_USAGE`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:573` `decideMw` 注释
- `packages/coding-agent/test/suite/decision-signoff.test.ts`

## 要求（只读）

1. 完整列出 `runMwDecideCommand` 的分支树（每个 `return` 一行），标注哪些分支在删掉 `hasUI` 门与确认框后会消失/改变。
2. 给出改造后的 argv 设计：preview 用 `--dry-run --json`、write 用 `--auto`（不带结论）。指出 `--allow-empty`、`--reason`、`--key` 在新流程里各自的去留，并说明 `decideMw` 会自动追加 `--project=<control root>` 的机制（给出 mw-runner.ts 里的行号）。
3. 列出 `decision-signoff.test.ts` 的全部用例名与断言要点，逐条标注：保留 / 改写 / 删除，并给出改写后的断言方向（不要写完整测试代码）。
4. 找出 `xkey-gate-guard.ts` 对 `sign-final.md` 的写保护规则：窗口转发 `mw decide sign` 是否会被该守卫拦截（给它的判断输入是什么），说明改造后是否需要同步放宽。
5. 检查 `/mw decide` 的命令注册与 help 文案位置（`:5040-5070` 附近），列出需要同步改的字符串（含 `DECIDE_USAGE`）。
6. 回答：`ctx.hasUI` 在 headless 下是 `false` 还是 `undefined`，现有代码的 `!== true` 判定意味着什么（给类型定义行号）。

## 写入允许面

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-tui-surface-20261022.md`
- `.agenticdoc/mw-signoff-decide-only/workers/sdo-rq3-tui/**`

## 交付格式

Markdown，六节对应上面 6 条。第 1、3 条用表格；第 2 条给出最终 argv 字面量。最后 `## 最小改动面` 用 ≤8 行列出必须改的文件与函数名。
