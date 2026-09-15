# Task T-03: update_index.py claim 降级其他 active 行（框架源）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001]
- vc_refs: [VC-017]
- pattern_refs: []

## 描述
`.agents/skills/agentic-task/scripts/update_index.py` `cmd_claim`（design D-001 写侧）：
1. `mutate()` 内目标行设 active 的同时，将其他 `status == "active"` 行降级为 `idle`（`updated` 一并刷新为 claim 时间）——对齐 TS `takeOverKey` 的单 active 纪律
2. 冲突预检（同 key 已 active 则 CONFLICT）语义不变
3. 脚本级验证（VC-017）：临时目录构造 `_index.parallel` 含两个 active 行 → 运行 `python update_index.py claim <root> K` → 断言 active 行唯一且 = K、原 active 行变 idle。验证脚本放临时文件，跑完删除（仓库规则：ad-hoc 脚本不留根目录）
4. 框架源改动按 AgenticTask 维护规则：在 installed clone（.agents/skills/agentic-task，本身是 git clone）内修改，完成后 `git commit && git push` 上游；push 失败不阻塞后续 stage，在 pm-state 记 pending

## 输入
- 依赖文件: .agents/skills/agentic-task/scripts/update_index.py（cmd_claim/mutate）
- 依赖 Task: 无
- AC 约束:
  > AC-001（写侧单 active）：claim 后 _index.parallel 的 active 行必须唯一

## 预期产出
- update_index.py cmd_claim 降级逻辑
- VC-017 脚本级验证输出（留 evidence/runs/ 或 pm-state 执行记录）
- 验证方式: 临时根目录 claim 前后 `_index.parallel` 断言
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 11:13 | cmd_claim mutate 前置降级其他 active 行（保留 claim_id，对齐 TS takeOverKey）；临时根脚本级验证三断言（降级/冲突语义保留/force 接管降级前任） | PASS: VC-017（[VERIFY] 三条输出） |
| 2 | 2026-09-08 11:14 | 框架 clone commit d33e777 + push origin master 成功 | done |

### 附注（现场观察）
- 验证时发现仓库实际 _index.parallel：goal-autopilot（他窗口 PID 39760）持有 active，本 key 被 TS takeOverKey 单活跃纪律降级 idle——D-001 所治理分歧类的活样本。本窗口执行不经派发不受影响；T-11 L2 按规格显式派发至 goal-autopilot。
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
