# Plan: mw-worker-timeout-convergence

> 单 stage 串行执行（改动集中于一个扩展子系统，无跨包依赖）。

## S1 实现（T-01~T-05）

- T-01 heartbeat.ts：readTaskProgress 解析 [CHECKPOINT]（最后一行）→ TaskProgress.checkpoint（ac: AC-004, vc: VC-004）
- T-02 output-writer.ts：appendCheckpoint + appendTimeout(kind, detail) 签名扩展（ac: AC-001/004, vc: VC-001/VC-005）
- T-03 worker-mode.ts：预算解析（task.md/env/默认 60m）、事件 touch 活动跟踪、idle interval + wall timeout、checkpoint 调度（min(30m,budget/2) + 每 10m）、两处 steer（自评/收尾）、信号计数器、risk 启发式（ac: AC-001/002/003, vc: VC-001~VC-003）
- T-04 ui-bridge.ts + pm-orchestrator.ts：deliverPmAlert 抽取；poll 循环 checkpoint 徽标 + mid/high 一次升级；PM_CONTINUE_HINT 超时分支（ac: AC-004/005, vc: VC-004/VC-006）
- T-05 parseTaskMd timeout 头（并入 T-03 文件，独立提交点）

## S2 验证（T-06~T-07）

- T-06 vitest 新用例 + 全量 agent-team-loop 套件零回归（ac: 全部, vc: VC-001~VC-006）
- T-07 npm run check（本 key 零错误）+ bundle 重建安装（mw build --install）

## S3 实机（T-08，可选）

- 小预算烟雾：timeout: 2 头 + PI_WORKER_IDLE_MS=20000 验证 wall/idle/checkpoint/steer 全路径实跑

## VC 清单

- VC-001 idle 判真挂死：无活动超阈值被杀，[TIMEOUT] 带 idle 判据
- VC-002 墙钟兜底：预算耗尽被杀，[TIMEOUT] 带 wall 判据 + exitReason
- VC-003 预算优先级与 steer 时刻：task.md > env > 默认；steerAt 公式
- VC-004 checkpoint 落盘与升级：[CHECKPOINT] 字段齐全；mid/high 触发一次 triggerTurn 升级；low 仅 widget
- VC-005 格式兼容：既有行不变，新行纯增量，Python 解析零依赖
- VC-006 widget/回读：运行行徽标；终态摘要含超时重试指引
