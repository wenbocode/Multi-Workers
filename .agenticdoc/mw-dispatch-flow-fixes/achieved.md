# Achieved: mw-dispatch-flow-fixes

> 完成日期：2026-09-09
> 质检：✅ 通过（evidence/quality-gate-report-2026-09-08.md Round 2 + Round 3 恢复复验）

## 交付了什么

修复 mw worker 派发链路（16 AC），全部在 agent-team-loop 扩展 + 框架脚本内：

1. **归属与队列（AC-001/002）**：owner 解析以激活 key 为准，task 落 `{key}/workers/`；watch 不一致一次同步一次告警；`activeKey()` 改为最新 updated 的 active 行 + `_index.md` 兜底（`readIndexMdActive`）
2. **心跳与活性（AC-003/004）**：worker 侧 ≤60s 结构化 `[HEARTBEAT]` 条目（`heartbeat.ts`，30s 间隔/90s 陈旧，与 doctor 双侧常量互指）；doctor `worker_liveness` 三判定（alive/stale/no-heartbeat）+ 阈值可配
3. **路由（AC-005~009）**：协议 additive（既有 61 用例零变更）；无凭证环境 review 默认 pi/timi 完成；显式 claude 保留且缺凭证隔离不降级
4. **门禁与播报（AC-010/011）**：phase-docs gate 仅评有未入队任务的 key；终态播报按窗口认领 key 过滤
5. **widget（AC-012/013）**：watched key 心跳进度 monitor（三态行）+ 终态摘要附心跳统计
6. **claim 协议（M1~M4）**：原子 claim（单锁 + 写后验证 + 双窗竞争测试）、restoreWatch 静默重绑、Z 后缀归一、跨写者 host:pid 协议对齐框架（update_index.py，已推 58f20f7）
7. **终态交付（AC-014/015/016）**：`readOutputBody` 全文回读（≤20k 截断指路）；终态消息 `triggerTurn: true` 驱动 PM 循环继续；worker.log 三段俱全（含 stale built-in 根因修复：dist 重建消除 `exitWithSuccess` 抢杀与挂死，双载防护 ACTIVATION_FLAG——详见 mw-stale-builtin-fix archived key）

## 目标如何达成

- 验证三层：vitest 90/90（含 M1/M2 原子性与静默重绑、VC-001~020 全映射）；mw pytest 121（doctor liveness ×4 + 隔离 8 用例）；L2 实跑 + smoke-ac016b 实机（worker.log 三段 + 裸 `pi -p` 4.1s 自然退出）
- 2026-09-09 晚恢复复验（Round 3）：工作区经历 worktree junction 删除事故后按会话日志重放恢复，重建 bundle 与事故前 SHA256 字节一致；dist 全量重建后 `exitWithSuccess` 0 处 / `finishSuccess` 3 处 / ACTIVATION_FLAG 在位 / 裸 `pi -p "Say exactly: ok"` 5s 自然退出；audit_phase PASS

## 遗留

1. **AC-015 实机首验**：需 pi 窗口重启加载新 bundle 后首次观察（triggerTurn 代码路径已由 VC 测试覆盖；tmux 在本机不可用，无法无头实机验证）
2. **mw serve 旧 launcher**：运行中的 serve（PID 62804，08-28 启动）仍携带 9-5 之前的 argv 传任务体行为；mw.py 修复已提交（357296d89），建议 `mw stop && mw start`
3. **W-1 全仓 TS 基线**：既有 packages/ai models 域错误（580→26，数据重拉后收敛），与本 key 无交集，另开 key 处理
