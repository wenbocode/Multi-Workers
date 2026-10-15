# KDR: mw-worker-output-contract

## R（需求）

- 技术栈：TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/**`，Node strip-only）+ Python（`packages/multi-workers/**`）；测试 vitest（`packages/coding-agent/test/suite/`，faux provider）+ pytest（`packages/multi-workers/test_*.py`）。
- 边界（不做什么，一句话）：只修 worker 输出面三契约（`output.md` 段契约 / `evidence/**` 产物写面 / `trace.log` 变更账本）及其依赖的检查点判据，不动 pi 核心、不动 phase 门禁、不改工具白名单。
- 关键约束（影响所有决策的核心约束）：GC-5 —— research/review 角色没有 `write`/`edit` 工具，因此修复不得靠「给角色加 write」，必须走放宽角色自有通道 `worker_file` 的路径域。

## 需求来源

- `_framework-reflect.md` 的 FW-001 / FW-002 / FW-005 / FW-007 / FW-009（五条同属「worker 输出面」一个写入面）。
- 本 key 立项前的复核证据（2026-10-14）：`mw-write-face-guard` 5 个 worker 的 `run.json` / `output.md` / `report.md` / `trace.log` / 产物字节与 mtime；`mw-worktree-junction-guard` 的 3 次实例（QG / W-12 / W-15）。
- 关键代码坐标：`worker/output-sections.ts`（`RECOVERY_SECTIONS` / `RECOVERY_SECTION_ALIASES` / `containsAlias`）、`worker/worker-mode.ts:2745`（`exitCode`）、`:2776`（questions 文案）、`:723/:1604/:1624/:2199`（写面）、`:2368-2388`（`[WRITE_FILE]` 记录）、`worker/worker-file-tool.ts:42,63`（`WORKER_FILE_NAME_RE`）、`shared/change-ledger.ts:116,123,135`。

## 范围外（分流）

- FW-003（伪 `failed` 风暴）、FW-004（派发卡两道静默门槛）→ 已有 key `mw-dispatch-reliability`。
- FW-006（review 审计只做引用闭包）→ `mw-review-audit-method`。
- FW-008（`./test.sh` 无墙钟超时）→ `mw-test-runner-hygiene`。

## A（架构）← system-design 追加

## I（实施）← PM 执行中追加
