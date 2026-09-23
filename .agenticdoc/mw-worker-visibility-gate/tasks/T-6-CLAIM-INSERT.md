# Task T-6: pm-state 缺 `- Claim-Id:` 行时插入该行（D-111 语义修订）

## 元信息
- Stage: 4（波形 2.5，必须在 T-3 完成并 ack 之后开始；与 T-5 串行，T-5 在 T-6 之后）
- 依赖: T-2（`shared/pm-state-claim.ts`）、T-3（接线与 `agent-team-loop-pm-state-sync.test.ts` 的 VC-011 用例）
- 风险: 中（写 pm-state.md；但只插一行、不重排模板）
- Agent: coding worker（`read/write/edit/bash/find/grep/ls`）
- ac_refs: [AC-011（REVISED @ 2026-09-23）]
- vc_refs: [VC-011（修订版）]
- 文件面（唯一）：`packages/coding-agent/src/extensions/agent-team-loop/shared/pm-state-claim.ts`、`packages/coding-agent/test/extensions/agent-team-loop-pm-state-claim.test.ts`，以及 `packages/coding-agent/test/extensions/agent-team-loop-pm-state-sync.test.ts` 中**仅 VC-011 那一个用例**的期望值

## 背景（实测，T-1 执行期发现 → design D-111）

- 本仓四个 key 的 `pm-state.md` **全部没有** `- Claim-Id:` 行：`mw-worker-progress-persist`/`mw-task-scope-isolation`/`mw-rag-window-parity`/`mw-worker-visibility-gate`（脚本核验：`re.search(r'^- Claim-Id:', t, re.M)` → None，而索引行都有 Claim 值）。
- 原因：TS 路径（`switch_key` → `IndexStore.claim`）只写 `_index.parallel`；随后 `advance_phase.py` 新建的 7 段模板不带 Claim-Id。
- 框架自身的处理口径：`update_index.py` 的 `_update_pm_state_claim` 在缺行时 **"Insert after '- Key:' line"**（`count=1`，保留换行风格）。
- 当前（T-2 实现）语义：缺行 → `ok:false` + reason，不写 → 于是"两处同值"对最常见的 key 创建路径**永远无法达成**，每次 claim 都只能回一条 warning。
- design D-111 已把语义改成"缺 Claim-Id 行 → 在 `- Key:` 行之后插入；既无 Claim-Id 也无 Key 行 → 才 `ok:false` 且不写"。

## 交付物

1. 改 `shared/pm-state-claim.ts`：
   - 保持既有成功路径（有 `- Claim-Id:` 行 → 单行原地替换 + 换行不变 + 原子写 + P-010 换行守卫）**逐字不变**。
   - 新增分支：无 `- Claim-Id:` 行 **但**有 `^- Key:` 行 → 在该行之后插入 `- Claim-Id: <claimId>`（使用文件的主导换行；其余字节不变；原子写）→ `{ ok: true }`。
   - 既无 `- Claim-Id:` 也无 `- Key:` 行 → `{ ok: false, reason: "pm-state.md has no '- Key:' or '- Claim-Id:' line" }`，文件逐字节未变（不写）。
   - 文件不存在 → 仍是 `{ ok: false, reason: "pm-state.md missing" }`（不创建）。
2. 改测试 `test/extensions/agent-team-loop-pm-state-claim.test.ts`：
   - 原"缺行 → ok:false 未变"用例改为：缺 Claim-Id 行、有 Key 行 → `ok:true`，插入后 (a) `- Claim-Id:` 值正确；(b) 插入位置紧跟在 `- Key:` 行之后；(c) `\r\n` 计数 = 原值 + 1、LF-only 保持 0（CRLF 样本）；(d) 除插入行外的字节逐字节相等；(e) 二级标题数与 `- Updated:` 行数不变。
   - 新增：既无 Claim-Id 也无 Key 行 → `ok:false` + 文件逐字节未变；文件不存在 → `ok:false` + 未创建。
   - `[VERIFY]` 行用 `process.stdout.write`，字段取自实测：`[VERIFY] VC-011: inserted=true ok=true outside_identical=true`、`[VERIFY] VC-011: no_key_line ok=false untouched=true`。
3. 改 `test/extensions/agent-team-loop-pm-state-sync.test.ts` 的 **VC-011 用例**（T-3 写的那个）：期望值从"`claimSync.ok === false` + 1 条 warning"改为"`claimSync.ok === true` + `claimSyncWarningText(...)` 为空串（无 warning）"，并断言文件里 `- Claim-Id:` 值 == 索引行 Claim 列（即 VC-010 的同值不变式对该 key 也成立）。**该文件其他用例（VC-010/VC-012）不得改动。**

## 约束

- 只改上述三个文件；不改 `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`shared/phase-docs.ts`、`dist/**`、Python。
- 插行必须单行、原子、换行不变；**禁止**整体重写模板（不得出现 `## 1. Snapshot` 之类的重建）。
- TS 只用可擦除语法；无 `any`；无 inline `import()`。
- 不 commit；不运行 `mw build`。

## 验收命令

```
cd packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-pm-state-claim.test.ts test/extensions/agent-team-loop-pm-state-sync.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/extensions/agent-team-loop-phase-docs-gate.test.ts test/extensions/agent-team-loop-watch-aggregate.test.ts
cd H:/git/Multi-Workers && npm run check
git status --short
```

## 报告要求

最终消息给出：改动文件、用例计数、`[VERIFY]` 行原文、插入前后的字节级实测数字（CRLF 计数、二级标题数、`- Updated:` 行数、除插入行外逐字节相等）、以及任何偏离 design D-111 的实现细节。
