# Task T-01: index-store latest-active 解析 + _index.md 兜底

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001]
- vc_refs: [VC-001, VC-002]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`（design D-001 读侧）：
1. `activeKey()` 语义变更：由 `readAll().find(e => e.status === "active")`（文件顺序第一个）改为取 `updated` 时间戳最新的 active 行（多 active 存量分歧时最近激活者胜）。`activeKeys()` 保持不动
2. 新增导出 `readIndexMdActive(agenticdocRoot: string): string | undefined`：读 `{root}/_index.md` 的 `^active:\s*(\S+)` 行，文件缺失/无匹配返回 undefined
3. 单测（test/extensions/agent-team-loop.test.ts）：
   - 双 active 行（agent-team-loop updated=旧、goal-autopilot updated=新）→ activeKey() === "goal-autopilot"（VC-001）
   - _index.parallel 全 idle + _index.md `active: K` → readIndexMdActive === "K"（VC-002）
   - 既有 activeKey 用例（若有）适配新语义

注意：`activeKey()` 生产调用方仅 ui-bridge.resolveOwnerKey 一处（已核实）；`updated` 为 ISO 字符串，字符串比较即可（同构格式）。

## 输入
- 依赖文件: shared/index-store.ts、test/extensions/agent-team-loop.test.ts
- 依赖 Task: 无
- AC 约束:
  > AC-001: 在窗口激活 key 为 K 的条件下，经该窗口 dispatch_worker 派发的任务 task.md 路径为 {K}/workers/{task-key}/task.md

## 预期产出
- index-store.ts 改造 + readIndexMdActive
- vitest 用例（VC-001/VC-002）
- 验证方式: `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop.test.ts`（packages/coding-agent 下）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:01 | activeKey 改 Date.parse 最新胜（混合 ISO-UTC/本地分钟格式安全）+ readIndexMdActive 导出；新增 4 用例（VC-001 ×2 + VC-002 ×2） | PASS: 51/51（定向 vitest） |
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
