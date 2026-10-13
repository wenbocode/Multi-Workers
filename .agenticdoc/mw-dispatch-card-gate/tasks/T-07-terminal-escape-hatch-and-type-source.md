# T-07 终态翻转 + 逃生舱真读 + `type:` 单一来源

- Key: mw-dispatch-card-gate｜Wave: 3｜依赖: T-02、T-05（均改 `worker-mode.ts` 之后）｜type: coding

## 上下文
三处缺口在 W1/W2 被显式挂起，均由本卡收口：
1. **AC-003 只完成一半**：T-04 已实现 `checkRecovery` 并把缺失段名写入读回信息，但**无法翻转 run 终态**（缺段仍为 `done`）—— 翻转需要写 `worker/worker-mode.ts`，而该文件在 T-04 卡里被划给 T-05（`evidence/…/mwd-t04-recovery-contract/report.md` 的 PM 裁定项）。现状仍会出现"内容缺段却判 done"，即本 key 要治的原始病症之一（`spec.md` E4）。
2. **逃生舱形同虚设**：`allow_foreign_write: true` **只写不读**（TS/Python 均无消费者，`evidence/research/spec-dispatch-path-20261012.md` ②），不满足 AC-007。
3. **`type:` 判据多源**：工具层收 5 值、worker 运行时认 10 值 + fallback（`spec.md` §8 P-08）；T-01 的 `shared/dispatch-card.ts` 因叶子层约束自带了一份私有 type 解析（其 `report.md` 已请 PM 裁定）。
4. **AC-005 的验证面**：`review` 角色需具备 bash 以执行验证（上一 key 实测：`type=review` 无 bash ⇒ 只能静态推演、返工重派）。

## 要求
1. **终态翻转（AC-003 收口）**：在 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts` 中，当 `checkRecovery`（T-04 已落地）判定缺段时，把该 run 的终态由 `done` 翻为 `needs-clarification`，并在读回体的 `## Questions` 首行**指名缺失段**。
   - 迁移兼容：无 `type:` 头或无 `task.md` ⇒ **不判**（不得把历史派发一次性判红，见 `spec.md` P-09）；
   - 不得通过放宽既有测试期望值来实现；既有测试若断言"缺段仍 done"，须改断言并在报告说明理由。
2. **逃生舱真读（AC-007 收口）**：为 `allow_foreign_write`（及其等价声明）实现**真实读取点**：声明为真时放行并在 `trace.log` 追加审计行（形如 `[ESCAPE_HATCH] allow_foreign_write=<task_key> target=<path>`），声明缺失或为假时按 fail-closed 处置；两侧（TS 判定与 Python 服务层）行为一致，并在测试中固定。
3. **`type:` 单一来源（P-08 收口）**：把 `shared/dispatch-card.ts` 的私有 type 解析替换为**单一来源**（不改变其对外导出与 `readEnvelope` 语义），并让工具层收值与 worker 运行时识别的词汇表**同一份常量**；`verifier`/`repair`/`phase-writer` 等既有在用值必须保留可用（不得为了收口而拒绝现实中在用的类型）。词汇表数值须**从真实语料枚举**（`tasks/*.md` 与 `workers/*/task.md` 的头部区 + `trace.log [START]` 记录；RQ-2b 已给 coding 219 / research 94 / review 28 / vision 1 / 缺失 1），并**必须覆盖 T-02 实测会命中 `unknown-type:codex` 的 legacy 值**（否则 G-1 会误拒——这属于 P-03 过拦违约）。
4. **`review` 验证面**：在 `.mw/dispatch.yml` 的角色默认中确认 `review` 具备 bash（用于执行验证命令）；若配置在别处定义，改为写入该处并在报告指明。
5. 新增测试 `packages/coding-agent/test/suite/dispatch-recovery-terminal.test.ts`：缺段 ⇒ 终态 `needs-clarification` 且首行指名段名；齐备 ⇒ `done`；无 `type:` ⇒ 不判；逃生舱真读 ⇒ 审计行出现且放行；无声明 ⇒ 拒绝。
6. **改动清单 ⊆ 事件 的接入点**（T-05 报的残留，PM 裁定归本卡）：在 `worker/output-writer.ts` 的终态落盘处调用 `shared/change-ledger.ts` 的 `diffLedger`；存在差集时把差集写入读回体（段名 `## Ledger Gaps`）并**并入第 1 条的终态判据**（有差集 ⇒ `needs-clarification`）；无任何 `[WRITE_FILE]` 事件的历史 trace ⇒ `extra=[]`，**不判红**（迁移兼容）。

## 交付格式
- 写入允许面：`worker/worker-mode.ts`、`worker/output-writer.ts`（T-04 已终态，归属移交本卡）、`shared/dispatch-card.ts`（T-01 已交付，可改但须保持导出兼容）、`.mw/dispatch.yml`、`test/suite/dispatch-recovery-terminal.test.ts`（新）。
- 写入禁止面：`worker/output-sections.ts`（T-04 归属，只读）、`worker/worker-file-tool.ts`（T-05 归属）、`pm/ui-bridge.ts`（T-02 归属）、`packages/multi-workers/launcher.py`（T-03 归属）、其他 key 目录、`.agenticdoc/**`（除本 worker 目录）。
- 交付物：上述改动 + 测试；`report.md` 含结论/证据（原始命令与输出）/改动清单/残留与未验证/上下文来源清单。
- 回收判据：
  - 验收命令（在 `packages/coding-agent` 下）：`node ../../node_modules/vitest/dist/cli.js --run test/suite/dispatch-recovery-terminal.test.ts test/suite/output-recovery-contract.test.ts test/suite/dispatch-card-envelope.test.ts` 全绿；
  - 另跑 `test/suite/mwds-t02-write-intent.test.ts`、`test/suite/worker-dispatch-guard.test.ts` 不回归；
  - 报告改动清单 ⊆ `trace.log` 的 `[WRITE_FILE]` 事件（T-05 机制，本卡起生效）；
  - 三条收口各自给出**反例**证据（缺段翻转、无声明拒绝、词汇表在用值仍可用）。
