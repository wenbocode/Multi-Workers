# T-DR4: 检查点判据与看门狗不变量设计（research）

- Key: mw-worker-output-contract
- type: research
- 写面：只读仓库 + 写本任务目录与唯一证据文件

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（「Worker 超时看门狗（activity watchdog + 墙钟兜底）」「30 分钟收敛检查点」「goal.md 一致性追踪」）。
- 本 key 的 spec（**已锁定**）：`.agenticdoc/mw-worker-output-contract/spec.md` —— §1.5 P5、§1.6 S5、§3 **AC-009**、§4 R5/R9。
- 已确证的现状（**设计前提**）：`READ_TOOLS = {read,grep,find,ls,glob}` 与 `WRITE_TOOLS = {write,edit}`（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:260`）⇒ `worker_file`/`bash` **不计**，writeless 的 `writes=0` 恒真（**入参缺陷**）；`computeRisk`（`:283`）三支：`high` = 过锚点零写、`mid` = 过锚点 phases 停滞 **或** `repeatTop>=4`、否则 `low`；`checkpointAnchorMs`（`:250`）= `min(30m, max(1s, budget/2))`，之后每 10m 刷新，**只有时间触发**；升级路径 `pm/pm-orchestrator.ts:1417` → `deliverPmAlert` → `ui-bridge.ts:175` `{triggerTurn:true}`；idle(10m)/墙钟(默认 60m) 两段只吃 `lastActivityAt`/`budgetMs`（`worker-mode.ts:2591`–`:2624`、`:2650`–`:2654`）。
- spec 阶段研究证据（**必读**）：`evidence/research/spec-rq4-checkpoint-settle-20261014.md`（含 `wjg-w12` 反证工件：`[WRITE_FILE]`=4、`worker_file`=4、`[CHECKPOINT]`=1、`reads=111`、`writes=0`、`risk=mid`、37,149 B 产物已落盘、`exit=2`）。
- 只读边界：**不得修改仓库任何文件**；禁止 `npm install|ci`、`git checkout|reset|clean|stash`、`npm run build`、`npm run diff:model-catalog`、全量 `./test.sh`。

## 要求

1. **两条修法路径的决策**：(i) 修**入参**（把 `worker_file` 与壳层写入纳入计数）vs (ii) 改**判据**（改用落盘信号 + 产物存在性 + progress 完成记录）；给出选择 + 理由 + 混合方案的边界。若选修入参，说明计数来源是否与账本（D3）同源、如何避免重复计数。
2. **新判据的精确规格**：`computeRisk` 的替换/扩展规则（各分支的判据与阈值）；`writeless` 与 `write` 角色是否共用同一函数；对 6 个历史实例的预期 `risk` 变化。
3. **`[CHECKPOINT]` 行字段**：新增哪些字段（如「距上次落盘时长」「产物存在性」「通道」）、格式与既有解析器（若有）的兼容。
4. **不变量证明（必须逐条给证据）**：改动不得影响 idle 看门狗（10m）、墙钟看门狗（默认 60m）、deadline steer（预算尾段）；说明每条不变量的证据（读了哪段源码、哪个测试锁定它）。
5. **steer 文案**：writeless 分支的文案现状（`checkpointSteerText`）是否需要改，改什么。
6. **AC-009 的测试形态**：两个场景（已落盘 → `risk≠mid`；零落盘 → `≥mid`）各自的用例文件 + 夹具 + 断言；以及「3 例看门狗行为不变」的验证方式。

## 唯一证据文件

`.agenticdoc/mw-worker-output-contract/evidence/research/design-rq4-checkpoint-invariants-20261014.md`

用 `bash` + Python heredoc 直接写该路径；同时在**本任务目录**用 `worker_file` 写同内容 `report.md`。

## 交付格式

- `## 0. 结论与决策` → `## 1…N` 逐问 → `## 未覆盖面声明`。
- 每条判据 `文件:行号` + 原文片段；命令 + 输出；禁止推测补齐。
- 末尾一行 `[VERIFY] …`；写出方法边界与未覆盖面。
- `output.md` **必带 4 段标题**：`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
