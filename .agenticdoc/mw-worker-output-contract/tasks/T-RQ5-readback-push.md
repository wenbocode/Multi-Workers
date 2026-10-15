# T-RQ5: 终态回读推送范围缺口（C1/C2/C3）复核与用例化形状（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「PM 编排 + Worker 执行」「文件驱动的去中心化协调」）。
- 本 key 的 spec：`.agenticdoc/mw-worker-output-contract/spec.md` —— 相关条目 §1.4（纳入声明）、§1.5 P6、§1.6 S6、§1.7 第 6 条、§3 AC-011/AC-012/AC-013、§4 风险 R5/R6。
- **已并入本 key 的既有证据（先读这两份，不要重新发现）**：
  - `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-gap-20261014.md`（14,191 B；结论：`notified.add` 早于 owner 门禁 ⇒ 非 watch key 的终态行被永久记账为已推送；探针决定性复现 + 11/11 自然实验）
  - `.agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-repro-20261014.mts`（5,197 B；合成探针，构造真实 `startWorkerPollLoop`）
- 已知起点坐标（**只是起点**）：`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:1440`（owner 门禁 `if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;`）、同文件 `:1436`（`notified.add(entry.taskKey)`）、`:1349-1357`（开窗基线）、`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:176-189`（`deliverPmAlert` → `pi.sendMessage(..., { triggerTurn: true })`）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、全量 `./test.sh`。可以运行探针（`node .agenticdoc/mw-worker-output-contract/evidence/readback-push-scope-repro-20261014.mts`，它只写临时树并在退出时删除）。

## 要求

1. **复核 C1 的两处锚点现状**：`notified` 的声明位置与生命周期（进程级 Set 还是持久化）、`:1434-1440` 的实际代码（贴原文）、`entry` 的字段来源（`ownerKeyOf` 如何解析 key）、以及轮询间隔常量的位置。
2. **`startWorkerPollLoop` 的全部投递/抑制分支**：把该函数里所有「不投递」与「投递」的分支逐条列出（含开窗基线、owner 门禁、无 watch key、gate reminder 的独立 watermark 机制、`triggerTurn` 合并路径、ack 相关分支），每条给 `文件:行号` + 判定条件。这是本 RQ 的核心清单。
3. **`ackStore` 的语义位置**：已 ack 标记存在哪、谁读写、与 `notified` 的关系（是否等价、是否持久化）——决定「未 ack 即补推」是否与既有语义冲突（AC-012 的前提）。
4. **用例化的可行形状**：给出把探针转成 `packages/coding-agent/test/suite/` 下回归用例的**具体形状**：可复用的 harness / faux provider / 假 `pi` / 临时 `.agenticdoc` 根构造点（逐条 `文件:行号`），以及用例断言应怎么写（`P1`…`P6` 对应到测试名与断言）。**不要写实现代码，给形状与落点。**
5. **反证条件的可执行化**：报告 §5 给出的可证伪预测（把记账移到门禁后 ⇒ `P3` 由 `saw b1=false` 变 `true`，`P1/P2/P4/P5/P6` 不变）——请核对探针里这几条断言的实现位置，确认它们**确实能区分** C1 与 C2/C3；若某条断言在修复后也会翻转，明确指出（否则 AC-011 的闸门不成立）。
6. **无 I/O 放大的确认（R5）**：确认判定分支（不投递的那条 `continue`）是否需要读 `output.md` body；给出代码证据（`readOutputBody` 之类调用的位置与它在分支中的先后），说明记账后置后每 tick 的开销面。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/spec-rq5-readback-push-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写一份同内容 `report.md` 作为 PM 回读兜底。

## 交付格式

- `## 0. 结论先行`（≤6 条）→ `## 1…N` 逐问作答（第 2 问必须是完整分支清单，第 4 问必须是可直接落 tasks 的用例形状）→ `## 未找到清单` → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；探针相关结论给出**实际运行命令与输出**（贴 `VERDICT` 行与 P1…P6 结果）。
- 未找到写「未找到（命令 + 输出）」；**禁止推测补齐**（本条的母报告已声明其未覆盖面：多窗口同 key、`triggerTurn` 合并比例、gate reminder 通道、C2 产品判断）。
- 末尾一行 `[VERIFY] <数值> …`；声明工具与方法边界（能否实跑探针）。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
