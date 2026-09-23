# PM State: mw-worker-tree-kill

## 1. Snapshot
- Key: mw-worker-tree-kill
- Phase: DONE
- Next Action: —
- Started: 2026-09-19 17:12
- Updated: 2026-09-19 18:41
- Completed: 2026-09-19 18:41

## 2. Task Status
| Task | 代码 | 验证 | 说明 |
|------|------|------|------|
| T-01-WORKER-EXIT-KILL | 完成 | 通过 | worker-mode.ts 4 exit 位点 + 'exit' hook 杀树；check 绿 + grep 不变量 |
| T-02-UNIT-TESTS | 完成 | 通过 | 5/5 绿；原 agent-team-loop.test.ts 158/158 不回归 |
| T-03-LIVE-REGRESSION | 完成 | 通过 | live 1/1（orphan_count=0）；全量 69 failed ≤ 76 基线且零交集；dist 重建 + pi 冒烟 |

## 3. Evidence Ledger
- E-001: worker-mode.ts 内每个 `process.exit(` 前一行均为 `killTrackedDetachedChildren()`（grep 6 处，:414/:441/:683/:884 + hook :483）→ AC-001~004 实现基础
- E-002: 单测 5/5 通过（mock killTrackedDetachedChildren；invocationCallOrder 断言 kill 先于 exit）→ VC-001~005
- E-003: 原套件 158/158 通过 → 成功路径零回归
- E-004: live 测试真实树（2 tracked + 1 孙进程）watchdog 退出后 2.11s 全灭 → VC-006（AC-006）
- E-005: 全量 vitest 69 failed / 2253 passed，失败文件全部为已知 Windows 环境语义类别，与改动面零交集 → new-failures=0
- E-006: dist 重建后 worker-mode.js 含 6 处 killTrackedDetachedChildren；pi --version/--list-models 冒烟正常
- E-007: 质检报告 evidence/quality-gate-report-2026-09-19.md：21 问，19 充分 / 2 ⚠️（Q-D-2 全链派发 smoke 降级、Q-D-3 POSIX live 无环境）/ 0 ❌
- E-008: 自审 diff：worker-mode.ts +15 行与设计一致；工作区含 mw-target-partition 未提交变更（非本 key 文件，不触碰）
- E-009: 全链 mw 派发 smoke（serve 91432 重启后）：worker 44776 挂起 Start-Sleep 109s → wall kill → kill 后 ppid=44776 两次探活全空（orphan_count=0），output.md kill 前落盘 → Q-D-2 关闭
- E-010: 质检复版（用户「按推荐，并做 qg」）：21/21 充分（Q-D-3 用户确认接受组合证据），0 ⚠️ 0 ❌ → 结论 ✅ 通过
- E-011: 独立 review（用户「review and quality gate」）：review-mw-worker-tree-kill，0 Critical / 1 Warning（CHANGELOG 缺）/ 5 Suggestion；W-1/S-1/S-3/S-4/S-2 全部采纳落地
- E-012: 处置后复验：单测 7/7 + live 1/1 + 原套件 158/158 = 166/166；npm run check EXIT=0；双 dist 重建（coding-agent/dist 23:07 + mw bundle/全局安装 23:08，均含 S-1）；root build 失败为另一会话 packages/ai kimi-coding 在途工作（未触碰）
- 证据归档：evidence/runs/run-2026-09-19.md + evidence/quality-gate-report-2026-09-19.md + workers/review-mw-worker-tree-kill/output.md

## 4. Hypothesis Queue
- H-001 [CONFIRMED]: ESM 模块内闭包使 killProcessTree 层 vi.mock 无法观测 killTrackedDetachedChildren 内部调用 → 设计期 D-004 修订为 mock killTrackedDetachedChildren 本身，per-pid 证据移至 live（design 调研留底补充节）

