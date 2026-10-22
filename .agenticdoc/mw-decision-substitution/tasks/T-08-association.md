# T-08 决策关联：`decision:` 头行 + settle 追加

- key: mw-decision-substitution · type: coding · phase TASKS
- timeout: 40
- 依据: spec.md rev3（AC-007）+ design.md D-012、D-013 + plan.md §1

## 上下文

- 头行注入点：`pm/ui-bridge.ts:writeDispatchTaskMd:2282`（dispatch_worker 工具与 /worker 共用写点），merge 链末端；键语法与解析安全性证明见 `design-association-report-signoff-20261019.md` Q1。
- settle 唯一追加点：`pm/pm-orchestrator.ts:1691-1745`（`recordWriteScopeResidualRisks:1719`、`recordModelErrorTerminal:1724` 旁）。
- 6 终态映射：done→ok；人工 revert/supersedes→rollback；failed→rework；exit 3/model_exhausted→inconclusive；NC→不落行；lost→pending+note=lost。

## 要求

0. **顺带一行修正（T-04b 残留 1）**：`pm-orchestrator.ts` 的 `buildDp2CheckpointState` 产 `v: 2`（约 `:1763`），而注册表 builder 与 `triage-client.ts` 校验器统一为 `v: 1`；把该处改为 `v: 1`（dp2 结构化输入将来接入校验时不会再被自己拒掉）。

1. `decision: <decision_id>` 头行**仅当 `acted=true`** 时注入 task.md。
2. 终态回收处追加 settle 行：按 6 终态映射；`(decision_id, outcome, run_id)` 去重；`rollback` 必须晚于 `ok`；重复 settle 取最后一条。
3. 无法关联的 5 类（PM 本地 / 长时延 / 复合归因 / worker 内部 tool_call / 跨 key 外溢）显式登记，不猜测。
4. 新建 `test/suite/decision-association.test.ts`：6 终态各一条、suggest 不注入头行、去重、rollback 顺序。

## 交付格式

- 实现按上列写入允许面落地；报告四段：结论 / 证据（命令 + 输出摘要）/ 残留与未验证 / 改动文件清单。
- 每处关键实现附 `path:line`；关闭态未证明前不得声称完成。
- 遇到契约不足：停手并在报告"残留"里写明，禁止自行改契约。

## 种子

- goal 锚点: `.agenticdoc/goal.md`（文件驱动的去中心化协调 / 项目级目标对齐）
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:2282`
- 代码锚点: `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1691`

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（仅头行组装函数）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（仅终态回收段）
- `packages/coding-agent/test/suite/decision-association.test.ts`（新建）
- `packages/coding-agent/test/suite/dp2-narrow.test.ts`（**仅** `:320` 的 `v` 断言同步为 1）

## 写入禁止面

- 除上列文件外的一切文件（含其它包的源码、其它 key 目录、`_pitfalls.md`、`_project_log.md`）
- 禁止 `git add` / `git commit` / `git checkout` / `git stash` / `git clean`
- 禁止修改 `packages/ai/src/models.generated.ts`、禁止跑 `npm run build`、禁止跑完整 vitest 套件（用 `./test.sh` 或指定测试文件）

## 验收命令

```bash
cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-association.test.ts
```

## 改动历史

- 2026-10-20 创建
