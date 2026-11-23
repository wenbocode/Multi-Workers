# 两个 DP key 的合并验收

本次合并覆盖 `mw-dp-call-policy` 和 `mw-dp-material-pipeline`。两者的权威索引均为 `DONE / idle`，认领为空。

| 验证 | 结果 |
| --- | --- |
| 调用策略与材料入口的五组 TypeScript 回归 | 118 项通过。覆盖常规 gate 路由、任务卡类型、Codex PM 入口、决策材料和 Worker 入口。[日志](release-typescript-core.log) |
| 材料链路、受限 Prepare Worker、配对、Monitor、本地与正式签收的九组 Python 回归 | 254 项通过，1 项跳过。[日志](release-python-acceptance.log) |
| PM 正常入口传输结果未知 | 首次请求 1 次。同一材料再次提交和重建 PM 会话后均为 0 次，复用原阻塞事件。[回放](release-replay.log) |
| 全量静态检查 | 隔离候选运行 `npm run check`。检查时临时应用共享工作树中已有的 `agent-team-loop-pm-state.test.ts` 参数修正，结束后恢复该测试，该修正未随这两个 key 提交。[日志](release-check.log) |

八个 DP 的 v0.5 冻结设计和原始请求、原始返回保留原字节，现有 [九例四段对账](../../../mw-dp-material-pipeline/evidence/acceptance/ac003-local-budget/v05-four-stage-comparison.md) 仍是材料验收入口。此次提交补齐了传输结果未知时的回执读取、受限 Prepare Worker 启动器和 Monitor 的候选校验。

扩展回归还跑了旧合同的样例。其中 35 项 Python 和 1 项 TypeScript 失败，包含旧模型输入预期、旧 dp-auto 比较材料及签收样例缺当前独审。对应旧测试的未完成调整仍留在原工作树，未纳入本次发布验收。
