# T-03 — 审计行 + `[WRITE_SCOPE_SUMMARY]` + PM 侧告警

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.2.4（审计行定稿 + 兼容性证据）+ §4.6 C-1（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-007 + 下列证据文件
- 证据: `evidence/research/design-write-guard-landing-20261011.md` §5（审计行字段 + 2 条真实行例 + 等值口径）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`；`packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-007｜VC: VC-029…VC-031｜波 4｜链 S1（依赖 T-02）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts test/suite/worker-dispatch-guard.test.ts`

## 必须实现
1. 审计行改 `… write-scope blocked=<bool> rule=… detail=… [risk=…] pattern=… target=… cmd=…`；新增 `[WRITE_SCOPE_SUMMARY] allow=… deny=… allow-unknown=…` 三计数。
2. **唯一既有读者**是 `test/suite/mwds-t03-bash-write-scope.test.ts:156` 的 `startsWith("[WRITE_SCOPE]")`，Python 侧零读者 ⇒ 扩展字段必须保持前缀与既有字段顺序不变。
3. `risk=deny-basename` 标注（F1–F3 类）；PM 侧告警出口复用 `pm-orchestrator.ts` 的 `recordDispatchAlarm`/`describeDispatchAlarm`（写 `.agenticdoc/_autopilot/auto-decisions.jsonl`）。
4. 断言 `allow_unknown_audited == allow_unknown_count`（等值，非「大于 0」）。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
