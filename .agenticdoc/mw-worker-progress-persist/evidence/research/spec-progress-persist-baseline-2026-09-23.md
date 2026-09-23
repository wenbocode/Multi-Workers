# Research: worker progress 落盘基线（spec）

## 决策问题

支撑 spec 的三项决策：(1) §1.4 范围取舍（只做机器代记 vs 追加只读角色落盘通道）；(2) §2.3 安全约束（写入面该多大、哪些文件必须不可写）；(3) §4 风险 R-1/R-3 与 AC-003/004/008 的必要性（角色分化与 parity 锁是否真有必要）。

## 调研方法与出处

- 事故现场（OverCode key `chroma-hnsw-poison-fix`，2026-09-23）：`workers/chroma-review-evidence-r1/{task.md,trace.log,worker.log}`、`workers/chroma-review-lifecycle-r1/progress.md`、pi session jsonl `C:\Users\wenbozhou\.pi\agent\sessions\--E--CLI_workspace-OverCode--\2026-09-23T07-13-14-186Z_01a0cd1c-87ca-775c-b7b9-145c8a3ed055.jsonl`。
- 框架源码：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`worker/output-writer.ts`、`rag/tools.ts`、`packages/multi-workers/autopilot/dispatch.py`、`packages/multi-workers/test_autopilot_l0.py`、`test_autopilot_dispatch.py`、`test_rag_research.py`、bundle `packages/multi-workers/dist/extensions/agent-team-loop.js`。
- 命令：`rg -n 'progress'` 跨 `mw.py mw_common.py launcher.py autopilot/*.py` 与 `dist/extensions/agent-team-loop.js`；TS 导出/行号经 `rg -n` 与逐段 `read`。
- 项目记忆：`.agenticdoc/_pitfalls.md` P-007；`.agenticdoc/_arch_snapshot.md` §1.4。

## 发现

### 1. 事故事实（可复核）

- `chroma-review-evidence-r1/task.md:1` = `type: review` → 只读工具面；`trace.log` 全程只有 `read/grep/ls` 行，机器检查点 `[CHECKPOINT] 2026-09-23T08:03:14.225Z elapsed=3000s reads=141 writes=0 phases=- uniq_targets=0 repeat_top=6 risk=high`（writes=0 是角色白名单的必然结果，不是 worker 偷懒）。
- `worker.log`：`[worker] start task=chroma-review-evidence-r1 type=review phases=-` … `[worker] done exit=0 elapsed=54m tools=146 tool_errors=4`。
- session 中三条检查点自评（msg `d1f32708` 08:05:52Z / `263782e0` 08:06:00Z / `77c7317f` 08:06:07Z）内容同构：「会话只读无法写 progress.md，请 PM 代记：CKPT <n>m converging=yes eta≈0m …」——三轮检查点零新增，54 分钟预算有一段被"无法执行的动作"空转。
- 终稿（msg `89ffc393`，08:05:29Z，约 10KB「chroma-review-evidence-r1 终稿：证据链独立复审」）**只存在于 session**；框架落盘的 `output.md` 仅 703 B（TL;DR + `Tools used` 模板）。
- 同批 `chroma-review-lifecycle-r1/progress.md`（789 B，15:57:43）由 PM 事后从 session 代记——**该约定是现状的兜底，不是 worker 自证**。

### 2. 根因在框架代码中可直接定位

- 角色→工具白名单：`worker-mode.ts:49-80` `TOOL_ALLOWLISTS`（`review: read/find/grep/ls`、`research: +bash`、`coding/phase-writer/repair/fallback: +write/edit`）；唯一判定入口 `toolsForType`（`:89`）。
- 检查点写机器证据 + 要求 agent 落盘：`worker-mode.ts:886-925` `writeCheckpoint()` 先 `appendCheckpoint(...)`（`:899`，写 trace.log），随后无条件发送 steer：「请立即自评收敛性，把一行追加到 `${taskDir}/progress.md`」（`:909-922`）——**没有角色分支**，对只读角色是不可执行指令。
- 重复触发：`scheduleCheckpoint`（`:926-933`）锚点 `min(30m, budget/2)`、刷新 `CHECKPOINT_REFRESH_MS=10m`（`:103`）→ 与事故中 30/40/50m 三次自评完全对应。
- 消费方：TS bundle `dist/extensions/agent-team-loop.js:16984`（同一条 steer 文本）与 `:22391`（PM 升级消息明确把 `progress.md`（worker 自评）与 `trace.log`（`[CHECKPOINT]` 行）并列为裁决证据）。**Python 侧零消费者**：`rg -n 'progress' mw.py mw_common.py launcher.py autopilot/*.py` 仅命中 `autopilot/roadmap.py:731`、`autopilot/state.py:779` 两处英文单词。
- 现成可复用的拦截/注册范式：read-scope 的 `pi.on("tool_call")`（`worker-mode.ts:708-744`，返回 `{block:true, reason}`）+ 拒绝留痕 `appendReadScopeTraceLine`（`:423`）；工具注册与每次 run 重算 `applyRagTools`（`:697-700`，`setActiveTools` 延后到 `runner.initialize()` 之后，`:692-695`）。
- 白名单跨语言锁：`packages/multi-workers/autopilot/dispatch.py:50-51`（`_CODING_TOOLS`/`_REVIEW_TOOLS`）、`:69` `REGISTRY`；锁由 `test_autopilot_l0.py:215-239`（正则 `:218` 直接解析 TS 源码块）实现，`test_autopilot_dispatch.py`、`test_rag_research.py:71` 复用同一 helper。改任一侧白名单必红另一侧。

### 3. 历史先例（同类失败已被记录过）

- `_pitfalls.md` P-007：review 角色「唯一交付通道 = 最后一条消息」，实测「12 次 review 任务里 8 次没交出结论」，根因判定为「无落盘通道」而非「输出太长」；采用口径 = 审查任务改派 `coding` 类型 + 只许写一份报告文件。
- 本次事故是同一根因在**检查点/进度证据**维度的第二次暴露（P-007 只覆盖了终稿）。

## 结论 → 决策映射

1. 「方案 (c) 机器代记 + 角色化 steer」是**下限且必须**：根因是 `writeCheckpoint` 的 steer 无角色分支（发现 2），不修则只读角色每次检查点都产生不可能完成的指令（发现 1 的三轮空转）。→ spec §1.4、AC-001~004。
2. 落盘通道应做成**窄工具**而非给只读角色 `write`/`edit`：`progress.md` 的邻居 `trace.log`/`worker.log`/`output.md` 是机器证据，PM 升级裁决直接引用（发现 2 的 `:22391`），一旦开放通用 write 就有伪造证据风险（P-004 同族的路径守卫失效即漏拦）。→ spec §2.3、AC-005~007、§4 Q1。
3. 机器行必须与 worker 自评行可区分且两者共存：coding 角色已由 steer 自写 progress.md，统一追加会重复。→ AC-002/AC-003、§4 Q3。
4. Python 侧改动只需 parity 登记、无行为改动（零消费者，发现 2），因此 AC-008 可用既有 helper 断言，实现面收敛在 TS。→ AC-008、design 的改动面估算。
5. 验证要点在「反例矩阵 + 现状一致性」而非正向路径：路径守卫的失效模式是静默漏拦（P-004/P-005），→ AC-006 反例矩阵、AC-007 白名单现状比对。
