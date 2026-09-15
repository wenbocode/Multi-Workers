# Task T-11: stage 机 + gate 生命周期

## 基本信息
- Stage: 2
- 代码状态: 代码完成（conductor.py stage 机 + gate 生命周期）
- 验证状态: 验证通过（test_autopilot_conductor_stage.py 11 passed，[VERIFY] VC-003 ×2/005/026 ×2；全量 299+1 抖动〔隔离 ×2 过，同前档判定与改动路径无关〕；T-10 28 无回归）
- 负责 Agent: PM 窗口（用户指令直执）
- ac_refs: [AC-001, AC-002, AC-003, AC-006, AC-024]
- vc_refs: [VC-003, VC-005, VC-008, VC-026]
- pattern_refs: []

## 描述
`conductor.py` 内实现 §5.1 stage 分支 + §5.3 gate 生命周期。

**stage 生命周期**（D-105 锁定顺序）：
- 无 approved stage → 确保 stage-confirm gate pending（roadmap 缺失 → 派发 roadmap-writer：输入 goal.md + 记忆三件套（存在时）+ _index.parallel 现存 key 清单 + schema 模板内嵌 task.md；read_scope 限 `.agenticdoc` 读，写目标仅 `_roadmap.md`；`loop: roadmap:stage-{N}`）
- stage-confirm 未回答 → 该 stage 派发行数 0
- 回答 approved → stage=running，放行 per-key 机
- 全部 key 终态 → 写闭环 dossier `.agenticdoc/_autopilot/stages/stage-{N}-close.md`（schema：stage id/goal/每 key {final phase, L3 裁决 meets|below|none + 报告路径, 证据引用}/generated_at）→ 创建 stage-close gate → approve → 标 stage=closed + 创建下一 stage-confirm gate → approve → running
- **stage-close reject** → stage 标 halted，暂停派发，等人工编辑 roadmap 或 `/autopilot resume`

**gate 消费**：
- 每 tick 扫描 answered gate（approved/rejected）→ gate-answered 事件 → 按.kind 分支推进（同 tick 或下一 tick）
- 回答文件损坏 → 跳过 tick + timeline config 事件

**reject 语义**（AC-024）：
- stage-confirm reject → roadmap-writer 重提案恰 1 次（`loop: roadmap:stage-N` 回合计 1）；再 reject → 停止自动提案，等人工编辑
- stalled gate reject → key 标 `closed-legacy`（遗留关闭，achieved.md 草稿保留），不阻塞 stage 闭环
- budget-exhausted / goal-change → halt 或等待人工解决

## 输入
- 依赖文件: roadmap.py / gates.py / dispatch.py / state.py / timeline.py
- 依赖 Task: T-03, T-05, T-06, T-09, T-10
- AC 约束:
  > AC-001: 在 goal 已确立且 autopilot 已启用的项目上，roadmap 生成流程完成后，`_roadmap.md` 中每个 stage 节均包含 key 清单（≥1 个 key）、key 间依赖声明、阶段目标三要素，roadmap 校验脚本对全部 stage 校验 exit 0
  > AC-002: 在 stage 提案已生成且 stage 门禁未回答的条件下，conductor 对该 stage 派发的 worker 任务行数为 0（查 `_workers.parallel`）；stage 门禁回答文件写入后 ≤ 2 个轮询间隔内出现该 stage 首个派发行
  > AC-003: 在 stage 内全部 key 到达终态（done 或人工裁决关闭）的条件下，conductor 在 1 个轮询间隔内生成 stage 闭环 dossier（含各 key L3 裁决与证据引用）并创建下一 stage 人工门禁文件，且在回答前对下一 stage 的派发行数为 0
  > AC-006: 在某 key L3 连续 2 轮裁决不达预期的条件下，该 key 被标记 stalled，1 个轮询间隔内生成含证据链引用的人工门禁文件，achieved.md 遗留问题节写入条目草稿并生成 pattern 文件；依赖该 key 的 key 派发行数为 0，无依赖 key 照常推进（1 个轮询间隔内派发行数 ≥ 1）
  > AC-024: 在 stage 门禁被 reject 的条件下，roadmap-writer 重新提案一次（计入其回合预算）；再次 reject 后 conductor 停止自动提案并等待人工直接编辑 `_roadmap.md`；在 stalled 门禁被 reject 的条件下，该 key 按遗留问题路径关闭（achieved.md 草稿保留），不阻塞 stage 闭环
- 设计约束:
  > D-105: stage 生命周期顺序锁定 + roadmap-writer 输入清单 + gate seq 分配
  > F2/F3/F7 覆盖点

