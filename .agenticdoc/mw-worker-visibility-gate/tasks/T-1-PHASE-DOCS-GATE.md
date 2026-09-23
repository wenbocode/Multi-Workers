# Task T-1: 派发门禁按相位分层（phase-docs.ts）

## 元信息
- Stage: 1（波形 1，可与 T-2 并行）
- 依赖: 无
- 风险: 中（改公开签名，但有可选参数兜底）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-012]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-012]
- 文件面（唯一）：`packages/coding-agent/src/extensions/agent-team-loop/shared/phase-docs.ts`、新建 `packages/coding-agent/test/extensions/agent-team-loop-phase-docs-gate.test.ts`

## 背景（实测，可直接引用）

- `shared/phase-docs.ts:127` `dispatchDocGaps(agenticdocRoot, key)`：`_scratch` 短路（`:128`），其余 `phaseDocGaps(readPhaseDocs(...))`。
- `phase-docs.ts:96` `phaseDocGaps(status)` 六项硬要求与相位无关：`spec.md`≥500B（`:7` 常量）、`evidence/research/spec-*.md`≥1、§0 含"预期收益"、≥1 条 `AC-NNN`、`design.md`≥500B、`evidence/research/design-*.md`≥1。
- 相位可读：`pm/ui-bridge.ts:902 dispatchPhase()` → `StateManager.read().phase`（`pm/state-manager.ts:31`）。调用点两处：`ui-bridge.ts:1093`、`:1498`（T-3 负责接线，本任务不改）。
- 现状缺陷：新 key 在 SPEC 相位永远过不了门禁（design 文档与 design 证据必须先生成，而 design 证据本该由 design 阶段的 worker 产出）→ 只能落 `_scratch`。
- `update_index.py claim` 新建 pm-state 时写 `- Phase: init`（另一个仓库的脚本），TS 侧 `Phase` 联合类型里没有 `init` → 必须归一化为 spec 层。

## 交付物

1. 改 `shared/phase-docs.ts`（**不得改动** 既有缺项文案字符串、`MIN_PHASE_DOC_BYTES=500`、`DOC_GATE_HINT`、`formatDocsBadge`、`readPhaseDocs` 的字段语义）：
   - 新增 `export type GateTier = "spec" | "design";`
   - 新增 `export function gateTierOf(phase: string): GateTier;` —— `SPEC`/`init`（任意大小写）/`—`/`-`/空串/未知串 → `"spec"`；`DESIGN`/`PLAN`/`TASKS`/`EXECUTE`/`VERIFY`/`DONE` → `"design"`。
   - 改 `phaseDocGaps(status: PhaseDocStatus, tier: GateTier): string[]`：`spec` 层只 push spec 侧四项（顺序不变）；`design` 层 push 全部六项（顺序与改造前完全一致）。
   - 改 `dispatchDocGaps(agenticdocRoot: string, key: string, phase?: string): string[]`：`_scratch` 短路不变；tier 由 `gateTierOf(phase ?? "")` 决定（**缺省即 spec 层** —— 这样两处既有调用点在本任务单独合入时仍能编译）。
2. 新增测试 `test/extensions/agent-team-loop-phase-docs-gate.test.ts`（只建临时 key 目录，用 `os.tmpdir()`，不污染仓库）：
   - VC-001：构造 phase=SPEC + spec 侧四项齐备 + `design.md` **缺失** 的 key → `dispatchDocGaps(root, key, "SPEC")` 返回 `[]`（放行）。
   - VC-002：phase=DESIGN + `design.md` 缺失 → 返回数组恰好 1 条且等于 `"design.md missing or under 500 bytes"`。
   - VC-003：phase=DESIGN + `design.md` ≥500B + 无 `evidence/research/design-*.md` → 返回恰好 1 条 design 证据缺项。
   - VC-004：phase 取 `"—"` / `""` / `"init"` / `"weird-phase"` 四种取值 → 判定与 `"SPEC"` 完全一致（返回数组相等）且不含任何 design 缺项。
   - VC-005：phase=SPEC + `spec.md` <500B → 返回条数 == spec 侧缺项数（构造时缺失几项就断言几条）且 design 侧缺项 0。
   - VC-012（回归，纯门禁层）：phase=SPEC + spec 侧齐备 → 放行（该 VC 的完整形态由 T-3 在工具入口断言；此处只需证明门禁层不依赖 task 类型）。
   - 边界：`design.md` 恰好 500 字节 → design 层放行（阈值是 `>=`）。
   - `[VERIFY]` 行必须用 `process.stdout.write("…\n")` 输出（vitest `silent: "passed-only"` 会吞 `console.log`），格式：`[VERIFY] VC-001: spec_phase_pass=true task_md=true`（本任务无工具入口，用 `spec_phase_pass=true gate_blocked=false` 这类等价断言值即可，但**每个字段必须取自实测变量**）。

## 约束

- 只改上述两个文件；**不改** `pm/ui-bridge.ts`（T-3 负责）、不改 `dist/**`、不改 Python、不改 `test/extensions/agent-team-loop.test.ts`。
- TS 只用可擦除语法（无 `enum`/`namespace`/参数属性）；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-phase-docs-gate.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：改动文件、用例计数、每条 `[VERIFY]` 行原文、`gateTierOf` 全取值表、以及任何偏离 design 的实现细节。
