# Task T-12: EXECUTE 循环 + L3 收敛 + done 三件套

## 基本信息
- Stage: 2
- 代码状态: 代码完成（conductor.py EXECUTE 循环 + L3 收敛 + done 事务；dispatch.py upsert 修正）
- 验证状态: 验证通过（test_autopilot_conductor_exec.py 12 passed，[VERIFY] VC-012 ×2/VC-025 ×2/VC-024；全量 312 零回归零抖动）
- 负责 Agent: PM 窗口（用户指令直执）
- ac_refs: [AC-004, AC-010, AC-022, AC-023]
- vc_refs: [VC-012, VC-024, VC-025]
- pattern_refs: []

## 描述
`conductor.py` 内实现 EXECUTE 任务循环与 VERIFY→done 收敛（D-108 / D-111 / D-112）。

**EXECUTE 任务循环**（D-111）：
- task 身份 = `{key}/tasks/` 文件名 stem（如 `T-01-baseline-freeze`）；队列 taskKey = `ap-{key}-{stem}`
- `tasks/` 目录是执行契约（advance execute 门禁检查它）；plan 列出但 tasks/ 缺失 → L1 审计捕为缺口 → L2 → 升级 stalled 类 gate；孤儿任务照常派发 + timeline 注记
- **每 key 串行**：同一 key 一次只有一个在飞 exec 任务；跨 key 并行由 max_parallel_keys 承担
- 任务顺序 = plan 执行顺序可解析时遵循，否则 stem 字典序
- `loop: exec:{key}:{stem}`；完成判定 = 该 loop 队列行 status=done
- 失败（exit≠0 / 看门狗 / spawn 失败，AC-023）计入该 loop 回合预算，超限走 stalled；孤儿和解同 attempt 重插不新计

**L3 收敛与 done 三件套**（D-108/D-112）：
- VERIFY 期：派发 reviewer（review 级，无 bash）→ 审查 repair worker 在 output.md / evidence 记录的 [VERIFY] 输出，不重跑命令；需重跑的验证命令在 QG 报告标 `needs-rerun` 计入遗留
- 裁决解析：L3 output.md `## Quality Gate Report`（VC 断言表逐条 PASS/FAIL）+ `## Achieved` 两节；缺节或缺陷 → 按 below 处理
- below → 派发 repair（`loop: repair:{key}`，coding 级）→ 复评 = 下一 L3 回合；复评总轮数 ≤ 2；2 轮 below → stalled（T-10 标记路径）
- meets → conductor 机械落盘事务：
  1. 写 QG 报告 `evidence/quality-gate-report-YYYYMMDD-HHMMSS.md`（时间戳唯一不覆盖）
  2. 写 achieved.md 草稿（从 output.md `## Achieved` 节复制）
  3. **后验 ≥200B**（不足 = L3 产出质量问题 → 按 below 走修复回路，不硬凑字数）
  4. pm-state.md §3 追加 PASS 证据行（`.mw/key-{key}.lock` 下原子重写）
  5. 调 advance_phase.py done（门禁重验三件套：achieved ≥200B / pm-state 含 PASS / QG 报告 ≥1）
  6. **advance 后验 index**：exit 0 后回读 _index.parallel phase 列；失配 → 重跑 update_index.py set-phase → 再失败 → 人工 gate + timeline 留痕

**崩溃恢复不变量**（AC-022）：杀重启后 2 间隔内恢复推进；每 task 目录 [START] 行数 = 1（进程级，D-115 口径）；回路预算计数与重启前一致；已完成 artifact mtime 不变

## 输入
- 依赖文件: dispatch.py / state.py / timeline.py / advance.py / 既有 trace.log [START] 约定（T-14 落地写入侧）
- 依赖 Task: T-06, T-07, T-09, T-10, T-11
- AC 约束:
  > AC-004: 在 stage 已激活、某 key 依赖全部满足且未被人工窗口 live-claim 的条件下，conductor 在 10s 内派发该 key 的首个 phase worker；两个无依赖 key 同时满足条件时并行推进（默认 max-parallel-keys ≥ 2）
  > AC-010: 在 quality gate 已通过的条件下，L3 review worker 输出 meets/below 二值裁决；below 时派发修复 task 后复评，复评总轮数 ≤ 2
  > AC-022: 在 conductor 于 stage 执行中被杀死并重启的条件下，重启后 2 个轮询间隔内从文件恢复状态继续推进：同 key 同 phase 的 worker 进程数 ≤ 1（无重复派发）、回路预算计数与重启前一致、已完成步骤的 artifact mtime 不变
  > AC-023: 在 autopilot 派发的 worker 以任意方式失败（exit 1、看门狗超时、spawn 凭证失败）的条件下，该失败计入所属回路的 retry 预算并按 AC-011 升级；且单个 worker 失败不阻塞同 stage 其他 key 的派发（其他 key 派发行数照常 ≥ 1）
