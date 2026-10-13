# T-05 coding 改动历史（trace 事件 ⊆ 报告清单）

- Key: mw-dispatch-card-gate｜Wave: 2｜依赖: 无｜type: coding

## 上下文
coding 无任何归属记录：`write_scope:` 仅 8/343，全仓无按 worker 的文件改动记录（`spec.md` E5）。依据 `design.md` §3.1。

## 要求
1. 在 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts`（写/编辑工具执行处）与 `worker/worker-mode.ts`（工具事件落 trace 处）：每次 `write`/`edit` 成功即向该 worker 的 `trace.log` 追加一行机器可读事件 `[WRITE_FILE] path=<绝对或仓库相对路径>`（一次调用一行；失败不记）。
2. 在回收侧（可放 `worker/output-sections.ts` 之外的**本卡自有**位置，避免与 T-04 文件冲突 ⇒ 放在 `worker/output-writer.ts` 之外的 `shared/` 新文件 `shared/change-ledger.ts`）实现 `diffLedger(reportText, traceText): { declared[], recorded[], extra[] }`：解析报告「改动清单」的文件与 `trace.log` 的 `[WRITE_FILE]` 事件，返回差集。
3. 泄漏防护：`[WRITE_FILE]` 只记路径，不记内容；不得记录其他 key 路径以外的敏感内容。
4. 新增测试 `packages/coding-agent/test/suite/change-ledger.test.ts`：声明 ⊆ 记录 ⇒ ok；声明含未记录文件 ⇒ `extra` 非空（红）；无 `[WRITE_FILE]` 的历史 trace ⇒ 不判红（迁移兼容）。

## 交付格式
- 写入允许面：`worker/worker-file-tool.ts`、`worker/worker-mode.ts`、`shared/change-ledger.ts`（新）、`test/suite/change-ledger.test.ts`（新）。
- 写入禁止面：`worker/output-sections.ts`、`worker/output-writer.ts`（T-04 归属）、`pm/**`、`packages/multi-workers/**`、其他 key 目录。
- 回收判据：`node ../../node_modules/vitest/dist/cli.js --run test/suite/change-ledger.test.ts`（在 `packages/coding-agent` 下）全绿；既有 `test/suite/mwds-t02-write-intent.test.ts`、`test/suite/worker-dispatch-guard.test.ts` 不回归；报告含改动清单（本身即该机制的首次自证）。
