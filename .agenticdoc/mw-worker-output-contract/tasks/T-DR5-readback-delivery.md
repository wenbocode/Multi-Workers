# T-DR5: 终端回读推送域修复设计（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「PM Agent 管理多个 Worker 并行开发」「文件驱动的去中心化协调」）。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— §1.5 P6、§1.6 S6、§3 **AC-011 / AC-012 / AC-013**、§4 R5/R6。
- 已确证的现状（**设计前提**）：`pm/pm-orchestrator.ts:1434`–`1475`：`notified.has(taskKey) || !isTerminal(status)` → `notified.add(entry.taskKey)`（`:1436`）**早于** owner 门禁 `continue`（`:1440`）⇒ C1（owner 不匹配）与 C3（`!watch.key`）被混为一谈；`recordWriteScopeResidualRisks`（`:1448`）与 `readOutputBody`（`:1457`）都在门禁之后；`notified` 兼作 `recordWriteScopeResidualRisks` 的「每任务一次」界（源码注释明写）。探针 `P4` 是绝对值断言 `step4 === 1`（修复后必然变 2，属**断言债**）；既有测试锁：`packages/coding-agent/test/extensions/agent-team-loop.test.ts:2053`–`2085`，其中 `:2077` 断言「无 watch key 期间不得复活终态行」。`ackStore`（`shared/ack-store.ts`）持久化 `taskKey | ackedAtIso`，poll loop 只用它渲染 widget。
- spec 阶段研究证据（**必读**）：`evidence/research/spec-rq5-readback-push-20261014.md`（含 11/11 自然实验、探针断言全文、既有测试约束）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。

## 要求

1. **C1/C3 拆分的最小改法**：给出改动后的代码形态（顺序、条件、变量），并证明既有断言 `:2077` 仍通过（C3 = 继续记账 + 保持静默；C1 = 不记账）。
2. **补推语义**：`ackStore` 未 ack 是否触发补推；**去重键**候选（`notified` 进程内 Set / `ackStore` 的 `taskKey|ackedAtIso` / `WorkerEntry` 无 run 字段的现实）逐条给代价，并给出推荐 + 多窗口与多 run 的行为说明（spec 列为 R6 未验证项）。
3. **`recordWriteScopeResidualRisks` 的界**：修复后如何保持「每任务一次」，避免每 tick 重放；给代码形态。
4. **AC-011 的 P4 断言改写方案**：改写为 `had("b2")` 或 `step4 === step3 + 1` 的具体 diff；以及「P3 必须恰好补推 1 次」的判定方式。
5. **AC-012 的 C2 机械判据**、**AC-013 的无 watch key 未读数**：给出可机械判定的表述 + 实现点。
6. **测试形态**：AC-011/AC-012/AC-013 各自的用例文件（候选 `packages/coding-agent/test/suite/mwoc-t01-*.test.ts`）+ 夹具（复用 `agent-team-loop.test.ts:148/1939/1970/1987` 的写法）+ `vi.useFakeTimers()` 的必要性；并说明是否**不需要** faux provider。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq5-readback-delivery-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写同内容 `report.md`。

## 交付格式

- `## 0. 结论与决策` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；命令 + 输出；禁止推测补齐。
- 末尾一行 `[VERIFY] …`；写出方法边界与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
