# KDR: mw-worker-tree-kill

## R（需求）

- 技术栈: TypeScript（pi built-in extension agent-team-loop/worker）+ vitest
- 边界: 只修 worker 退出路径的子进程树清理；launcher Job Object / serve 侧杀进程不在内
- 关键约束: 不修改 pi 核心（只读复用 utils/shell.ts 导出）；watchdog 判定语义与 trace/output 格式不变；Windows + POSIX 双平台
- 来源: 2026-09-19 目标项目事故（worker idle 自杀后孤儿 python 吃 151 GB），用户转发事故报告并拍板「开新 key 来做」
- key 决策: 与 active key mw-provider-routing（DESIGN，provider 路由架构）无交付物交集 → 新建独立 key，deps 留空；决策由用户会话拍板（本记录即为留痕，mw-provider-routing 的 pm-state 归其持有窗口维护，不跨窗写入）

## A（架构）

- D001 清理入口: 选复用 utils/shell.ts killTrackedDetachedChildren，否扩展自实现/自杀整树（tracked Set 唯一出口）
- D002 覆盖策略: 选全 4 exit 位点显式 + 'exit' hook 兜底、写盘→杀树→exit，否仅 hook（best-effort 不确定）
- D003 Job Object: 选不做记遗留，否 launcher OS 级回收（独立交付物）
- D004 测试观测: 选 mock killTrackedDetachedChildren + invocationCallOrder + listener 直调，否 mock killProcessTree（ESM 闭包不可观测）/ emit exit（计数不可控）；per-pid 由 live 证据承担
