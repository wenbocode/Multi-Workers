# T-06 — 文档同步：把"人签"从文档里删干净

- type: coding
- owner key: mw-signoff-decide-only
- 派生自：`design.md`、`spec.md` AC-009

## 上下文

项目目标见 `.agenticdoc/goal.md`。代码里已经没有"人在 agent loop 之外签收"这条路，文档必须与新语义一致，否则下一个 agent 会照着旧文档重新造出人签入口。

必读证据：

- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-signoff-faces-20261022.md` §2/§6 —— 文档中所有 `--human-confirmed` / `cli`/`tui` / "会话外执行" 的落点。
- `.agenticdoc/mw-signoff-decide-only/evidence/research/spec-gate-structure-20261022.md` §1 —— "仅当存在 `decision-scope.md`" 这句话为什么必须删。
- `.agenticdoc/mw-signoff-decide-only/design.md` §2/§3 —— 最终规则与参数面。

锚点：

- `docs/decision-substitution.md:360-445`（§5.2 收尾强制签收、§5.4 TUI 入口 FIX-Q）
- `docs/decision-substitution.md:421`（"仅当 key 目录存在 `decision-scope.md` 时生效"）
- `docs/decision-substitution.md:485`（故障表"收尾门禁报必须有决策签收记录"）
- `packages/multi-workers/README.md:854`（能力表"收尾签收"行）
- `packages/multi-workers/README.md:880-930`（`mw decide sign` 一节）
- `packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md` 的 `## [Unreleased]`

## 要求

1. `docs/decision-substitution.md`
   - §5.2：`mw decide sign` 的结论只来自 `dp25-signoff-conclusion`；删除"人只回结论""应用签收必须由人在 agent 会话外执行""`--human-confirmed` 例外"等表述；写清 jev 不可用时**不写文件、exit 0、门禁保持 MISSING**。
   - §5.3/§5.4：删掉整段 FIX-Q 描述（`ctx.hasUI` 拒绝、确认框、`--human-confirmed`、`signed_via: tui`），替换为"窗口只触发签收，preview 用 `--dry-run --json`，写面 `sign --key k --json`；`signed_via` 只有 `auto-decide`"。
   - 门禁段：把"仅当 key 目录存在 `decision-scope.md` 时生效"改为"无条件执行；`.mw/decide.json` 的 `signoff: disable` 或该 key 档案无 `kind=decide` 行 → 跳过；存在性与 `conclusion:` 检查已并入该规则"。
   - 故障表 `:485` 行：把"人写签收文件"改成"重跑 `mw decide sign`（决策模型不可用时先修 transport）"。
   - 保留 `--human-confirmed` 只出现在历史档案说明里（如果必须提及），并注明**已删除**。
2. `packages/multi-workers/README.md`
   - `:854` 能力表：签收由 `mw decide sign --project .agenticdoc/<key>` 触发，结论由决策模型给出；删除"人只回结论"与"人在 agent 会话外跑 `dp apply`"。
   - `:880-930`：命令示例去掉 `--conclusion`/`--human-confirmed`；补 `--dry-run --json` 的 `verdicts` 形状；补"零 `kind=decide` 行 → 无需签收"。
3. CHANGELOG（两个包各一条，`## [Unreleased]` 下 `### Changed` / `### Removed`）：
   - multi-workers：签收收敛为决策模型单一路径；删除 `auto-llm`/`cli`/`tui` 面与 `--conclusion`/`--human-confirmed`；门禁改为无条件执行 + 零决策行跳过。
   - coding-agent：`/mw decide sign` 不再要求 `hasUI`、不再弹确认框、不再传 `--human-confirmed`；preview 改用 `--dry-run --json`。
   - 不写 issue/PR 链接（本 key 无对应 issue）。

## 写入允许面

- `docs/decision-substitution.md`
- `packages/multi-workers/README.md`
- `packages/multi-workers/CHANGELOG.md`
- `packages/coding-agent/CHANGELOG.md`

## 写入禁止面

- 所有源码与测试文件
- `.agents/skills/agentic-task/**`（含其 SKILL.md/references）
- `.agenticdoc/**`（PM 管理）

## 验收命令

```bash
rg -n "human-confirmed|human_confirmed|--conclusion" docs/decision-substitution.md packages/multi-workers/README.md
rg -n "decision-scope.md 时" docs/decision-substitution.md
```

期望：第一条只剩"已删除"的说明性提及（如有），不得有可照做的命令示例；第二条无输出。

## 改动历史

| date | change |
| --- | --- |
| 2026-10-22 | 卡片创建 |
