# L2 Smoke: watchdog + convergence paths (AC-001..004) — 2026-09-09

两次实跑（mw serve 全局队列派发，pi/timi，任务 `timeout: 2` → budget 2m、checkpoint 锚点 60s、deadline steer 90s、墙钟 120s）。

## Run 1（发现 steer 投递缺陷）

任务：单次 `bash sleep 100` 后回复。结果：

- `[START] 08:05:38` → `[TOOL] bash sleep 100` → **`[CHECKPOINT] elapsed=60s reads=0 writes=0 risk=high`（锚点精准命中）** → `[TIMEOUT] wall: budget 120s exceeded (last activity 6s ago)` → `[END] exit=1 elapsed=120s tools=1`
- output.md Exit Reason：`wall timeout: budget 120s exceeded (last activity 6s ago) (checkpoint: risk=high reads=0 writes=0 phases=-)` —— 墙钟判据 + checkpoint 摘要全文落盘
- 队列：failed；PM readback 正常送达
- **缺陷**：worker.log 两行 `Extension error (<runtime>): Agent is already processing. Specify streamingBehavior ('steer' or 'followUp')` —— agent 运行中 `pi.sendUserMessage(text)` 裸调用抛错（agent-session.ts L1168），checkpoint/deadline 两个 steer 均未送达
- 修复：checkpoint steer → `deliverAs: "followUp"`（当前 turn 结束后作为独立 turn 落地，不打断在途工作）；deadline steer → `deliverAs: "steer"`（注入当前 turn，紧急收尾）

## Run 2（修复后全路径 PASS）

任务：单次 `bash sleep 70` 后回复。时间线：

```
08:12:08 [START]
08:12:20 [TOOL] bash sleep 70
08:13:08 [CHECKPOINT] elapsed=60s reads=0 writes=0 risk=high   ← 锚点命中
          （checkpoint steer 以 followUp 入队，无 Extension error）
08:13:30 sleep 结束 → followUp turn 启动，agent 执行
08:13:48 [TOOL] bash echo "CKPT 1m converging=yes eta≈0m ..."  ← 自评按指令写入 progress.md
          （deadline steer 90s 到点，steer 注入当前 turn）
08:13:58 [END] exit=0 elapsed=110s tools=2                      ← 预算耗尽前自行收尾完成
```

- **progress.md**：`CKPT 1m converging=yes eta≈0m Task complete: ...` —— worker 自评落地
- **worker.log**：`[worker] start/done exit=0` + 完整最终回复（含 已完成/未完成/后续建议 结构——deadline steer 文案被采纳）；**零 Extension error**
- **output.md**：四节俱全，Summary 为结构化收尾报告；Exit Reason: `Agent settled after 2 tool call(s).`
- 队列：done

## 结论

- AC-001 idle 判据/互斥：单测覆盖（实跑需真挂死，不作烟雾）
- AC-002 预算解析 + 墙钟：Run 1 实证（120s 精准、判据落盘、exitReason 携带 checkpoint）
- AC-003 deadline steer：Run 2 实证（agent 在预算内收尾交付，exit=0 而非被杀）
- AC-004 checkpoint + 自评 + PM 升级：Run 2 实证 checkpoint/自评链路；PM triggerTurn 升级为单测覆盖（mid/high 一次、low 不打扰、跨 key 隔离）
- 遗留观察：Run 2 中 risk=high 属预期（sleep 非读非写、60s 零写触发纯探索判据）——真实编码任务中读多写少的前段也可能触发 high；PM 升级消息已注明"机器判据仅供参考"
