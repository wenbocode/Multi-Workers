# Task T-04: 心跳写入（appendHeartbeat + worker interval）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-003, AC-005]
- vc_refs: [VC-004, VC-005]
- pattern_refs: []

## 描述
新文件 `packages/coding-agent/src/extensions/agent-team-loop/shared/heartbeat.ts` + 改 `worker/output-writer.ts` + `worker/worker-mode.ts`（design D-003）：
1. `shared/heartbeat.ts`：`HEARTBEAT_INTERVAL_MS = 30_000`、`HEARTBEAT_STALE_MS = 90_000` 常量 + `readHeartbeatInfo(taskDir): { lastTs, ageMs, phase, phaseTotal, count, firstTs } | undefined`（扫 trace.log 最后一条 `[HEARTBEAT]` 行，无则 undefined）
2. `output-writer.ts` 新增 `appendHeartbeat(taskKey, workersRoot, phaseInfo)`：追加行 `[HEARTBEAT] <ISO-ts> task=<key> phase=<i>/<n|->`（沿用 outputDir 路径约定与 appendFileSync 单写者模式；不改 appendTrace/appendGoalCheck）
3. `worker-mode.ts`：`workerModeActivate` 内起 `setInterval`（HEARTBEAT_INTERVAL_MS，`.unref()`），tick 时 `appendHeartbeat(meta.taskKey, meta.agenticdocRoot, ...)`（phase = `nextPhaseIdx-1 已完成数/总`，无 phases 用 `-`）；`exitWithSuccess`、watchdog、catch、process exit hook 四处 `clearInterval`
4. 单测：
   - VC-004（L0）：断言 HEARTBEAT_INTERVAL_MS ≤ 60_000；appendHeartbeat 输出匹配 `^\[HEARTBEAT\] \S+ task=\S+`
   - VC-005：混合 trace.log（[FLOW]/[GOAL_CHECK]/[HEARTBEAT]）——[FLOW]/[GOAL_CHECK] 行格式与改前一致（复用既有断言/新增解析对比），[HEARTBEAT] 独立行类型
   - readHeartbeatInfo 解析（lastTs/phase/count）正确性

注意：meta.agenticdocRoot 实为 {owner}/workers 目录（既有命名误导，沿用约定勿改）。

## 输入
- 依赖文件: worker/output-writer.ts、worker/worker-mode.ts、test/extensions/agent-team-loop.test.ts
- 依赖 Task: 无
- AC 约束:
  > AC-003: 在 worker 执行期间（含单次 LLM 生成 > 60s 的阶段），结构化进度条目以 ≤ 60s 间隔持续写入
  > AC-005: 心跳机制不改变既有协议语义（additive）

## 预期产出
- shared/heartbeat.ts + appendHeartbeat + worker interval
- vitest 用例（VC-004/VC-005 + readHeartbeatInfo）
- 验证方式: 定向 vitest + `npm run check`
- 验证等级: Level 1（间隔行为 L2 在 T-11）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:15 | shared/heartbeat.ts（常量 + readHeartbeatInfo）+ appendHeartbeat + worker-mode 30s interval（unref，三 exit 路径 + 看门狗清理）；VC-004/005 + readHeartbeatInfo 三用例 | PASS: 55/55（定向 vitest） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
