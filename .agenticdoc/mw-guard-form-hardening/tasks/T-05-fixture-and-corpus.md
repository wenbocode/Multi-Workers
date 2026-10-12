> **状态：已由 T-04 吸收，本卡不执行（PM 裁定 D-022）。** 理由：T-04 的写入面本就包含 `test/suite/mwds-t02-write-intent.test.ts`，且已交付：① fixture 语义修正（`TASK_DIR = path.join(PROJECT, ".agenticdoc", "k", "workers", "t02")`，自身 taskDir 真例保持 `true`）；② 跨目录负例（`dir_blind_bypass=0 checked=4`）；③ 语料回归红→绿（`hits=2→13`、`FP=0`、`violations=1`、`leak_caught=5/5`）；④ Windows 9 项边界用例（VC-019 全量）。残余（非 ASCII 文件名 W9、R-1…R-5）已转 T-10 承接。

# T-05 — fixture 语义修正 + 跨目录负例 + 语料回归

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.3.4（PM 裁定：不得盲改断言）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-003, AC-004 + 下列证据文件
- 证据: `evidence/research/design-target-axis-20261011.md` §6（测试改造点）；spec AC-003/AC-004
- **唯一允许改的路径**: `packages/coding-agent/test/suite/mwds-t02-write-intent.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-003/AC-004｜VC: VC-014…VC-018, VC-046｜波 2｜链 S2（依赖 T-04）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t02-write-intent.test.ts`

## 必须实现
1. **fixture 语义修正**：`test/suite/mwds-t02-write-intent.test.ts` 的 `TASK_DIR` 补 `.agenticdoc` 段（现为 `<PROJECT>/k/workers/t02`，与真实布局不一致），使「自身 taskDir 的相对写法」这条真例**保持 `true`**。
2. **不得**按「由 `true` 改 `false`」的方式静默删真例；改为**新增**跨目录负例：`.agenticdoc/<other>/workers/x/report.md`、`../other/workers/x/report.md` ⇒ `false`。
3. Windows 9 项边界逐条落测试或显式标注为已知限制（design §4.3.2）。
4. 语料回放两条硬断言（`false_positives == []` ∧ 唯一真阳 ⊆ `KNOWN_TRUE_POSITIVE_TASKS`）**保持不变**；断言不得依赖 hits 计数上限（语料会增长）。
5. 报告实测：`hits` / `violations` / `false_positives` / 5 样例 `leak_caught` 前后对照。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
