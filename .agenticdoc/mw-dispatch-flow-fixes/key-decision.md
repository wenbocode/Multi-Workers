# KDR: mw-dispatch-flow-fixes

## R（需求）

- 技术栈: TypeScript（agent-team-loop extension）+ Python（launcher/mw 路由感知，如需）
- 边界: 不改看门狗语义、不做 worker 间通信、不做 claude 凭证配置、不含 goal-autopilot conductor 设计
- 关键约束:
  - dispatch owner key = 窗口激活 key；watch 与激活不一致时以激活为准 + 告警，不静默用陈旧 watch（用户决策 1）
  - worker 执行期结构化进度日志（心跳 ≤ 60s 间隔），活性判定阈值解耦可配（用户决策 2）
  - 路由全局默认 pi（用户决策 3，2026-09-07 澄清落定）：`type: review|research` 不再硬路由 claude，默认 pi/timi；claude 仅显式 cli=claude 时使用；`type: codex → codex` 保留（显式类型语义）
  - 显式 cli=claude 缺凭证不降级：沿用 mw-dispatch-reliability D-001 per-task failed + 原因留痕（用户决策 4）
  - 可用性检测唯一来源 mw_common（route_precheck/resolve_credential），本 key 不写第二套；默认路由静态无运行时判定链（用户决策 5，认可需求层表述）
  - docs-gate 仅对名下存在 ≥1 未入队任务的 key 评估告警（用户决策 6）
  - mw 播报按窗口认领 key 作用域过滤：终态摘要固化现有 watch.key 过滤，扫描 gate 告警仅认领 key 播报（用户决策 7，第三轮修订；弃"每窗口单一可更新播报面"机制）
  - 心跳消费面（用户决策 8，设计审核轮追加）：活 monitor 在 watch widget（4s 原位重绘，running 行显示 ph 进度 + hb 距离 + STALE 标记）；终态 worker-summary 附心跳统计（时长 + phase 完成度）；AC-012/013
  - 心跳/trace 侧全部 additive：output.md 四节、exit code 映射、既有 trace 条目格式不变
  - 修复验收以 ga-spec-review-1 同规格重跑为准（AC-008）
- 来源: goal-autopilot key 流程测试发现，2026-09-07 用户确认立 key，交其它窗口执行；同日两轮需求澄清完成（决策 3-7 落定，见 evidence/research/spec-routing-decisions-2026-09-07.md 与 spec-docgate-summary-2026-09-07.md）

## A（架构）← system-design 追加

- D001 owner 解析: 选 latest-active 链+写侧 claim 降级，否 watch 优先（根因在双 active+find-first）
- D002 mismatch 告警: 选每 session 一次 displaySummary，否自动 switch（避免静默抢 claim）
- D003 心跳: 选 worker 内 30s interval+独立行类型，否 PM 探活（GC-3 禁跨 worker 通信）
- D004 活性判定: 选 doctor 新节信息性，否 TS 独立脚本（doctor 双入口同源纪律）
- D005 路由: 选 pickWorkerRoute 删 claude 行，否 task.md cli 行（全局默认 pi 最小实现）
- D006 gate/播报: 选未入队过滤前置+接线处作用域，否本体掺 watch（关注点分离可测）
- D007 测试: 选 L1 密封为主+L2 仅 AC-008，否全 L2（与 mw-dispatch-reliability D-007 同构）
- D008 心跳消费面: 选 widget 活 monitor+终态摘要统计，否 summary 消息活更新（transcript append-only）

## I（实施）← PM 执行中追加
