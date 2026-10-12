# T-07 — TS 三解析器切换到单源（首个 `type:` 胜出）

- key: `mw-guard-form-hardening`｜基线 commit: `ab546bb64`｜角色: **coding**
- **唯一权威**（不得改写、不得凭记忆猜测）：`design.md` §§4.4.2（6 份解析器矩阵）+ §4.4.4（fail-closed 范围 PM 裁定）（含 L1–L18 落点总表与 VC 定义）+ `spec.md` AC-005 + 下列证据文件
- 证据: `evidence/research/design-role-key-identity-20261011.md` §2/§3（矩阵 + fail-closed 规则 + 存量影响）
- **唯一允许改的路径**: `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`；`packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`；`packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`；`packages/coding-agent/test/extensions/agent-team-loop.test.ts`；外加自身目录 `report.md`
- 禁止: 运行 `npm run check`/全量 vitest/`mw build`/`mw.py build`（PM 负责）；修改 `design.md`/`spec.md`/`plan.md`；改本卡未列出的文件；删既有测试用例（只能新增或按下卡明示修订）

## 卡元信息
- AC: AC-005｜VC: VC-020…VC-023｜波 3｜链 S3（依赖 T-06）
- 验收命令（PM 执行）: `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts test/suite/autopilot-protocol.test.ts test/suite/task-frontmatter.test.ts`

## 必须实现
1. `worker/worker-mode.ts::parseTaskMd` 改用 `shared/task-frontmatter.ts`；**首个 `type:` 胜出**（正文行不得覆盖）。
2. `pm/task-dispatcher.ts` 与派发侧 `resolveDispatchType` 复用同一函数（派发期判据与执行期角色同源）。
3. `autopilot/status-model.ts`：共享边界提取，但**保留其 fenced-only 语义**（不得顺手统一）。
4. **fail-closed 范围（PM 裁定，覆盖任何更宽方案）**：仅对**带 origin 标记**（派发）任务在 `type:` 缺失/非法时拒绝；**无标记**（手工/冒烟）任务保持现行为 + 审计行 ⇒ `test/suite/autopilot-protocol.test.ts:346-362` **不得改写**（T-13 零拦截契约不变），只允许新增 origin 标记用例。
5. 存量具名：`.agenticdoc/mw-worker-tree-kill/workers/review-mw-worker-tree-kill/task.md`（头 `coding` / 正文第 3 行 `review`）⇒ **现状（last-wins）角色 = `review`；修后（首个 `type:` 胜出）角色 = `coding`** —— 即 `flip` 的具名方向是 **review → coding**（PM 勘误：本卡初稿把方向写反）。用例必须固化「修后 = `coding`」并额外断言「正文行不得改变角色」，因为正文可写即等于角色可自我改写（这正是 A8 洞）。注意该文件是**历史**产物，本次修的是判据而非该文件。
6. 断言：全量语料（当前 311 本，会增长）上 `flip == 0`（前值 1，具名）。**不得**写入语料计数上限。
7. **签名适配（T-06 实测）**：`shared/task-frontmatter.ts` 的 `readTaskType(text)` 返回 **对象** `TaskTypeReading`（含 `type` / `source` / `bomStripped`，`source ∈ {header, body, missing, invalid}`），不是字符串——调用侧按 `.type` 取值，并按 `source` 决定审计措辞；`extractTaskHeader` 返回 `TaskHeaderRegion`，`scanBodyTypeLines` 返回 `TaskBodyTypeLine[]`。模块 **零 import 纯函数、不抛异常**，不得在其上加重试/兜底逻辑。

## 交付
- 唯一写入（除源码/测试外）= `worker_file file="report.md"`、`mode="append"` 追加、`mode="write"` 覆盖；禁止其它路径。
- `report.md` 必须含：改动文件清单、前后行为对照表（输入/期望/实测）、红→绿证据、未完成项与原因（若有）。
