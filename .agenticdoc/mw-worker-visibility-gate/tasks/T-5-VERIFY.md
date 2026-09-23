# Task T-5: 独立验证（VC 复现 + 变异反例）

## 元信息
- Stage: 3（波形 3，必须在 T-1…T-4 全部完成并 ack 之后开始）
- 依赖: T-1、T-2、T-3、T-4
- 风险: 中（要动被测源码做变异，必须逐字节复原）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-001 … AC-013]
- vc_refs: [VC-001 … VC-013]
- 文件面：只写新建的报告 `evidence/verify-independent-2026-09-23.md`（相对本 key 目录），临时试验代码只允许放 `os.tmpdir()`；变异必须复原。

## 目标

对 design §7 的 13 条 VC 做**独立复现**（不复用 T-1/T-2/T-3/T-6 的断言结论，自己构造输入），并对 3 处关键判据做**变异反例**，证明"改坏即红、复原即绿、逐字节相等"。

### 执行期修订（必读，已写入 design/spec）

- **D-110**：门禁调用点实为**三处**（`pm/ui-bridge.ts:1093`、`:1498`、`pm/pm-orchestrator.ts:429`）——三处都要验，特别是第三处的 **DESIGN 相位拦截**（T-3 已加反例用例，你要独立重做）。
- **D-111 / AC-011 [REVISED @ 2026-09-23]**：VC-011 语义已变——pm-state **缺** `- Claim-Id:` 行时**插行**（`ok:true`、无 warning），只有**既无 Claim-Id 也无 Key 行**才 `ok:false` + 不写。按修订后的 VC-011 复现（旧语义视为 FAIL）。
- **VC-009 的 risk 来源**：`readTaskProgress` 只解析 trace.log 的 `[CHECKPOINT] ... risk=<...>` 行（不解析 progress.md 的 `CKPT ... [machine]` 行）—— 夹具要按前者构造。
- 回归面：5 个测试文件合计 **203 passed**（`agent-team-loop.test.ts` 173 + `phase-docs-gate` 11 + `pm-state-claim` 8 + `watch-aggregate` 7 + `pm-state-sync` 5 − 1 重叠计数以实跑为准）。

## 交付物

报告 `.agenticdoc/mw-worker-visibility-gate/evidence/verify-independent-2026-09-23.md`，含：

1. **VC 复现表**：VC-001…VC-013 逐条 → PASS / PASS-with-note / FAIL，附**命令 + 原始输出片段**（grep 得到的行，不接受"返回 ok"这类转述）。
2. **变异反例**（每个都要 sha256 前后对照）：
   - M-1：把 `gateTierOf` 的未知串分支改成返回 `"design"` → 期望 VC-004（或 VC-001）转红；复原后 sha256 与变异前相同。
   - M-2：把聚合行的 `risk=high` 段去掉 → 期望 VC-009 转红；复原后 sha256 相同。
   - M-3：把 `takeOverKey` 里的 `syncPmStateClaimId` 调用短路（`if (false)`）→ 期望 VC-010 转红（两处值不再相等）；复原后 sha256 相同。
3. **回归**：`cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-phase-docs-gate.test.ts test/extensions/agent-team-loop-pm-state-claim.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts` 的通过/失败计数（期望 0 failed）；`npm run check` exit code。
4. **git 洁净性**：起止各跑一次 `git status --short`，逐行相同（证明变异全部复原、无残留临时文件）。
5. **缺口**：任何无法复现的 VC（写清原因与建议）。

## 约束

- 只读被验代码；**不得**修改 T-1/T-2/T-3 的交付文件（除变异窗口期外）；变异结束必须复原并给 sha256 证据。
- 不得 commit；不得运行 `mw build`；不得改 `dist/**`、不得改 Python。
- 报告必须落盘（`evidence/` 下），并在 `output.md` 里给出 `[VERIFY]` 行。

## 验收命令

```
cd H:/git/Multi-Workers
python -X utf8 -c "import pathlib;print(pathlib.Path('.agenticdoc/mw-worker-visibility-gate/evidence/verify-independent-2026-09-23.md').stat().st_size)"
git status --short
```

## 报告要求

最终消息给出：VC 复现统计（PASS/PASS-with-note/FAIL 计数）、3 个变异的红/绿与 sha256、回归计数、缺口清单。
