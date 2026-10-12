# T-06 — 新模块 `shared/task-frontmatter.ts`（单源解析）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.4.1（API 与边界算法）+ §4.5（代码纪律）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-005 + 下列证据文件
- 证据: `evidence/research/design-role-key-identity-20261011.md` §1（API 定稿 + 边界规则）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`；`packages/coding-agent/test/suite/task-frontmatter.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-005｜VC: VC-039｜波 1｜链 S3
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/task-frontmatter.test.ts`

## 必须实现
1. 新建 `packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`，导出 `extractTaskHeader` / `readTaskHeaderScalar` / `readTaskType` / `scanBodyTypeLines` / `findTypeEscalation`。
2. 头部边界算法：首行 fence（`---`）→ **首个空行** → 头部键文法截断（无空行时必须靠键文法截断）；`type:` 取**首个**；BOM 必须剥离并在返回值中标记。
3. `readTaskType` 返回含来源信息（头部/正文/缺失/非法）以便调用侧审计；不得抛异常。
4. 仅可擦除 TS 语法、无 `any`、无内联 import、单行 helper 内联。
5. 新增 `test/suite/task-frontmatter.test.ts`：覆盖裸头/fence 双形态、无空行、BOM、正文 `type:`、非法值、空文件、行尾 CRLF/LF。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
