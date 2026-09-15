# PM State: mw-worker-timeout-convergence

## Section 1: Snapshot

- Key: mw-worker-timeout-convergence
- Claim-Id: —
- Phase: DONE
- Updated: 2026-09-09 16:59
- Completed: 2026-09-09 16:59

## Section 2: Execution Log

- 2026-09-09 15:0x-15:3x 需求与设计两轮对话定稿：用户 OverCode 取证（4 超时 worker 两模式）+ 方案 B+A+C 采纳 + 收敛检查点新增要求（超 30m 必须有执行日志收敛判据；发散分拆判断归 PM 主窗口）。research/spec/design/plan 落盘（AC-001..006，VC-001..006）；switch_key 认领
- 2026-09-09 15:3x-16:0x 实现 T-01~T-05：heartbeat.ts [CHECKPOINT] 解析（TaskProgress.checkpoint）；output-writer appendCheckpoint + appendTimeout(kind,detail)；worker-mode 预算解析（resolveBudgetMs/resolveIdleMs/checkpointAnchorMs/steerAtMs 导出）+ 全事件 touch 活动跟踪 + idle interval + wall timer + checkpoint 调度（10m 刷新）+ 双 steer + 读写信号计数 + computeRisk（high/mid/low）；ui-bridge deliverPmAlert 抽取（deliverWorkerResult 复用）；pm-orchestrator 运行行 ck 徽标 + mid/high 一次 triggerTurn 升级 + PM_CONTINUE_HINT 超时分支（wall→双倍预算重派一次，idle→排查环境）
- 2026-09-09 16:01 T-06：vitest 83/83（+10 新：预算优先级/阈值/锚点与 steer 时刻公式/parseTaskMd timeout/computeRisk 三分支/appendCheckpoint 往返/appendTimeout 双 kind/widget 徽标含 ⚠/升级一次且 low 不扰/跨 key 隔离）；biome 本 key 零告警
- 2026-09-09 16:0x T-07：npm run check 全仓 580 = 既有基线（零交集），本 key 零错误；bundle 重建安装 + dist 重建（built-in 后备同步，方案 A 纪律）
- 2026-09-09 16:0x S3 实跑 Run 1（sleep 100）：checkpoint 60s 锚点/risk=high/wall 120s 判据/output.md exitReason/队列 failed 全中；**发现 steer 投递缺陷**（agent 运行中裸 sendUserMessage 抛 "Agent is already processing"，两 steer 未送达）→ 修复：checkpoint→deliverAs followUp、deadline→deliverAs steer
- 2026-09-09 16:1x S3 实跑 Run 2（sleep 70，修复后）：全路径 PASS——checkpoint steer 落地为 followUp turn、自评写入 progress.md（CKPT converging=yes）、deadline steer 注入在途 turn、**agent 预算耗尽前自行收尾 exit=0 elapsed=110s**、worker.log 零 Extension error；证据 evidence/runs/smoke-watchdog-2026-09-09.md
- 2026-09-09 16:4x 质检门禁（用户触发）：发现两个覆盖缺口并当场补齐——集成测试 ×4（idle 60s 精准杀/delta 滴流 200s 不杀/多 phase 存续 phases=0/2/小预算下 checkpoint→deadline steer→wall 顺序 + deliverAs 选项断言）；套件 87/87（本 key 新增 14）、biome 全绿、check 580=基线零交集；报告 evidence/quality-gate-report-2026-09-09.md，结论 ✅ 通过，验证欠债 3 项（PM 升级实机首验待窗口重启、idle 阈值收紧待流式确认、模板完全对齐待闲时）
- 待办：用户重启 pi 窗口后，PM 升级（AC-004 triggerTurn 唤醒）在真实长任务上的首验；OverCode 侧大任务按新协议重派观察

## Section 3: Notes

- gc/docs：goal.md GC-4 约束行已按 D-2026-09-09-1 修订（activity watchdog + 墙钟兜底 60m + per-task timeout + 30m 收敛检查点）
- Python 侧零改动（AC-006）：doctor 仍前缀锚定 [HEARTBEAT]，新行纯增量；PI_WORKER_TIMEOUT_MS 语义降级为全局默认（task.md timeout: 优先）
- 2026-09-09 23:59: 恢复复验轮：事故后会话日志重放恢复、bundle 字节一致、vitest 90/90（含本 key 14 用例）；补齐 6 项文档形态债（§0/前馈两节/spec-*与design-*调研留底/tasks/ 拆分 8 文件）使 audit 转 PASS
