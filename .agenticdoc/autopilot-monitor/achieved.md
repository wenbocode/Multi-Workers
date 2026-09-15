# Achieved: autopilot-monitor

## 做了什么

`/autopilot monitor [on|off]`：PM 窗口底部（belowEditor）常驻监控面板，4s 轮询，实时显示编排链路四层状态——

- **mw serve**：PID、fresh/STALE CODE 判定（复用 5fa74a900 的 serveStaleness，含无 serve.meta 的 pid-mtime 回退）、uptime；down 时给 `/mw restart` 指引（指引永不被截断）
- **conductor**：PID + alive/dead（signal-0）、autopilot 意图（enabled/paused/not enabled）
- **workers**：跨 key 全部 running 行（taskKey + 向上取整分钟数），0 折叠
- **gates**：pending gate 数 + id + kind + `/autopilot gate ... approve|reject` 提示

实现：新文件 `autopilot/monitor.ts`（采集/渲染/生命周期三段，纯只读零写 API，apply 回调注入不持 pi 依赖）+ `console.ts` monitor case（hasUI 守卫 print 降级、deps 注入缝）。独立 widget id `agent-team-loop-monitor` 与 watch widget 并存。

## 目标收益判定（对照 spec §0）

✅ 达成：「链路是否活着、卡在哪」的答案时间从分钟级（手动 /mw status + /autopilot status + 读文件）降到 ≤1 轮询周期（首帧实际 0 tick 即时）。QG 实机佐证：首跑即在本 repo 上正确判出 serve STALE 并给出恢复指引（dogfood PASS）。

- AC-001..009：22/22 问题全充分（QG 报告 evidence/quality-gate-report-2026-09-11.md，A=22 B=0 C=0）
- 测试：autopilot-monitor 12/12（VC-001..008、VC-011、wiring、PM 补边界）+ 回归 147/147；tsgo 零错；npm run check 全绿
- 性能：readMonitorState 实测 1.46ms/次（预算 <100ms）
- 部署：mw build --install 完成（全局 bundle + dist）

## 遗留

- D-003 视觉叠放顺序（monitor 与 watch 实屏排布）建议首次实窗目视确认，异常走 design 合并 fallback（id 契约与互不覆盖已 harness 证明）
- 本 repo serve 当前 STALE（代码 17:11 变更 > serve 14:35 启动），新窗口会提示 /mw restart——预期行为
- conductor 内部状态机细节（阶段/派发队列）未透出（spec 范围外，如需要另开 key）

## 提交

已提交 `2c06dcc2d`（feat(coding-agent): add /autopilot monitor bottom panel，4 文件 +1028/-2，用户确认后）。
