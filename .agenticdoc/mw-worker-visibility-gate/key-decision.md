# KDR: mw-worker-visibility-gate

## R（需求）

- 技术栈: TypeScript（pi Extension API，agent-team-loop 扩展）+ 既有 vitest 测试面；零 Python 行为改动。
- 边界（不做什么，一句话）: 不动框架仓库脚本、不动 monitor 的跨 key 升级投递、不按任务类型收紧派发、不清理 `_scratch` 存量任务。
- 关键约束: 门禁与面板判定必须纯文件读取可复现（GC-1）；claim 同步必须单行原地替换且不阻断索引侧写入；两处 `dispatchDocGaps` 调用点行为必须一致。

### 需求来源

2026-09-23，另一台机器（PC3）窗口的真实事故，用户判定要修三项并明确选型：

| 项 | 用户选择 | 含义 |
|----|---------|------|
| 派发门禁 | **C1** 相位分层 | SPEC 相位只校验 spec 侧四项；DESIGN 起追加 design 侧两项 |
| 面板可见性 | **B2** 聚合提示 | 面板仍只列本 key 行，另加"本窗口派发但他键所有"的 1 行聚合提示（含状态计数/风险） |
| claim 身份 | **D-c** 双写同值 | 保留双写，规定"两处必须同值 + TS takeover 同步 pm-state + 索引行为权威"，并登记 `_pitfalls.md` |

否决的备选（记录原因）：
- C1 的替代 `--allow-undocumented` 旁路开关：等于把门禁变成可选，违背"不写文档不得派发"的初衷。
- B1（把面板筛选直接换成 `ownedByThisWindow` 全混列）：跨 key 行会被误读成 watched key 的产物，且会让 `no workers` 语义失效。
- D-a（从 pm-state 模板彻底移除 `- Claim-Id:`）：最彻底但属格式变更，且需同时改框架仓库的 stub/升级逻辑 → 跨仓库，本 key 不做（登记为 Q-2）。
- 按任务类型限制 SPEC 相位派发：与历史口径 P-007（审查/调研任务以 `type: coding` 派发以获得落盘能力）冲突 → 明确不做（AC-012 作为回归项）。

## A（架构）← system-design 追加

- D101 门禁分层落点: 选 `phase-docs.ts`，否调用点各自分层（单一事实源，避两入口分叉）
- D101b 新增相位参数: 选可选缺省 `""`=spec 层，否必填（避免并行 worker 瞬时 typecheck 红）
- D102 相位归一化: 选未知/占位→spec 层，否未知即拒（新 key 的 `init` 占位不能被拒）
- D103 任务类型门禁: 不加，否 SPEC 只放 research/review（与 P-007 既有实践冲突）
- D104 `_scratch` 语义: 不变，否取消短路（临时任务仍需入口）
- D105 面板注入方式: 选可选第六参数 `extraTaskKeys`，否必填/全混列（不动 12 处既有调用）
- D106 聚合行格式: 选单行末尾 + risk 标记，否每任务一行（面板不被淹没）
- D107 claim 写入策略: 选单行原地替换 + 原子写，否复用 `StateManager.write()`（会抹掉 7 段模板）
- D108 claim 同步落点: 选 `takeOverKey` + 会话恢复 re-claim，否仅 `takeOverKey`（两条路径都改 Claim 列）
- D109 拒绝文案: 不变 + 无旁路参数，否新增豁免参数（门禁不可降级为可选）

## I（实施）← PM 执行中追加

- W1：T-1 `phase-docs.ts`（gateTierOf + tier 化 phaseDocGaps + dispatchDocGaps phase?）+ T-2 `pm-state-claim.ts`（单行替换/换行守卫/原子写）并行落地，新测试 11+7=18 全绿；`npm run check` EXIT=0。
- T-1 实测暴露两处勘察遗漏：**D-110**（门禁调用点实为三处，含 `pm-orchestrator.ts:429` 后台扫描；既有 `agent-team-loop.test.ts:1516` 的 gaps 断言 5→3）；**D-111**（本仓四个 key 的 pm-state 均无 `- Claim-Id:` 行：TS 路径只写索引行，`advance_phase` 新建模板不带该行 → 缺行时必须插行才能让"两处同值"达成，AC-011 按 REVISED 修订）。
- W2：T-3 接线（三处门禁传相位 + 面板聚合行 + claim 同步四个展示点），新测试 12 + 既有 191 全绿（5 文件 203 passed / 0 failed，PM 复跑确认）；T-4（PM 直执）CHANGELOG 三条 + `_pitfalls.md` P-011，CRLF 保留。
- W2.5：T-6 按 D-111 补插行分支（待验）。
- 已知偏离（均已在 design/任务书登记）：`phaseDocGaps` 的 tier 参数为可选缺省 `design`（保住 9 处既有单参调用）；T-3 的 VC-009 夹具写 trace.log 的 `[CHECKPOINT]` 行而非 `progress.md` 的 `[machine]` 行（`readTaskProgress` 只解析前者，任务书原文有误）。