- 设计约束:
  > D-108: done 三件套事务与后验全文
  > D-111: stem 身份 + 串行 + loop 标签
  > D-112: L3 证据记录制（不重跑）
  > F5/F6/F13 覆盖点

## 预期产出
- `packages/multi-workers/autopilot/conductor.py` 扩展（EXECUTE 循环 + L3 收敛 + done 事务）
- `packages/multi-workers/test_autopilot_conductor_exec.py`（stub worker 行为注入队列）：
  - 任务逐个 done；失败 → retry 1 轮成功；retry 超限 → stalled（VC-025 失败注入：exit 1/spawn 失败两形态 + 其他 key rows≥1）
  - meets → 二值裁决 + QG/achieved 落盘 + 三件套后验 + advance 成功（VC-012）
  - below → repair 派发 → 复评；2 轮 below → stalled；后验 200B 不足 → below 路径
  - 缺节 output → below
  - advance 后验：index 失配 → set-phase 重跑 → 再失败 → gate
  - 杀重启：[START]=1 / 预算不变 / mtime 不变 / 2 tick 续推（VC-024）
  - 孤儿任务照常派发 + 注记；plan 缺失任务 → L1 缺口路径
- 验证方式: `[VERIFY]` 行输出
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 19:20-20:10 | 读 D-108/111/112 + 框架 done 门禁（achieved ≥200B/pm-state PASS/QG ≥1）+ update_index set-phase 接口 → dispatch.py 队列行改 upsert-by-task_key（与 TS WorkerStore.upsert 对齐，杜绝重复键行；读回校验加唯一性）→ conductor.py：execute_loop 全量（stem 身份/plan 序或字典序/每 key 串行/失败计预算超限 stalled/全完 advance verify）；_verify_loop（L3 reviewer 回合预算 2/below → repair（同回合预算 round_budget）→ 复评；缺节或 FAIL 行 → below；meets → _done_transaction）；_done_transaction（D-108 顺序：QG 报告时间戳唯一→achieved 草稿→后验 200B 不足走 below→pm-state PASS 行（.mw/key-{key}.lock 原子重写幂等）→advance done→后验 index：失配重跑 update_index set-phase→再失败 mark_stalled 人工 gate）+ _missing_plan_tasks（tasks 边界合成缺口走 L2）+ _family_rows（重试 -a<N> 后缀同 loop 真实计数）+ 12 用例 | 12 passed；全量 312 零回归 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 编辑工具转义 | conductor.py _done_transaction | `ValueError('illegal newline value: \n')`——大编辑 JSON 转义把 newline="\\n" 写成字面反斜杠（含 QG/achieved 两处）| 已修：换回 "\n"；rg 扫全文件确认无残留 |
| E2 | 测试侧 ×3 | test_autopilot_conductor_exec.py | ①advance 后断言 rows==[]（done 行本就留文件）②orphan 测试漏首 tick（_set_row 对不存在行 no-op）③短 achieved 断言 QG 不存在（D-108 顺序 QG 先于后验，QG 合法存在）| 均已修 |
| E3 | T-10 遗留断言 | test_autopilot_conductor.py | execute 桩测试期望 0 行——T-12 后 EXECUTE 真派发 | 已按新契约更新（断言 ap-k1-T-01 派发 + mtime 不变） |

### 设计取舍备注
- **重试身份**：attempt 1 用裸 stem（D-111 taskKey = ap-{key}-{stem}），重试 -a<N> 后缀同 loop——每尝试独立目录，used_rounds 真实计数（同目录重写 task.md 会丢历史 attempt 计数，不可用）；完成判定 = stem 家族任一行 done
- **dispatch upsert**：队列行 replace-first-or-append（与 TS WorkerStore.upsert 同语义）——对所有现有流为等价变换（唯一 stem），为 exec/repair 重试锁死无重复键行
- **exec 派发类型用 phase-writer**（coding 全集）：REGISTRY 无 exec 类型，新增会破 T-17 奇偶；repair 用于 L3-below 修复（语义已锁定）
- **L3 缺节/FAIL/短 achieved 三形态统一 below**：不硬凑字数；QG 报告先于后验写入（D-108 锁定顺序），below 轮次产生的 QG 报告在复评 meets 后复用（verdict 内容未变）
- **done 事务每步 check-before-write**：QG 已存在则复用/achieved ≥200B 则不重写/PASS 已在则不追加——崩溃重启下一 tick 续完（AC-022）；index 已 DONE 直接 advanced（crash-after-advance 恢复）
- **roadmap key-done 在事务后下一 tick**（phase DONE → _mark_key_done），与 stage 闭环的 tick 粒度一致
- L3 reviewer read_scope = key 目录 + goal.md（D-106 同型防护，reviewer 类型不强制但按需收紧）；exec/repair 不设 read_scope（coding worker 需项目级读写，AC-012 无 scope 即无拦截）

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
