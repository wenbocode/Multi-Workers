# Task T-10: per-key phase 机（L1/L2 回路与 stalled）

## 基本信息
- Stage: 2
- 代码状态: 代码完成（conductor.py per-key phase 机）
- 验证状态: 验证通过（test_autopilot_conductor.py 28 passed，[VERIFY] VC-007/008/010/013/015/016/019/021 ×13；全量 289 passed 零回归）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-004, AC-005, AC-008, AC-011, AC-013, AC-014]
- vc_refs: [VC-006, VC-010, VC-013, VC-015, VC-016, VC-019]
- pattern_refs: []

## 描述
`conductor.py` 内实现 §5.2 per-key phase 机（每 tick 对每个 ready key）：

1. **pick ready key**：roadmap 依赖满足 + 未被人工窗口 live-claim + 受 max_parallel_keys 上限（在飞 key 数）
2. **live foreign claim** → skip + timeline skip 事件（不派发）；人工 force 接管 conductor 持有的 key → 1 间隔内新增派发行数 0
3. **非终态 worker 行存在** → 等下一 tick（不重复派发）
4. **phase artifact 映射**：SPEC→spec.md；DESIGN→design.md；PLAN→plan.md；TASKS→tasks/*.md；EXECUTE→全部 exec loop 终态（exec 循环本体在 T-12，本 task 留接口）；VERIFY→QG 报告 + achieved.md；done→终态
5. **artifact 缺失** → 派发 phase-writer（loop 无关，生成动作）
6. **artifact 存在** → L1 审计（audit_evidence）：
   - clean → **advance via 脚本**（advance.py 子进程；timeline advance 事件带脚本 exit code）
   - gaps → L2 rounds left? → 派发 verifier（`loop: l2:{key}:{edge}`，attempt 递增）；phase-writer 补证属同回合修复动作不另计；L1 重审后有缺口才开下一回合
   - rounds 用尽 → 人工 gate（budget-exhausted）或 stalled 升级
7. **budget=1 一致性**：round_budget 对 L1↔L2 / L3 / retry 三回路同源生效（config 单处）
8. **stalled 标记路径**：L3 连续 2 轮 below（判定接入在 T-12，本 task 实现标记动作）→ key-status stalled + 人工 gate + achieved.md 遗留草稿 + pattern 文件四产物；依赖该 key 的 key 阻塞（派发 0），无依赖 key 照常
9. **EXECUTE 中途接手**：key 手动推进至 EXECUTE 后交给 autopilot → 从 _index.parallel 恢复 phase 续推，已完成 artifact mtime 不变
10. **孤儿和解**（D-102）：队列 ap- 行 vs task 目录对账，同 attempt 重插不新计回合

## 输入
- 依赖文件: autopilot/ 全部 S1 模块（state/dispatch/gates/timeline/audit/advance/config）
- 依赖 Task: T-02~T-09
- AC 约束:
  > AC-004: 在 stage 已激活、某 key 依赖全部满足且未被人工窗口 live-claim 的条件下，conductor 在 10s 内派发该 key 的首个 phase worker；两个无依赖 key 同时满足条件时并行推进（默认 max-parallel-keys ≥ 2）
  > AC-005: 在任何 phase 推进路径上，conductor 对 pm-state.md Phase 字段的直接写入次数为 0 且对 goal.md 的写调用次数为 0，全部推进经 advance_phase.py 完成（静态检查 conductor 代码无 Phase 直写、无 goal.md 写调用 + 调用日志留痕）
  > AC-008: 在 L1↔L2 裁决回路达到配置上限（默认 2 轮）的条件下，conductor 对第 3 轮 L2 worker 的派发数为 0，并在 1 个轮询间隔内生成人工门禁文件
  > AC-011: 在全局回合预算配置修改为 1 的条件下，L1↔L2、L3 收敛、task retry 三类回路均在 1 轮后升级（人工门禁或 stalled），第 2 轮派发数为 0
  > AC-013: 在某 key 被人工窗口 live-claim 的条件下，conductor 跳过该 key 且时间线记录 1 条 skip 事件；人工 force 接管 conductor 持有的 key 后，conductor 在 1 个轮询间隔内对该 key 的新增派发文行数为 0
  > AC-014: 在某 key 已由手动方式推进到 EXECUTE 后交给 autopilot 的条件下，conductor 从 pm-state.md 恢复其 phase 继续推进，已完成 phase 的 artifact 文件 mtime 不变（不重做）
- 设计约束:
  > D-102: 零私有状态；F4/F8/F9/F13 覆盖点
  > D-111: round 单位表；每 key 串行

## 预期产出
- `packages/multi-workers/autopilot/conductor.py` 扩展（per-key phase 机）
- `packages/multi-workers/test_autopilot_conductor.py` 扩展（fixture 项目 + stub advance/dispatch）：
  - L1 干净直推（VC-007 运行期：advance 事件带 exit code；直写 0）
  - 缺口 → verifier 派发 → 补证 → 重审干净 → advance（1 回合闭环）
  - 2 轮上限 → 第 3 轮 rows=0 + gate 1 tick 内（VC-010）
  - budget=1 → 三回路 1 轮升级、第 2 轮 rows=0（VC-013；L3/retry 路径用 stub 触发）
  - live-claim skip + 接管后 rows=0（VC-015）
  - EXECUTE 接手：phase 恢复 + mtime 不变（VC-016）
  - 转移矩阵：每类转移事件 ≥1 行含 ts+key，key 字段无 null（VC-019）
  - stalled 四产物 + 依赖阻塞传播（VC-008 联合断言；gate 语义细测在 T-11）
- 验证方式: `[VERIFY]` 行输出
- 验证等级: Level 1（VC-006 并行计时在 T-16）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 15:55-16:45 | 读 design §5.2 状态机 + S1 全模块 API + 框架 phase 枚举（spec/design/plan/tasks/execute/verify/done）+ KEY_STATUSES/STAGE_STATUSES + pm-mind pattern 格式（.agenticdoc/patterns/{key}/）→ conductor.py 扩展：orchestrate（孤儿和解先行→roadmap 解析→running stage 扫描→claim/deps/in-flight/并行 cap 四门→_advance_key）；phase 机（artifact 映射/缺失→phase-writer gen 标签；存在→build_dossier→clean→advance 脚本+exit code 事件；缺口→verifier l2 循环→同回合 fix→重审；预算尽→budget-exhausted gate，approve=+1 bonus 轮，reject/bonus 尽→mark_stalled）；mark_stalled 四产物（key-status/gate/achieved 草稿/pattern 文件）；closed-legacy 转移（stalled gate reject→依赖同 tick 解锁）；_mark_key_done；reconcile_orphans（同 attempt 重插）；execute_loop 留 T-12 桩 + 测试 13 用例 | 28 passed；全量 289 零回归 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | fixture 自伤 | test_autopilot_conductor.py | `_key_project` 二次 save 用 default_config 覆盖 enabled=True | 已修：从 load_config 取已存配置再改 budget/cap |
| E2 | 路径误解 | test_autopilot_conductor.py | roadmap 真实路径是 .agenticdoc/_autopilot/_roadmap.md，fixture 写到 .agenticdoc/ 下致 orchestrate 早退 | 已修：四处置换路径 |
| E3 | API 笔误 | conductor.py | `mw_common.TERMINAL_STATUSES` → 实为私有 `_TERMINAL_STATUSES`；`orphan.task_md` → 实为 `task_dir` | 已修（同包私有访问有 state.py 先例） |
| E4 | 同 tick 快照陈旧 | conductor.py | closed-legacy 改写后依赖检查仍用旧 status_of | 已修：_apply_stalled_rejections 原地更新字典 |

### 设计取舍备注
- L2 回合结构：round = verifier 派发（attempt 递增）；同回合 fix（phase-writer 同 loop 同 attempt）不新计；fix 派发时机 = verifier 终态且 fix 行缺席（verifier 无写工具，其终态必然未闭合缺口）
- budget-exhausted 语义：approve=+1 bonus 轮（gate context_refs 携 loop 标签）；reject→stalled；bonus 尽→直接 stalled（不再建第二个 budget gate）；stalled 时 mark_stalled 另建 stalled gate（两问两点：预算门问是否追加，stalled 门问遗留关闭或人工介入）
- 依赖满足 = done/closed-legacy；stalled 阻塞依赖者；closed-legacy 解锁（人已裁决遗留关闭）；stage 仅 running 状态被工作（T-11 管 pending→running 激活）
- gen 派发（artifact 生成）loop 标签 gen:{key}:{phase} 不入任何预算表；stem 计数避免同 key 同 phase 重派冲突
- roadmap.py 的 roadmap_path 在 _autopilot/ 下（与 config/timeline/gates 同目录）——T-15 console 消费时同源

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
