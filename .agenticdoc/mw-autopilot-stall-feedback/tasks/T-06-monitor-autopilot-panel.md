# T-06-monitor-autopilot-panel

状态: done · 覆盖: AC-006, AC-007 · 依赖: T-02

## 目标

底部监控面板增加 autopilot 分节：tick 新鲜度（seq + age）、槽位用量、每 key phase/status/in-flight、advance 停滞连击（次数 + 分类 + 时长）与最近错误、pending 门禁计数、STUCK 高亮与处置命令。全部只读。

## 步骤

1. 读 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`：确认 `readConfig` / `readRoadmap` / `queryTimeline` / `listGates` 的既有签名与 `EVENT_TYPES` / config 键校验的宽松度。
2. 新增纯函数 `deriveAutopilotPanel(input) -> AutopilotPanel`（可注入 `nowMs`、数据读取结果），实现 design D-8 的派生规则（含与 Python 同规则的 streak 派生，注释互相指向）。
3. `monitor.ts` 的 `renderMonitorLines` 增加分节渲染；空数据渲染占位行；沿用固定分节与 110 列截断。
4. 配置键：TS 侧读取 `advance_stall_ticks`（默认 5）与 `poll_interval_sec`（STALE 阈值 `max(30s, 5 × poll)`）。

## 验证

- TS 单测：无 config / timeline 缺失 / gate 文件损坏 / 事件超窗 四种降级不抛；STALE 判定边界；stalled key 行含 `/autopilot gate <id> approve|reject`；行宽 ≤110。
- `npm run check` 0 error / 0 warning / 0 info。

## 执行记录

- 2026-09-22 23:58 完成（TS 侧）。
- `monitor.ts`：新增 `readTimelineTail`（尾部字节窗口 TS 镜像）、`classifyAdvanceFailure`（与 Python 同一契约）、`deriveAdvanceStalls`（面板口径：其他事件不打断运行，仅同 edge 成功清除；注释指向 conductor 的严格版）、`deriveAutopilotPanel(projectDir, nowMs, workers, deps?)`；`MonitorSnapshot` 增 `autopilot`，`MonitorGate` 增 `key`；`renderMonitorLines` 新增 autopilot 分节（tick 新鲜度/STALE、slots、每 key 相位+状态+in-flight+依赖阻塞、停滞连击+分类+时长+错误摘要、stalled 行给 `/autopilot gate <id> approve|reject`，110 列截断）；`formatUptime` → `formatDuration`。
- `status-model.ts`：config 镜像新增 `advance_stall_ticks`（默认 5，范围 1..50，读/校验/写三处同步——两侧均对未知字段 fail-closed，缺此镜像会让 Python 写出的配置在 TS 侧读取失败）；`EVENT_TYPES` 增 `resume` / `l3-no-verdict`。
- 测试：`test/suite/autopilot-monitor.test.ts` 新增 6 例（派生+只读哈希不变、STALE、空项目降级、stall 派生规则、尾部读取有界容错、config 镜像含旧文件缺键取默认）；既有 `MonitorSnapshot` 字面量补 `autopilot` stub。
- 结果：`vitest --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-console.test.ts` = **51 passed**（含既有用例与 `advance_stall_ticks` 新增字段的 `saveConfig` 期望更新）；`npm run check` 全绿（0 error/warning/info）。
