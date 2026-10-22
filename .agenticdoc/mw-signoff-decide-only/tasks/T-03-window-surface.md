# T-03 — 窗口面：不弹框、不问人、结论由模型给

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md` §4、`spec.md` AC-003/AC-007/AC-008

## 上下文

项目目标见 `.agenticdoc/goal.md`。`/mw sign` 这条命令在窗口里只是"触发决策模型签收"的按钮：没有确认框、没有 `hasUI` 门、没有调用方结论。

必读证据（已落盘）：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-tui-surface-20261022.md` —— 14 个出口的逐行清单、argv 归属（`--project` 由 runner 追加）、`xkey-gate-guard` 只订阅 `tool_call` 因此不拦这条路径、`ctx.hasUI` 恒为 boolean。
- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-signoff-faces-20261022.md` §2（`signed_via` 的窗口侧消费点）。

关键锚点：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4793` `runMwDecideCommand`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4821-4827` `hasUI` 门
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4864-4870` 逐结论前置拒绝
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4874-4882` 确认框
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4730` `decidePreviewArgs`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4558` `parseDecideArgs`、`:4491` `DECIDE_USAGE`、`:4502` `ParsedDecideArgs.conclusion`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts:573-582` `decideMw`（自动追加 `--project=<control root>`）

## 要求

1. `decidePreviewArgs`：`["sign","--key",key,"--dry-run","--json"]`；`--allow-empty` 按调用参数追加。
2. 写入 argv：`["sign","--key",key,"--json"]`。**不要传 `--auto`**：项目配置 `signoff: disable` 时必须继续生效。窗口绝不显式传 `--project`（runner 已追加）。
3. 删除 `ctx.hasUI !== true` 守卫与 `ctx.ui.confirm` 确认框；删除逐结论前置拒绝（结论在写入时才由模型产生，窗口无从预判）。
4. 成功出口拆分"已签收 / 未签收"：`exit 0` 不等于写了文件。判据：stdout 含 `signed_via:` 行 → 已签收（回显该行与 `conclusion:`）；否则 → 未签收（"decision model unavailable / sign-off not required"），文案明确不写文件。
5. `parseDecideArgs` / `ParsedDecideArgs`：删除 `conclusion` 字段与 `--conclusion` 解析；`sign` 允许裸调用；`DECIDE_USAGE` 同步删除 `--conclusion`/`--human-confirmed`。
6. 输出通道（AC-007）：命令结果文本走 `runMwDecideCommand` 的返回值（transcript 可见）；`ctx.ui.notify` 只在 `ctx.hasUI` 为真时调用，headless 下不得静默丢信息。
7. `mw-runner.ts` 的 `decideMw` 注释同步（不再有人签/结论参数）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`

## 写入禁止面

- `packages/coding-agent/test/**`（T-05 负责）
- `packages/multi-workers/**`（T-01/T-04 负责）
- `.agents/**`（T-02 负责）
- `docs/**`、`*.md`（T-06 负责）
- `packages/coding-agent/dist/**`

## 验收命令

```bash
cd packages/coding-agent && npx tsc --noEmit -p tsconfig.json
rg -n "human-confirmed|hasUI !== true|--conclusion" src/extensions/agent-team-loop/pm/ui-bridge.ts
```

期望：`tsc` 无错误；`rg` 无输出（`hasUI` 仍可用于 notify 判断）。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建；按 RQ3 证据修正写面 argv（不传 `--auto`）与成功出口判据 |
