# T-06 — AC-007：`output.md` 信息量（Deliverables/省略 + Exit Reason 努力度）

- key: `mw-dispatch-settle-gates`｜AC: **AC-007**｜VC: **VC-031…VC-033**｜波次 **3**｜链 2（依赖 T-04 对 `worker-mode.ts` 的编辑）
- 角色: coding
- **唯一允许改的路径**：① `worker/output-writer.ts`；② `worker/worker-mode.ts`（**仅** Exit Reason 一行与 `changedFiles` 取值处）；③ 新建 `packages/coding-agent/test/suite/mwds-t06-output-informativeness.test.ts`；④ 自身目录 `report.md`
- 上游：`design.md` DD-09；证据 `evidence/research/design-settle-read-20261010.md` §回归断点（28 条，必须"更新而非放松"）

## 现状（实测）
- `## Changed Files` 体 = `opts.changedFiles?.join("\n") ?? "(none)"`（`output-writer.ts` 约 `:65-66`）；`changedFiles` 的唯一赋值是 `[]`（`worker-mode.ts` 约 `:1359`）⇒ `?? "(none)"` **不可达**；语料 30 个目录中该段出现 0 次 `(none)`、且**从不含源码改动**（`run.json.artifacts` 采集器 `shared/run-store.ts:119-138` 只收任务目录内文件）。
- `## Exit Reason` = 常量 `Agent settled after ${toolCallCount} tool call(s).`（`worker-mode.ts` 约 `:1361`）⇒ 8 次与 127 次调用的 run 文本同形。

## 必须实现
1. **`## Changed Files` → 条件化**：当 `run.json.artifacts`（或等价已采集产物列表）非空 ⇒ 段名改为 `## Deliverables`，列出产物（**排除** `output.md`/`progress.md`）；为空 ⇒ **整段省略**（不得留空段、不得输出 `(none)`、不得写 `(none)` 以外的占位）。
2. **`## Exit Reason` 带努力度**：`toolCallCount` + `writes=<report.md|progress.md|none>`（writes 取自本 run 的实际写动作统计；无写 ⇒ `none`）。**不得**改变既有前缀语义（保持英文、单行、可 grep）。
3. **回归断点必须更新（不是放松）**：受影响断言（据 `design-settle-read` 证据：#4、#10/#11、#19；#23 必须保持绿）——把"必须有 `## Changed Files` 段"改为"有产物 ⇒ `## Deliverables`；无产物 ⇒ 无该段"。不得删除断言语义。
4. `output-writer.ts` 的"空则覆盖、非空则追加 `---`"既有语义（约 `:95`）不动；本卡只改段生成。

## 反向用例（必须真跑）
- (a) 无 artifacts ⇒ `output.md` 中**不存在** `## Changed Files` 与 `## Deliverables`（断言两者皆无）；(b) 有 artifacts ⇒ 存在 `## Deliverables` 且不含 `output.md`/`progress.md`；(c) `## Exit Reason` 含 `toolCallCount` 数字与 `writes=`；(d) 静态代码扫描/真实 run：`(none)` 不可能再出现在该段（证伪旧不可达路径）；(e) 单测直接跑旧断言集（更新后的 28 条）全绿。

## 对照协议（`plan.md §5`）
A 恢复无条件段 ⇒ (a) 转红；B 反转（无产物也输出 `## Deliverables`）⇒ (a) 转红；C 去掉 `writes=` ⇒ (c) 转红。每组贴 sha256 → 逆改 → 红 → 还原 → 绿。

## 证据
```
[VERIFY] VC-031: no_artifacts_section_absent=true none_literal=0
[VERIFY] VC-032: with_artifacts_heading=Deliverables excludes_output_md=true excludes_progress_md=true
[VERIFY] VC-033: exit_reason_has_toolcalls=true writes_field=true
[VERIFY] regression: updated_assertions=28 green_before=28 green_after=28
```
命令：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t06-output-informativeness.test.ts test/extensions/agent-team-loop.test.ts`

## 禁止
不改 `shared/output-sections.ts`（T-05）；不改 `pm/*`；不改大测试文件**除**本卡列明的 4 处断点（#4/#10/#11/#19）之外的内容；不 build；不 commit；不跑全量套件 / `npm run check`。
