# T-01 · 写面单一真源：`shared/write-surface.ts` + 三个薄适配层（W1）

- Key: mw-worker-output-contract
- type: coding

## 上下文

- 目标锚点：`.agenticdoc/goal.md`（「工具白名单按任务类型」「凭证隔离」「Worker 进程级隔离」）——本卡只动「谁能写哪条路径」这一条判定链，不改工具集表。
- 现状（**已确证，不要重复发现**）：同一路径在**派发期**与**运行期**判定相反。
  - 运行期允许面：`worker/worker-mode.ts` 中 `worker_file` 通道 + 壳层守卫允许 `taskDir + <key>/evidence/**`。
  - 派发期允许面：`pm/ui-bridge.ts` 的 `judgeWriteTarget` 只有「taskDir」+「无目录成分的白名单 basename」，**没有 `evidence/**` 面**。实测：review 卡声明写 `evidence/*.md` 在派发期被判不可满足。
  - 两个 `WORKER_FILE_NAME_RE` 共用点：`worker/worker-file-tool.ts:42`（通道自带 basename 白名单）与 `pm/ui-bridge.ts`（`!hasDirComponent` 通道）。
- 设计落点（`design.md` §3，逐字照办）：新增 `shared/write-surface.ts`，导出四个符号 —— `pmWriteDenyReason(target)`（deny 表 6 条，从 `ui-bridge` 迁入）、`isAllowedWorkerFileName(name)`（迁址后的 basename 白名单）、`resolveWriteSurfacePaths(ctx)` → `{ taskDir, keyDir, agenticdocRoot, projectRoot }`、`judgeWriteTarget(pathToken, ctx)`（**唯一谓词**：deny → taskDir → evidence 面 → basename → shape → fail-closed）。
- 三个调用点**退化为薄适配**（只转换入参类型，不做判定）：`worker/worker-file-tool.ts`、`worker/worker-mode.ts` 的 `checkBashWriteScopeTarget` 调用点、`pm/ui-bridge.ts::judgeWriteTarget`。
- 路径域语义（`design.md` §3.2）：基准**双接受**（project-root 相对 `.agenticdoc/<key>/evidence/...` 与 keyDir 相对 `evidence/...`）；允许面 = `taskDir` + `<key>/evidence/**`（`evidence/**` 不限制扩展名）；拒绝面 fail-closed（`../..`、其他 key、仓库源码、`.git`、`node_modules`）；`WORKER_FILE_NAME_RE` **不放宽**，只迁址 + 再导出；`write_scope:` **同时约束 `worker_file`**（今日零行为变化）。
- AC-007 的层级（`design.md` §3.3）：模型可见的 `Tool … not found` 由 pi 核心 `packages/agent/src/agent-loop.ts:611` 的 `kind:"immediate"` 分支生成，扩展改不到那段文本 ⇒ 验收只走 (a)「该错误不再产生」（卡面注入正确通道 + `worker_file` description 写明唯一通道）。
- 跨 key 热文件告警：`pm/ui-bridge.ts` 是多窗口热文件（并行 session 已使其行号漂移）。**一律符号锚定，禁止按行号定位**；开工前若发现该文件正被第三方编辑，停下并在「残留与未验证」报告，不要覆盖别人的行。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/write-surface.ts`（新建）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/deliverable-evidence.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
- `packages/coding-agent/test/extensions/agent-team-loop-worker-file-tool.test.ts`
- `packages/coding-agent/test/suite/mwoc-w1-write-surface.test.ts`（新建）

## 写入禁止面

其余一切路径。特别地：`worker/worker-mode.ts`、`pm/pm-orchestrator.ts`、`shared/change-ledger.ts`、`shared/heartbeat.ts`、`worker/output-*.ts`、`packages/multi-workers/**`、其它 test/suite 文件全部只读（本卡只改 `judgeWriteTarget` 所在的 `pm/ui-bridge.ts`，**不得**顺手动 `applyWatchWidget` 或任何 widget 渲染）。**禁止 `npm run check`**（全仓 `biome --write`，多会话破坏性）；**禁止**无文件参数的全量 vitest（P-032）。

## 要求

1. **建 `shared/write-surface.ts` 并让三处调用点退化为薄适配**：判定逻辑只能出现在新模块里；三个调用点不得保留各自的 deny 表 / basename 白名单 / 目录判定副本。若某调用点需要额外入参（如 `write_scope` 条目），由适配层转换后传入谓词，判定仍在谓词内。
2. **`evidence/**` 双基准**：`<key>/evidence/**` 必须同时接受 project-root 相对与 keyDir 相对两种写法（否则 AC-016 放行的订单在运行期写不成）。
3. **`WORKER_FILE_NAME_RE` 迁址 + 再导出，语义逐字不变**（`worker/worker-file-tool.ts` 与 `pm/ui-bridge.ts` 从新模块导入同一常量）。放宽它等于重开目录盲区，禁止。
4. **`write_scope:` 同时约束 `worker_file`**：默认面必须与 `renderDefaultWriteScope` 等价（零行为变化）；用测试证明默认情形无回归。
5. **AC-007(a)**：`worker_file` 的 description/提示文案写明「这是你的唯一写通道」，让 worker 不做无效尝试；不改 pi 核心。
6. **`research` 的窄通道行为逐字保持**：不要为保住 research 而写 `if (type === "research")`；用现有测试证明。
7. **测试**（新建 `test/suite/mwoc-w1-write-surface.test.ts`）：
   - `evidence/**` 两基准各 1 例成功；`../..`、其他 key、仓库源码各 1 例 fail-closed 且留 trace（对齐 AC-016 的 3/3 拒绝）。
   - 1 例 research 卡 + 1 例 review 卡的 `## 唯一证据文件`/写入面声明 `evidence/**` ⇒ 派发期判定可满足（当前 review 形态实测失败，这是本卡的核心红灯）。
   - 派发期与运行期**共用同一谓词**的机械证据：两处调用点都从 `shared/write-surface.ts` 导入（可用导入断言或行为对照测试），不得各写一份正则。
   - 任务目录内 basename 白名单既有用例 3/3 仍通过（AC-006）。
8. `git diff --stat` 收尾只应含允许面文件（工作区其它 session 的改动不算）。

## 交付格式

`output.md` 五段齐全（`结论`/`证据`/`残留与未验证`/`上下文来源`/`改动清单`）。`证据` 段给**可复跑的原始命令与原始输出**：新测试条数与逐条结果、`allow=2 deny=0` 类汇总前后对照（若涉及）、派发期/运行期同源证据、`research` 无回归的既有测试名单与条数。末尾一行 `[VERIFY] …`。

## 验收命令

```powershell
cd H:/git/Multi-Workers/packages/coding-agent
node ../../node_modules/vitest/dist/cli.js --run test/suite/mwoc-w1-write-surface.test.ts
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-worker-file-tool.test.ts
npx tsgo --noEmit
git diff --stat -- packages/coding-agent/src/extensions/agent-team-loop packages/coding-agent/test
```

（已知 `agent-team-loop-worker-file-tool.test.ts` 在 HEAD 有 **2 条既存红**（`worker-file-tool` 7/9，trace.log 污染）——报出基线即可，不要去修。现有 write_scope 相关套件请用 `rg -l "write_scope|writeScope|WRITE_SCOPE" test/` 定位后逐文件跑并列名单。）

## 改动历史

- 2026-10-14 spec 阶段 RQ-2 实测：派发期与运行期写面判定相反；`TOOL_ALLOWLISTS` 11 键、5 键无 `write`/`edit`；`activeToolsForType` 为这些角色追加 `worker_file`。design 阶段 DR1 裁决双基准、加 `evidence/**`、`WORKER_FILE_NAME_RE` 只迁址不放宽。
- PM 派发前实测：`pm/ui-bridge.ts` 与 `worker/worker-file-tool.ts` 在本卡开工时无活跃写者（见 run 时的 `git status` 复核）。
