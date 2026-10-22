# T-05 — TS 测试重写：窗口不再问人

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md` §4/§6、`spec.md` AC-003/AC-007/AC-008

## 上下文

项目目标见 `.agenticdoc/goal.md`。T-03 已删除 `hasUI` 门、确认框、`--conclusion`/`--human-confirmed`；窗口写面是 `sign --key k --json`，预览是 `sign --key k --dry-run --json`，成功/未签收由 stdout 是否含 `signed_via:` 区分。

必读证据：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-tui-surface-20261022.md` §1/§2/§4 —— 14 个出口清单、argv 归属、两个测试文件的真实分工（`decide-command.test.ts` 才是含 `hasUI`/`--human-confirmed` 断言的那 12 例；`decision-signoff.test.ts` 是写守卫）。

实现锚点：

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4793` `runMwDecideCommand`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:4730` `decidePreviewArgs`
- `packages/coding-agent/test/suite/decide-command.test.ts:62` `fakeDecideCtx`、`:175` `hasUI=false` 用例、`:284` 确认框 argv 用例、`:390` 守卫用例

## 要求

### `packages/coding-agent/test/suite/decide-command.test.ts`

- 删除（5 例）：`hasUI=false notifies a warning and never calls the runner`（`:175`）、两个断言"preview 不写文件/无 `--human-confirmed`"的守卫用例中依赖确认框的部分、`confirming forwards the exact write argv with --human-confirmed`（`:284`）、以及任何期望 `usage` 错误里出现 `needs a conclusion` / `invalid conclusion` 的断言（`:151-158`）。
- 改写（4 例）：
  - `parseDecideArgs` 用例：裸 `sign --key k` 合法；移除 `conclusion` 字段断言。
  - preview argv 断言：`["sign","--key","k","--dry-run","--json"]`。
  - write argv 断言：`["sign","--key","k","--json"]`（不含 `--auto`、不含 `--project`）。
  - `hasUI=false` 用例：改为"仍然 spawn，且结果文本回到命令返回值"。
- 保留（3 例）：`--dry-run` 失败时 notify 的行为、非签收子命令的透传、`decideMw` 的 `--project` 追加断言（如果在该文件）。
- 新增：
  - `headless sign runs and reports through the return value`：`hasUI:false` 时 runner 被调用一次，返回文本包含 `signed_via`。
  - `exit 0 without a signed_via line is reported as not signed`：stub 输出 "decision model unavailable ... not required"，断言结果文本不提"已签收"/文件路径。
  - `preview never touches the write path`：preview 调用只出现 `--dry-run`，写面调用 0 次。

### `packages/coding-agent/test/suite/decision-signoff.test.ts`

- 0 删；2 改：凡依赖 `write_signoff` 的 agent-session env 拒绝或 `--human-confirmed` 的夹具，改成新语义（env 存在也能写、argv 无该标志）。

### `packages/coding-agent/test/suite/decision-dashboard-command.test.ts`

- 4 处断言依赖旧语义（`:217`、`:254`、`:285`、`:381`，具体见 `.agenticdoc/mw-signoff-decide-only/workers/sdo-t03-window/report.md`）：按新语义修正（不再有确认框/`--conclusion`/`hasUI` 拒绝）。

## 写入允许面

- `packages/coding-agent/test/suite/decide-command.test.ts`
- `packages/coding-agent/test/suite/decision-signoff.test.ts`
- `packages/coding-agent/test/suite/decision-dashboard-command.test.ts`

## 写入禁止面

- `packages/coding-agent/src/**`（T-03 的写面）
- `packages/multi-workers/**`
- `.agents/**`、`docs/**`

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/decide-command.test.ts test/suite/decision-signoff.test.ts test/suite/decision-dashboard-command.test.ts
```

必须全绿；不得用 `skip`/`todo` 掩盖被删的行为。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建；按 RQ3 §4 把主战场定位到 `decide-command.test.ts` |
