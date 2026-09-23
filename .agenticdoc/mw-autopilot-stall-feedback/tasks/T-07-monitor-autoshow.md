# T-07-monitor-autoshow

状态: done · 覆盖: AC-008 · 依赖: T-06

## 目标

autopilot 已启用（`_autopilot/config.json` 存在且 `enabled=true`）的项目在 PM 窗口自动显示监控面板；`/autopilot monitor off` 关闭后本会话不再自动拉起；未启用项目行为不变。

## 步骤

1. `autopilot/console.ts`：`registerAutopilotCommands` 的初始化路径中，检测 enabled → 调既有面板显示入口（不新增写操作）。
2. 会话级「已手动关闭」标记只在内存中（不落盘）。
3. 与 `pm/ui-bridge.ts` 完全解耦（该文件被并发 key 持有）。

## 验证

- TS 单测：enabled → 自动显示一次；off 后不再显示；disabled 项目不显示。
- 手工（若扩展已重载）：在 tmux 中启动 pi，观察底部面板出现 autopilot 分节；`/autopilot monitor off` 后消失。
- 扩展加载验证受并发 key 的 `dist/` 重建限制，未执行则记入 AC-011 未决。

## 执行记录

- 2026-09-23 00:00 完成。
- `console.ts`：新增 `autoStartMonitor(ctx, projectDir, deps?)`（`ExtensionContext`，可在 session_start 阶段调用）+ 会话级 `monitorSuppressed`（仅内存，不落盘）+ `resetMonitorSuppression()`（测试隔离钩子，未来 session_shutdown 可复用）；`cmdMonitor` 的 `off` 置位、`on` 清除；`AutopilotConsoleDeps` 增 `autoMonitor?: boolean`（默认 true）。
- `pm/pm-orchestrator.ts`：`session_start` 钩子在 `ui.ctx = ctx` 后调用 `autoStartMonitor(ctx, projectDir)`（4 行纯追加）。
- 测试：`autopilot-monitor.test.ts` 新增 2 例（enabled → 自动显示 + 幂等 + off 抑制 + on 恢复；无 UI/opt-out/disabled/无 config 四种不显示）。
- 结果：`vitest --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts` = 51 passed；`npx tsgo --noEmit` 与 `npm run check` 均干净。
- 并发边界说明：`pm-orchestrator.ts` 在并发 key（mw-rag-integration-fix）的脏文件集内，本 key 只做 4 行纯追加，并在 §执行记录 与 T-09 证据里核对 diff 为 additive（`49 insertions / 1 deletion`，其中 1 deletion 与 RAG/parallel-protocol 改动属于对方；本 key 的 import 与 RAG import 共存）。
- **未执行**：扩展 bundle/dist 重建与真实窗口目视验证（受并发 key 的 `dist/` 构建限制）—— 记入 AC-011 未决，不得声称已生效。
