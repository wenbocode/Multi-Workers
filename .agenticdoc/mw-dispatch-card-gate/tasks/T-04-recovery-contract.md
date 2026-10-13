# T-04 回收契约（output.md 五段 + 状态判据）

- Key: mw-dispatch-card-gate｜Wave: 1｜依赖: 无｜type: coding

## 上下文
4 个 worker 中 3 个内容齐全却因 `output.md` 只有占位段被判 `needs-clarification`（本会话工人回读记录；`spec.md` E4）；交付格式与回收判据未成文。依据 `design.md` §3.2。

## 要求
1. 在 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts` 定义并导出回收契约：
   - `RECOVERY_SECTIONS = ["结论","证据","残留与未验证","上下文来源"]`，`coding` 追加「改动清单」、`review` 追加「未覆盖面声明」；
   - `checkRecovery(text, type): { ok, missing[] }`（宽档，同 T-01 词表风格）。
2. 在 `worker/output-writer.ts`：落盘前用 `checkRecovery`；缺段时**不得**只落占位段 —— 须把缺失段名写入读回信息，使终态判为 `needs-clarification` 且**指名缺失段**（现状是笼统判"only placeholder sections"）。
3. 迁移兼容：既有历史派发不回溯判红；仅对新派发生效。
4. 新增测试 `packages/coding-agent/test/suite/output-recovery-contract.test.ts`：齐备 ⇒ `done`；缺某段 ⇒ `needs-clarification` 且读回文本含该段名。

## 交付格式
- 写入允许面：`worker/output-sections.ts`、`worker/output-writer.ts`、`test/suite/output-recovery-contract.test.ts`（新）。
- 写入禁止面：`worker/worker-mode.ts`（T-05 归属）、`pm/**`、`packages/multi-workers/**`、其他 key 目录。
- 回收判据：`node ../../node_modules/vitest/dist/cli.js --run test/suite/output-recovery-contract.test.ts`（在 `packages/coding-agent` 下）全绿；既有 `test/suite/*output*` 不回归；报告含改动清单。
