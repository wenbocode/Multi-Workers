# T-10 — 14 条未覆盖分支测试

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.6 C-5 + `evidence/research/design-*-20261011.md` 各自的「本域分支清单」（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-008 + 下列证据文件
- 证据: 三份 design 证据中的分支清单（`design-write-guard-landing` §6：S1 承担 5 条 BR-01…05；`design-target-axis` §7：3 条；`design-role-key-identity` §7：#6/#7/#8/#13 ⇒ B1/B1b/B2/B3/B4）
- **唯一允许改的路径**: `packages/coding-agent/test/suite/mwds-t03-bash-write-scope.test.ts`；`packages/coding-agent/test/suite/worker-crosskey-readonly.test.ts`；`packages/coding-agent/test/suite/worker-dispatch-guard.test.；`packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`（仅追加）ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-008｜VC: VC-032…VC-034｜波 5｜链 S4（依赖 T-03、T-09）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts test/suite/worker-crosskey-readonly.test.ts test/suite/worker-dispatch-guard.test.ts`

## 必须实现
1. 把 14 条分支逐条落为**可独立失败**的用例（不是把既有断言换个名字）；每条给 `文件:行号` + 用例名 + 触发条件。
2. 覆盖必须包含：`ui-bridge.ts` 的 `:250`（豁免顺序）、`:82`（`_index.md` 回退）、`:1345-1346`/`:1402-1406`（放弃分支）；`shared/index-store.ts:159-161`；S1 的 5 条；S3 的 4 条。
3. 断言须是**行为级**（返回值/审计行/拒绝原因），不得只断言函数被调用。
4. 报告给出「分支 → 用例 → 前值（未覆盖时无法观察）/后值」表。

5. **承接 T-04 的残余（PM 裁定 D-022）**：T-04 登记的 R-1…R-5 与非 ASCII 文件名（W9，`cjk_hits=0`）逐条落为用例或显式标注为已知限制；断言须能在实现回退时变红。
6. 本卡结束时，`mwds-t02` 的既有断言（含语料 `false_positives == []` ∧ 唯一真阳）必须仍全绿。
7. **biome 告警已由 T-03 处置（本卡只需复核，不要回退）**：T-03 在 `test/suite/mwds-t03-bash-write-scope.test.ts:731` 加了带理由的 `// biome-ignore lint/suspicious/noTemplateCurlyInString: shell parameter expansion inside the corpus literal, not a JS p...`。**PM 已裁定接受该抑制**（语料行 `"printf x > ${T}/x.md"` 里的 `${T}` 是 shell 展开字面量，警告属误报；抑制优于改写字符串——后者会让人误以为语料可改写）。本卡只须：① 保留该注释及其理由；② 复核 `npx biome check --error-on-warnings` 在该文件上 0 issue；③ **不得**改动词料字符串或断言。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
