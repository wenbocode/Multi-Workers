# T-11 — 空洞断言替换

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §`spec.md` AC-009｜QG-B D-047 的 2 条空洞断言（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-009 + 下列证据文件
- 证据: `evidence/quality-gate-code-adversarial-20261011.md`（前 key 的对抗质量门报告，含 2 条空洞断言的具名位置）
- **唯一允许改的路径**: `packages/coding-agent/test/suite/`（仅 2 条空洞断言所在文件，报告须列明路径）；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-009｜VC: VC-035｜波 4｜链 S4（依赖 T-05）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts test/suite/mwds-t04-deliverable.test.ts`（PM 勘误：原写 `mwds-t01-worker-crosskey.test.ts` 不存在；实际命中 = `mwds-t03` + `mwds-t04`）

## 必须实现
1. 定位 QG-B 点名的 2 条**自证式**断言（占位符集合自计数、形态覆盖薄断言）并替换为**独立数据源**断言（从真实文件/常量清单/实现导出的集合比对，而非用被测量集合与自己比较）。
2. 每条替换说明「为什么原断言恒真/近似恒真」，并给出**能失败的改造版本**（先构造失败再修实现或修断言，报告须附红→绿证据）。
3. 不得通过删除用例来消除空洞断言。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
