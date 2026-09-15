# KDR: mw-widget-terminal-lifecycle

## R（需求）

- 技术栈: TypeScript（agent-team-loop 扩展）+ Python（launcher starter prompt）
- 边界: 只改 widget 终态行生命周期（ack/分区折叠）与终态摘要取源；不改调度协议、不改 _workers.parallel 行/列格式、不做 TTL、不做 widget 交互
- 关键约束: ack 不得删除/改写队列行（dispatched 集合防重复派发）；队列行格式为 TS/Python 双侧共享协议（GC-4）；跑动中与待处理行必须常驻显示（用户指令，不用时间兜底）
- 用户决策留底（2026-09-10）:
  - 不手动改当时在跑的 t03-t08 队列行（曾误判僵尸行，实为 UTC 时间戳误读）
  - 不用 TTL 兜底隐藏；处理完/已完成总数 > 5 折叠 more...
  - 终态摘要当前混入文件路径等，要求改为「状态及卡点」
  - 用新 key（不并入 goal-autopilot / agent-team-loop）

## A（架构）← 2026-09-10 design 落盘

- D001 ack 持久化：选 sidecar `_workers.acked` + workers lock，否队列加列/新 status/删行归档（双侧解析器兼容 + 防重复派发）
- D002 ack 通道：选命令 + 工具双通道（PM-only 由 index.ts 分支保证），否单通道
- D003 widget 分区：选 live/unhandled 不折叠 + history 5+more，否 TTL（用户否决）
- D004 终态 detail：选按状态取源 + 回退链（Exit Reason/Questions/TL;DR），否统一 Summary 首行
- D005 TL;DR：选 worker 侧归一化 + starter prompt 引导，否仅展示侧清洗
- D006 reconcile 执行者：选 launcher（running_procs 归属知识 + 队列单写者），否 TS poll loop
- D007 reconcile 判据：选正证据每 poll + 90m 静默窗口（env 可调），否仅启动时 reconcile
- D008 beat 协议：选 `.mw/launcher-beat` + 静默退让，否进程扫描/不防护
- D009 测试：选 L1 双侧扩展零回归，否新 e2e 套件

## I（实施）← PM 执行中追加