## 预期产出
- `packages/multi-workers/autopilot/conductor.py` 扩展（stage 机 + gate 消费）
- `packages/multi-workers/test_autopilot_conductor_stage.py`：
  - stage-confirm 未答 ≥3 tick rows=0（VC-003）；答后放行（时延断言 VC-004 在 T-16）
  - 全 key 终态 → 1 tick 内 dossier + next gate pending + next rows=0（VC-005）
  - stage-close approve → closed + 下一 confirm gate；reject → halted 停派发
  - stage-confirm reject → 重提案恰 1 次；二拒后 0 提案（VC-026）
  - stalled gate reject → closed-legacy + 闭环不阻塞（VC-026）
  - stalled 全链路：四产物齐备 + dep rows=0 + indep rows≥1，1 tick 内（VC-008）
  - roadmap-writer 派发 task.md 含输入清单 + read_scope + loop 标签
  - gate 回答损坏 → skip + config 事件
- 验证方式: `[VERIFY]` 行输出
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 18:10-19:05 | 读 design §5.1/§5.3/D-105 + roadmap/gates/dispatch API → orchestrate 重构（§5.1 顺序：gate 消费→孤儿和解→stage 分支→per-key 机，闭环检查插在 running stage 扫描首）+ 新函数：_consume_answered_gates（损坏 gate → config 事件+跳 tick；tick 第 3 步 goal-change 扫描同步容错）、_set_stage_status（roadmap 锁下幂等改写）、stage-confirm approve→running / stage-close approve→closed+下一 confirm gate / reject→halted、_stage_activation（halted 存在→全局停派；无 running→首个 pending stage 激活）、_activate_pending_stage（拒绝后重提案：rm mtime vs 最近拒绝 gate 文件 mtime 区分「新提案待确认」与「当前提案已被拒」；人工手改 roadmap 同样得到 confirm gate 而非被 writer 覆盖）、_dispatch_roadmap_writer（D-105 输入清单：goal 内客+记忆三件套指针+_index key 清单+schema 模板；read_scope=[.agenticdoc]；同 loop 最多 2 尝试）、_stage_closure（全部 key ∈ done/closed-legacy 才闭环；stalled-pending 阻塞）+ dossier（stage/goal/每 key final phase+L3 裁决+证据引用/generated_at）+ _l3_verdict（T-12 前缺省 none）、_consumed_gate_ids（时间线 gate-answered 为消费记录：人工恢复 halted→running 后旧拒绝 gate 不重放）+ 11 用例 | 11 passed；T-10 28 无回归；全量 299+1 已知抖动 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | parser 误用 | conductor.py | _roadmap_writer_prompt 用 parse_workers_file（_workers 格式）读 _index.parallel → key 清单恒空 | 已修：改 state.read_key_states |
| E2 | 幂等漏洞 | conductor.py | 拒绝 stage-close gate 在人工恢复 running 后被重复消费再 halt | 已修：时间线 gate-answered 事件作消费记录（gate id 前缀匹配，重启可重导） |
| E3 | 同 tick 陈旧 | conductor.py | closure 检查用旧 roadmap 对象（closed-legacy 同 tick 改写后仍读 stalled） | 已修：_stage_closure 改收 status_of 活视图 |
| E4 | 激活流程洞 | conductor.py | 拒后重提案完成后无新 confirm gate（rejected_note 恒走 dispatch 分支） | 已修：rm/gate mtime 对比 + _latest_rejected_confirm |
| E5 | 测试侧 ×3 | test_autopilot_conductor_stage.py | fixture k1 replace 叠写（donedone）/k2 默认 done 被 per-key 机跳过/_answer 空值 note 替换不匹配（gates.py 裸 `note:` 行）/重提案编号假设错（fixture 跳过 a1） | 均已修 |

### 设计取舍备注
- gate 消费幂等双层：状态转移幂等（目标状态即已消费）+ 时间线消费记录（防人工恢复后被旧答案重放）；budget/goal-change gate 无转移（轮询型，T-10 语义不变）
- stage-confirm 拒后重提案：同 loop `roadmap:stage-{N}` 最多 2 尝试（拒后重提 + 失败重试共用上限，有界）；二拒或二败后停止自动提案，人工手改 roadmap 会得到新 confirm gate（不被覆盖）
- 闭环终态集 = {done, closed-legacy}；stalled-pending 阻塞闭环（人工未裁决）；stalled-reject 同 tick 解锁闭环（AC-024）
- halt 全局停派：任一 stage halted → _stage_activation 返回 False（stage 串行推进，halt 即项目暂停）；人工改回 running 后恢复（时间线消费记录防重放）
- dossier L3 裁决 T-11 阶段恒 none（T-12 EXECUTE 循环写 l3-verdict.txt 后变 meets/below）
- roadmap-writer dispatch 暂未传 l2 caps（render_task_md 不写字段，T-13 worker 侧缺省回退 8/65536；read_scope=[.agenticdoc] 下默认 8 文件够用，T-16 e2e 再校）

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
