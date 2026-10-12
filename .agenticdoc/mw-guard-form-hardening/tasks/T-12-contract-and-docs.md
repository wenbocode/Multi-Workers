# T-12 — 契约与文档处置（标记消费端 / 占位符计数 / CHANGELOG）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §`spec.md` §5 Q2 默认（删契约 + 设计说明改写）+ `design.md` §4.6（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-010 + 下列证据文件
- 证据: `evidence/research/spec-form-inventory-20261011.md`（C2/C7 现状）；前 key QG 报告的 C2/C7 条目
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/shared/deliverable-evidence.ts`；`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`packages/coding-agent/CHANGELOG.md`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-010｜VC: VC-036/037｜波 5｜链 S5（依赖 T-07）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/mwds-t03-bash-write-scope.test.ts`

## 必须实现
1. **`WRITE_SURFACE_MARKER`（C2）**：确认全仓无消费端后，删除该契约常量或补齐消费端——二者择一并写明理由；不得留下「有写入无读取」的悬空标记。
2. **`DELIVERABLE_PLACEHOLDERS`（C7）**：实现与文档计数对齐为 **16**；不得只改文档不改实现（反之亦然）。
   - 具名位置（T-11 复核）：`shared/deliverable-evidence.ts:57` 的注释仍写 `The 15 placeholder/default strings`，而 PM 实测集合大小为 16 ⇒ 必须同步为 16；同时核对 `design.md`/`spec.md` 与本 key 文档里的同一数字。
   - 断言侧已由 T-11 改造为「外部 `EXPECTED_PLACEHOLDERS` 集合逐元素相等 + 同尺寸替换控制」，本卡只负责注释/文档计数与实现一致，**不得**回退该改造。
3. `packages/coding-agent/CHANGELOG.md` 的 `## [Unreleased]` 下按 `### Fixed`/`### Changed` 追加本 key 的行为变化条目（英文、无 emoji、无版本号）。
4. 如删常量：确认无 import 残留、`npm run check` 无未用导出告警。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
