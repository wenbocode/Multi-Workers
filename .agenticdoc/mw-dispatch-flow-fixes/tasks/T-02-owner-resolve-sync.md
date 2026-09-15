# Task T-02: resolveOwnerKeyWithSync + watch 接线 + mismatch 告警

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001, AC-002]
- vc_refs: [VC-003]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` + `pm/pm-orchestrator.ts`（design D-001 解析链 + D-002 告警）：
1. `resolveOwnerKey` 升级为 `resolveOwnerKeyWithSync(pi, indexStore, watch, explicit, agenticdocRoot): string`：显式参数（非空 trim）> `indexStore.activeKey()`（T-01 最新语义）> `readIndexMdActive(root)` > `SCRATCH_WORKERS_KEY`
2. watch≠owner 时每 session 每对 (watch, owner) 恰好一次告警：`displaySummary(pi, "[mw] owner-key mismatch: window watch='X' but active key='Y' — dispatching under 'Y' (run /pm-key switch Y to align).")`；用 Set<string> 记 `X->Y` 已告警对
3. `registerWorkerTools` / `registerWorkerCommands` 增加 `watch: PmWatchState` 参数（pmActivate 处传入），两个派发入口（dispatch_worker 工具、/worker 命令）改用 resolveOwnerKeyWithSync
4. 单测（VC-003）：fake pi（捕获 sendMessage）+ 临时根构造 watch=X、active=Y → 首次派发告警 1 条（含 X 与 Y）、二次派发 0 条、task.md 落 `{Y}/workers/`

## 输入
- 依赖文件: pm/ui-bridge.ts（resolveOwnerKey/registerWorkerTools/registerWorkerCommands）、pm/pm-orchestrator.ts（pmActivate 接线）
- 依赖 Task: T-01（activeKey 最新语义 + readIndexMdActive）
- AC 约束:
  > AC-002: 在窗口 watch 状态与激活 key 不一致的条件下，派发前完成同步：以激活 key 为准并输出一次告警（时间线/日志留痕），不静默使用陈旧 watch

## 预期产出
- resolveOwnerKeyWithSync + 告警 + 两入口接线
- vitest 用例（VC-003）
- 验证方式: 定向 vitest（同 T-01）+ `npm run check`
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:08 | resolveOwnerKeyWithSync（显式 > latest-active > _index.md > _scratch，模块级 Set 每对一次告警）+ 两入口 watch 参数 + pmActivate 接线 + fakeCmdPi 增 sendMessage 捕获；VC-003 用例 | PASS: 52/52（定向 vitest） |
| 2 | 2026-09-08 11:10 | npm run check 全量：本 key 全部文件 0 错误（仓库整体 580 错误均为另一会话 packages/ai models 改动所致，T-10 复查） | PASS（本 key 范围） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
