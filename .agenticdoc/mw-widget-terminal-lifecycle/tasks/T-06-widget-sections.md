# Task T-06: widget 三区渲染（分区 + 折叠 + unhandled 计数）

## 基本信息
- Stage: 3
- 代码状态: 代码完成（PM 直执）
- 验证状态: 验证通过（vitest 100/100 含 3 个新用例 + [VERIFY] VC-001/002/003 埋点；biome 零告警）
- 负责 Agent: 待定
- ac_refs: [AC-001, AC-002, AC-003]
- vc_refs: [VC-001, VC-002, VC-003]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` renderWatchLines 重构（D-003）：

1. **签名扩展**：`renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key)`；调用方同步：pm-orchestrator 的 startWorkerPollLoop / refreshWatch / restoreWatch（pmActivate 构造共享 `new AckStore(agenticdocRoot)` 实例）
2. **三区**（owned = 该 key 的行；acked = ackStore.readAll() keys）：
   - live：running（现有实时 detail：hb/up/ck/lastAction 不变）+ pending——全部输出，不折叠
   - unhandled：failed/needs-clarification 且 ∉ acked——全部输出，不折叠，detail = readTerminalDetail（T-05）
   - history：done ∪ acked 终态——按 updatedAt 新→旧，输出前 `WATCH_HISTORY_MAX=5` 行，超出追加 `  ... +N more`
   - 顺序：header → live（running 先于 pending）→ unhandled → history → more
3. **常量**：`WATCH_MAX_TASK_LINES`（6）移除，新增 `WATCH_HISTORY_MAX = 5`
4. **header**：既有计数 parts 保留；unhandled 数 >0 时追加 `${n} unhandled`
5. 无 ack 文件（AckStore.readAll 空）→ 行为等同全部未 ack（旧项目兼容）

**测试**（agent-team-loop.test.ts 追加；现有 renderWatchLines 用例改为新签名）：
- 3 running + 2 pending → 5 行全出、无 more（VC-001）
- 3 failed 未 ack → 全出；ack 1 个 → 该行进 history、余 2 留 unhandled（VC-002）
- 7 done → history 5 行 + `... +2 more`；5 done → 无 more（VC-003）；排序按 updatedAt 新→旧
- header 含 `N unhandled`（>0 时）；=0 时不出现
- 旧用例（counts/phase/failure detail/heartbeat stats/START-END runtime）在新签名下语义不变
- 输出 `[VERIFY] VC-001/002/003: ...` 埋点行

## 输入
- 依赖文件: `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`（三处调用点）、`shared/ack-store.ts`
- 依赖 Task: T-01（AckStore）、T-05（readTerminalDetail）
- AC 约束:
  > AC-001: 在 renderWatchLines 输入中存在所 watch key 的 running/pending 行时，输出的任务行区包含全部 running/pending 行且无折叠标记（数量不设上限）
  > AC-002: 在存在未 ack 的 failed/needs-clarification 行时，输出包含全部这些行且无折叠标记；这些行 ack 后不再出现在该区（由 AC-004 的 ack 状态驱动）
  > AC-003: 在 done 行与已 ack 终态行总数 N > 5 时，按 updatedAt 新→旧输出前 5 行并追加一行 `... +N-5 more`；N ≤ 5 时全部输出且无 more 行
- 设计约束:
  > D-003: 三区 + WATCH_HISTORY_MAX=5 + header `N unhandled`；ack 每 tick 读文件（4s 轮询节奏）
  > spec §1.4: 不做 TTL（用户否决）；more 行不可展开

## 预期产出
- `pm/ui-bridge.ts`（renderWatchLines 重构 + 常量）
- `pm/pm-orchestrator.ts`（调用点 + AckStore 构造）
- `agent-team-loop.test.ts`（新用例 + 旧用例改签名）
- 验证方式: vitest 全绿（含既有 90 用例零回归）+ 埋点
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T07:46Z | renderWatchLines 三区重构（live 不折叠/unhandled 不折叠+header N unhandled/history 新→旧 cap5+more）；WATCH_MAX_TASK_LINES→WATCH_HISTORY_MAX=5；签名加 ackStore；pm-orchestrator 三调用点+pmActivate 构造 AckStore；测试 21 处调用点机械更新（node 脚本，避免 CJK 编码风险） | vitest 100/100（新增 3 用例）+ 埋点 VC-001/002/003；无旧折叠断言残留；biome 零告警 |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
