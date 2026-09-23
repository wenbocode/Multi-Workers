# Task T-4: 独立验证（第三方视角）

## 元信息
- Stage: 3
- 依赖: T-1、T-2、T-3 全部完成
- 风险: 中（重型验证；注意输出预算与落盘）
- Agent: coding worker（独立视角；允许跑测试与临时改文件做反例，但必须 sha256 复原）
- ac_refs: [AC-306 及 AC-301~AC-305 复核]
- vc_refs: [VC-301 ~ VC-312]

## 交付物

`.agenticdoc/mw-rag-window-parity/evidence/verify-run-2026-09-23.md`（**唯一允许写的文件**；其余只读）

落盘协议：先 `write` 骨架（§0~§6 标题 + 结论占位），再每节一次 `edit` 填充。建议 ≤ 300 行。

## 必须做

### 1) 基线与零回归

1. `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-window.test.ts`（逐条记 `[VERIFY]` 原文）
2. `node ../../node_modules/vitest/dist/cli.js --run test/suite/rag-config.test.ts test/suite/rag-parity.test.ts test/suite/rag-tools.test.ts test/suite/rag-required.test.ts test/suite/rag-role-defaults.test.ts test/suite/rag-evidence.test.ts`
3. `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-output.test.ts`
4. `cd packages/multi-workers && python -m pytest -q`（记 passed / deselected / 失败项）
5. 仓根 `npm run check`（exit code）
6. `git diff --stat -- packages/multi-workers/test/fixtures packages/multi-workers/test_autopilot_l0.py`（必须为空）
7. `git status --porcelain` 与 `git diff --stat`（区分「本 key 改动」与「其它会话改动」）

### 2) 反例（**必须做**，逐条记录「改了什么 / 看到什么红 / 还原方式 / sha256 是否复原」）

- **反例 A（parity 放宽真的生效且必要）**：把 `rag/config.ts` 的 `skill.dir` 从 `optionalString` 改回 `requireString`
  → VC-301/VC-302 必须红；还原 + sha256 自检。
- **反例 B（`--project` 真的指向控制工作区）**：把 `shared/mw-runner.ts` 里 `runMwCliRaw` 追加的
  `--project=${projectDir}` 改成 `--project=.` → VC-308/VC-309 至少一条必须红（取到错的配置/行）；还原 + 自检。
- **反例 C（doctor 行真的被渲染）**：删掉 `formatDoctorReport` 里插入 RAG 行的那一行
  → VC-310 必须红；还原 + 自检。
- **反例 D（渲染门控真的与 Python 同门）**：把 `formatDoctorReport` 里的
  `if (shouldShowRagDoctorRow(report.rag))` 改回 `if (report.rag)`
  → VC-309b 必须红（无 RAG 配置的项目会被多打一行 `rag: not enabled`）；还原 + 自检。

> 若某条反例不变红，说明该断言是装饰：如实降级该 VC 的证据强度并写明原因（不得含糊）。

### 3) 逐 VC 表

每行给：断言摘要 | 发射位置 `file:line` | **实测行原文** | 证据强度（强/弱/装饰）。VC-301~VC-312 全部要有行；
缺失的必须显式写「未覆盖 + 原因」。

### 4) 实现/文档一致性抽查（≥6 条可证伪断言）

独立挑至少 6 条本次改动引入或影响的断言（示例：`RagSkillEntry.dir` 的类型、`dir: ""` 的错误文本、
`RAG_SUBCOMMANDS` 与 `mw.py _RAG_ACTIONS` 是否一致、`formatRagDoctorLine` 的 fingerprint 截断位数、
截断阈值 30 行、`/mw` description 是否含 `rag`），逐条对照代码/实跑，给「断言 | 依据(file:line 或命令) | 符合/不符」。
**不符项不要改**——写进报告并给 `file:line`。

### 5) 补充实验（E-4，必做）

T-3 自报有两个渲染分支**没有用例钉住**：probe 多服务器排序拼接（`A=reachable, B=unreachable`）与
`required_missing>0` 追加。请自行构造一个真实项目 fixture（两个 mcp 服务器，至少一个指向 `127.0.0.1:9xxx`
不可达；roles/phases 里声明 `require` 且存在缺失引用以让 `required_missing>0`，具体构造自定），
跑 `mw.py doctor --json` 与文本版，断言 `formatRagDoctorLine(report.rag)` 与 Python 的 `rag: ` 行**逐字相等**。
在报告 §4 给实测两串；**若发现不一致，不要改代码，写清 `file:line` 与两串原文**。

### 6) 归属与限制

- 失败项逐条归属：本 key 缺陷 / Windows 环境基线 / 其它会话未提交改动。
- 如实写「未做」：真实 RAG 服务联调、`mw serve` 重启后的端到端 worker 跑、pi TUI 里真按 `/mw rag` 的人工操作
  （本任务只验证代码路径与纯函数）、中文排版。

## 验收

- 报告含 §0 复现命令表、§1 VC 汇总表、§2 逐 VC 明细、§3 反例试验记录、§4 一致性抽查、§5 零回归与改动面、§6 未覆盖与限制。
- 除该报告外未改任何文件（反例试验的临时改动必须已复原）；未 commit。
