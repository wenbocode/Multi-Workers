# T-04: PM model-error 告警（pm-orchestrator.ts）

type: coding

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（PM Agent 编排；文件驱动去中心化协调）。
- spec：`.agenticdoc/mw-model-error-perception/spec.md`（AC-006）；design：design.md §3.4（本任务蓝图）、§2 D7、§4 协议契约。
- 关键锚点（TRQ-3 取证，行号自行校对）：
  - 插桩点：pm-orchestrator.ts:1603 `recordWriteScopeResidualRisks` 旁的轮询终态分支（唯一同时具备去重/owner/双通道的位置）
  - 终态判定源：run.json（worker exit 3 时写 `model_exhausted: true`，T-01 提供）与 output.md `## Exit Reason` `model unavailable:` 前缀（双源取或）
  - 告警通道：`recordDispatchAlarm`（worker-mode.ts 写入侧先例 :3619-3626；PM 侧消费 :500-600、:1828-1840）
  - 重派回路失明现状：8 条重派路径对失败原因无感知（TRQ-3）——本任务只做**感知**（告警），不改 autopilot/conductor 决策
- 契约（design §4）：同 key 连续 K=2 个 model-error 终结 → 记录 kind=`model-error` 告警；非 model-error 终结清零该 key 计数。

## 要求

1. 终态分支新增 model-error 判定：run.json `model_exhausted===true` 或 Exit Reason 以 `model unavailable:` 开头。
2. 每 key 连续计数（内存 map 即可，PM 进程生命周期内有效）：达到 K=2 → `recordDispatchAlarm(kind: "model-error", count, detail: taskKey)`；K 的定义=连续两次终态均为 model-error（中间任一非 model-error 终态清零）。
3. 告警沿既有通道呈现（与 no-product 同级），不新增 UI 面；不在本任务阻断/改变任何重派行为。
4. 禁止：改 worker/**、launcher/mw Python、packages/ai、`~/.pi`；不改 autopilot 决策逻辑。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/worker/**`（T-01 所有）、test/**（T-05 所有）、Python 全部、autopilot 决策分支

## 验收命令

```
npm run check
node node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-pm.test.ts   # 从 packages/coding-agent 下；文件名以实际为准
```

- 全绿；并行说明：worker-mode.ts 由 T-01 并行修改中，其报错不归你修；`model_exhausted` 字段以 design §4 契约为准先行实现，T-01 若有偏差由 T-05 统一对齐

## 改动历史

- 2026-10-15 任务创建（T-04，Stage 1）