## 5. Decisions
- 2026-09-19: 用户会话拍板新建 key（与 mw-provider-routing 无交付物交集），deps 空（记录于 key-decision.md R 章）
- 2026-09-19: AC-004 语义修订（refusal 在 hook 注册前退出，本 AC 收敛为硬崩溃兑底）[REVISED 标注]
- 2026-09-19: AC-001~003 量化口径修订（ESM 闭包发现后，per-pid 证据移至 live）[REVISED 标注]

## 6. Turn End Records
### 2026-09-19 23:15（review+qg 轮收口）
1. 顶层目标：独立 review + 质检终版闭合
2. 新增证据：E-011、E-012
3. 无新假设
4. review 建议 S-1/S-3/S-4 落地 = done 后增量修复（已重验证）
5. 阻塞：root `npm run build` 因另一会话 packages/ai 在途工作失败（包内 build + mw build 绕过，双 dist 已更新；不影响本 key）
6. 无需新增 Task
7. 下一动作：无（key 维持 done，增量已归档）
8. 已写入 ✅
9. pattern 候选：mock 打模块导出边界（ESM 闭包）；静态 review 与代跑测试互补（review 声明不代跑，PM 复跑闭合）

### 2026-09-19 19:00（smoke 补验轮收口）
1. 顶层目标：按用户推荐处置关闭 2 项 ⚠️ 并重跑质检
2. 新增证据：E-009、E-010
3. 无新假设（checkpoint risk=high 为预期机器判据误报，PM 判定继续等待，已验证）
4. 无需重开 Task（smoke 失败即测试通过）
5. 无阻塞
6. 无需新增 Task
7. 下一动作：achieved.md → advance done
8. 已写入 ✅
9. pattern 候选同前（待 done 后归档）

### 2026-09-19 18:50（verify 轮收口）
1. 顶层目标：质检闭合 + 合入前自审
2. 新增证据：E-007、E-008
3. 无新假设
4. 无需重开 Task
5. 阻塞：2 项 ⚠️ 待用户确认（Q-D-2/Q-D-3，均组合证据性质）
6. 无需新增 Task
7. 下一动作：用户确认 ⚠️ 处置 → achieved.md → advance done
8. 已写入 ✅
9. pattern 候选同前

### 2026-09-19 18:12（执行轮收口）
1. 顶层目标：worker 退出路径杀 tracked 子进程树，修复孤儿化事故链
2. 新增证据：E-001~E-006
3. 假设：H-001 证实（D-004 修订）
4. 无需重开 Task
5. 无阻塞（/mw restart 属用户侧运维动作，已提示）
6. 无需新增/拆分 Task
7. 下一动作：推进 verify → quality gate → done（achieved.md）
8. 已写入本 pm-state ✅
9. 可提炼 pattern：进程树清理必须挂在「模块导出层」可观测的入口；mock 同模块内部调用不可行（候选，待 verify 后决定是否入 patterns/）

## 7. Process Log
- 2026-09-19 17:11: key 创建（spec/design/plan/tasks 全链落盘，mermaid PASS）
- 2026-09-19 17:15-17:25: T-01 实现 + T-02 单测（含 D-004 修订：ESM 闭包发现）
- 2026-09-19 17:25-18:10: T-03 live 测试（修复 waitFor 默认参数与 argv 索引两处测试 bug）+ 全量回归 + dist 重建 + pi 冒烟
- 2026-09-19 18:10-18:50: verify：质检报告（19✅/2⚠️/0❌）+ diff 自审 + 指纹重算（264ea1756fc7）+ baseline 对照落盘
- 2026-09-19 18:55-19:00: 用户「按推荐，并做 qg」：serve 重启（4448→91432）→ 全链 smoke 派发 smoke-tree-kill-1（wall kill，orphan_count=0）→ 质检复版 21/21 通过 → ack
- 2026-09-19 22:47-23:15: 用户「review and quality gate」：派发独立 review worker（needs-fix，0C/1W/5S）→ W-1 CHANGELOG + S-1 try/catch + S-3 两用例 + S-4 注释 + S-2 归档 → 166/166 + check 绿 + 双 dist 重建 → 质检终版通过 → ack
