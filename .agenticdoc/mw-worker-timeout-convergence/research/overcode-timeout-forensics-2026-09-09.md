# Research: OverCode worker 超时取证（用户分析留底）

> 日期：2026-09-09
> 来源：用户在 E:\CLI_workspace\OverCode 项目（key certify-parsed-reuse）对 4 个超时 worker 的 harness 源码 + trace 时间线取证。本文为原始分析留底，作为本 key 的需求证据。

## 直接机制

worker-mode.ts watchdog（30 分钟默认，PI_WORKER_TIMEOUT_MS 可调）：mw 监听 agent_settled，超时未 settle 即强杀——"No response after 1800000ms"。

## 两种超时模式（4 个 worker）

### 模式 A：真干满 30 分钟被杀（cpr-004、cpr-005）

| worker | 工具调用 | 特征 |
|---|---|---|
| cpr-004 | 196 次（100 bash + 74 read + 12 write） | 每分钟有活动，最后工具调用在被杀前 28 秒——还在干活 |
| cpr-005 | 152 次（78 bash + 38 read + 26 写改） | 活跃到被杀前 9 秒——代码已完成，死在收尾验证/文档阶段 |

纯预算不足，全程无挂死。

### 模式 B：停止工具调用但未 settle（cpr-003、cpr-007）

| worker | 静默尾巴 | 特征 |
|---|---|---|
| cpr-003 | 4 分钟 | 代码+42 测试已完成（事后全绿）；生成最终长报告时被杀。另有 7 分钟活动空窗（≈ parsed_store.py 大文件单次超长模型调用） |
| cpr-007 | 7.75 分钟 | 22 分钟 128 次调用全是读/查，零写；读完全部 7 份必读材料后开始生成 ~300 行实现，生成在途直到 watchdog 到点 |

心跳在静默期持续 = 进程活着、模型 API 调用在途——watchdog 注释里的 "network hang" 场景与慢生成不可区分。

## 根因归纳（用户）

1. 30m 固定预算太小，校准于小任务（成功样本 9m/13m/7m/14m 全是小/中任务；失败的恰是四个最大实现任务）
2. 模型延迟是墙钟放大器（glm-5.3 远程 API：大文件单次生成数分钟、长报告收不了尾、大实现一次生成直接超窗）
3. dispatch 设计放大 T007：7 份必读材料要求全读后开写，慢模型下读阶段吃掉 22/30 分钟

## 用户已做的处置（OverCode 侧）

大任务转 PM 直执（T007 已收）、dispatch 带时间预算指引、"20 分钟节点先写执行记录"。

## 本 key 的对策映射

- 模式 A → AC-002（per-task timeout 头）+ AC-003（deadline steer 提前收尾）
- 模式 B → AC-001（activity watchdog：token 增量区分慢生成与真挂死）+ 墙钟兜底上调
- "死在收尾" → AC-003 deadline steer
- 发散风险 → AC-004（30m 收敛检查点 + PM 升级判断）
