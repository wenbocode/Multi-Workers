# Research: owner key 错位根因与解析链设计（design）

## 决策问题

D-001/D-002（AC-001/002）：ga-spec-review-1 落错目录的完整机制链；owner 解析的正确来源与优先级。

## 调研方法与出处

- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts:63-67,111-113`：`readAll()` 每次实时读文件（无内存缓存）；`activeKey()` = `readAll().find(e => e.status === "active")` —— **返回文件顺序第一个 active 行**
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:15-19,106-132`：`resolveOwnerKey` = 显式参数 > `activeKey()` > `_scratch`；`takeOverKey`（switch_key/auto-takeover）设目标行 active **并降级其他 active 行**（单 active 纪律，TS 侧）
- `.agents/skills/agentic-task/scripts/update_index.py:234-278`（cmd_claim）：设目标行 `status: active`，**不降级其他 active 行**；`INDEX_FILE = "_index.parallel"`（Python 侧只写此文件）
- `.agenticdoc/_index.md`：内容 `active: goal-autopilot` —— 由 workflow 文档指示 LLM 手工维护（workflow-requirements.md「始终更新 _index.md 的 active 行」），无脚本同步
- 事故时序重建（ga-spec-review-1，2026-09-07 11:20）：agent-team-loop 行（文件首行）为旧 TS takeover 遗留 active；goal-autopilot 2026-09-06 16:52 经 python claim 追加为 active（不降级）→ 双 active 并存 → `activeKey()` find 返回 agent-team-loop → `resolveOwnerKey` → task 落 `agent-team-loop/workers/ga-spec-review-1/`，而 `_index.md` active=goal-autopilot（正确意图）
- `worker-mode.ts:69-77`（parseTaskMd 的 agenticdocRoot 实为 workers 目录）与 `output-writer.ts:17-24`（outputDir 约定）——确认 trace/output 路径约定

## 发现

1. 双写者不对称：TS takeover 维持单 active；python claim 制造多 active。两者都只写 `_index.parallel`，但 `_index.md` 由 LLM 手工维护，三个事实源可两两分歧且无告警
2. `activeKey()` 的 find-first 语义在多 active 时按文件顺序裁决 —— 与"最近激活"意图相反
3. `resolveOwnerKey` 完全不感知窗口 watch 状态（watch 不进解析链），事故中"解析结果与 watch 一致"是历史巧合（同一窗口早前 takeover 过 agent-team-loop）
4. `activeKey()` 生产调用方仅 `resolveOwnerKey` 一处（`activeKeys()` 无生产调用方）—— 改语义无涟漪
5. rows 的 `updated` 字段在 claim/takeover/restoreWatch/phase 更新时都会刷新，是跨 TS/Python 唯一可比较的时序字段

## 结论 → 决策映射

- 发现 1/2 → D-001 双修：写侧 `update_index.py claim` 降级其他 active 行（对齐 TS takeOverKey）；读侧 `activeKey()` 改为取 `updated` 最新的 active 行（对已分歧存量索引的防御）
- 发现 3/4 → D-002：`resolveOwnerKey` 升级为带同步告警的 `resolveOwnerKeyWithSync`（显式参数 > latest-active > `_index.md` active 行兜底 > `_scratch`）；watch 与解析结果不一致时每 session 告警一次（displaySummary 留痕进时间线），不自动改写 watch
- 发现 5 → latest-active 以 `updated` 字段排序；接受残余风险（stale 行若 recently bumped 会赢）——写侧修复阻断新分歧，读侧为存量防御
