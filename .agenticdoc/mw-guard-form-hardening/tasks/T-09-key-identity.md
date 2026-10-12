# T-09 — key 豁免 14 名 + 读侧归一 + `_index.md` 回退 + 守卫无条件

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.4.5（key 身份定稿）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-006 + 下列证据文件
- 证据: `evidence/research/design-role-key-identity-20261011.md` §4/§5（豁免清单 + 归一 + 回退 + 调用行约束）；`evidence/research/spec-key-identity-20261011.md`（A5/A6/A7 实测）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`；`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`；`packages/coding-agent/test/suite/worker-crosskey-readonly.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-006｜VC: VC-024…VC-028, VC-043, VC-044｜波 3｜链 S3（依赖 T-04）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/worker-crosskey-readonly.test.ts test/suite/worker-dispatch-guard.test.ts test/suite/index-store.test.ts`

## 必须实现
1. 豁免改为**显式 14 名常量清单**（RQ-5 的 12 名 + `_impl_gate.log` + `_incidents`）；`_`/`.` 无条件豁免分支删除。
2. 「新 key 引导路径」判据 = `findByKey === undefined`；`advance_phase`（`ui-bridge.ts` 约 `:2045`）与 `claim` 的放行**方向一致**（不得一处拒绝一处放行）。
3. `shared/index-store.ts` 三处读侧（`:73`/`:101`/`:164-166`）大小写归一：保首写大小写、**不迁移存量**；`:101` 不得再追加重复行。
4. `_index.md` 回退（`ui-bridge.ts:82`）**必须补 `claimState` 检查**（今日快照即满足该前置）。
5. `dispatch_worker` 侧守卫改**无条件**，但必须保留 3 个调用行（否则 `test/suite/mwds-t01-*.test.ts:269-272` 变红）。
6. 测试：`exempt_live_key=0`、`case_mismatch_bypass=0`、14 名逐名用例、`_tmp` 形式活 key 被拒、回退路径不产生「活窗口判未持有」。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
