# Research: conductor 进程模型、挂载方式与状态推导（design）

## 决策问题

conductor 以何种进程模型挂载 mw 服务、opt-in 配置放哪、GC-1「无独立状态存储」下回合预算计数与崩溃恢复如何落地（支撑 spec §1.1 / §2.1 / §2.2 / AC-011 / AC-018 / AC-022 / AC-025）。

## 调研方法与出处

通读以下源文件（全文或相关函数）：

- `packages/multi-workers/mw.py` cmd_serve（L136-262）：serve 进程管理 proxy + launcher 两个 Popen 子进程，1s 主循环检查 stop 请求与子进程存活，finally 统一 terminate；PID 文件 `.mw/mw.pid`；`cmd_status`（L265-276）读 PID 判运行
- `packages/multi-workers/launcher.py` run/_poll_once（L238-337）：launcher 内存 `running_procs` dict 持有 worker 进程；队列行状态经 `mw_common.update_status` 回写；崩溃重启 launcher 后靠 `_workers.parallel` 行 status=running 恢复语义
- `packages/multi-workers/mw_common.py` L330-463：`acquire_lock`（O_CREAT|O_EXCL，重试 20 次指数退避）、`parse_workers_file`（容忍 7/8 列）、`_write_workers_file`（tmp+replace 原子替换）、`archive_stale_entries`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts` L1-80：_index.parallel 7 列（key|status|phase|claimId|deps|desc|updated），AgenticTask 表格格式
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` L64-110：claimId 格式 `host:pid`，`parseClaim` 要求数字 pid，`claimState` 用 pid 存活性判定 held-live/held-stale
- `.agents/skills/agentic-task/scripts/advance_phase.py`（全文）：GATES 表（design 需 spec≥500B+research≥1；plan 需 mermaid 校验；done 需 achieved.md≥200B + pm-state 含 PASS + quality-gate-report）；`update_pm_state` 用正则替换 `- Phase:`/`- Updated:` 接口行，漂移即 exit 1
- `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`（全文）：TS 侧 upsert 持 workers.lock，8 列序列化（model 列）

## 发现

1. **子进程挂载模式现成**：mw serve 已用「Popen 子进程 + 1s 主循环监护 + stop 请求 + finally terminate」管理 launcher；conductor 作为第三个同构子进程零新机制，且获得与 serve 不同的崩溃域（serve 死 ≠ conductor 死，反之亦然——但 finally terminate 保证 serve 退出时 conductor 跟随，无孤儿）
2. **AC-025 的启用时延可达**：serve 主循环 1s tick 检查配置 mtime → spawn conductor；conductor 首个 tick（间隔 ≤5s）即派发 roadmap-writer。链路 ≤6s，满足「1 个轮询间隔内 roadmap 提案流程启动」
3. **worker 进程所有权在 launcher**：conductor 只写队列行、从不 spawn 进程——conductor 重启（AC-022）对运行中 worker 零影响；恢复 = 重读共享文件推导位置
4. **claimId 互操作约束**：conductor 认领 key 必须写 `host:pid` 格式（pid 数字），否则 TS 窗口 parseClaim 失败当作 stale 可强行接管；用 conductor 自身真实 pid 即可双向 held-live 判定
5. **状态推导的事实源齐备**：key phase 在 _index.parallel 第 3 列；派发历史在 {key}/workers/*/task.md（可带任意 frontmatter 标签）；gate/roadmap/时间线为本设计新增共享文件——无需 conductor 私有 state 文件即可推导全部状态（GC-1 成立）
6. **回合预算可从 task 目录推导**：task.md frontmatter 加 `loop:`/`attempt:` 标签后，`count(loop==L)` 即已用回合数；重命名/轮转不影响（task 目录不轮转）；console 与 conductor 读同一来源，AC-018 数值天然一致
7. **已知良性竞态**：TS `dispatchNewTasks`（pm-orchestrator.ts L300-345）扫描 task.md 无锁，conductor「写 task.md→写队列行」间隙可能被 TS 窗口抢先 upsert 同 taskKey 行；两侧行内容等价（cli=pi/provider=timi），launcher `running_procs` 内存去重保证不双 spawn，行状态最坏被重置 pending 后由 reap 修正——影响有界，无需引入跨语言锁协议

## 发现

8. **plan.md / tasks/ 实际格式（D-111 取证）**：`.agenticdoc/mw-dispatch-flow-fixes/plan.md`（实测）：Stage 总览表（Stage|目标|Tasks|覆盖 VC|依赖|出口判据）列 T-NN 任务集，Stage 明细节内 `- T-NN <描述>` 逐行列出；`.agenticdoc/agent-team-loop/tasks/`（实测）：任务文件命名 `T-NN-<slug>.md`（如 T-01-task-protocol.md）。EXECUTE 期推导 = 枚举 `{key}/tasks/T-*.md` ↔ plan.md T-NN 行映射，task id 即文件名前缀，无需新清单文件

## 结论 → 决策映射

- D-101 conductor = mw serve 的第三个 Popen 子进程（`autopilot/conductor.py --project=...`，`.mw/conductor.pid`，serve 1s tick 按配置监护）→ spec §2.1、AC-025
- D-102 零私有状态：全部状态从共享文件推导（含 loop/attempt 标签计数）→ GC-1、AC-011、AC-018、AC-022
- D-103 conductor 用真实 `host:pid` 认领，人工窗口 force 接管后 conductor 1 tick 内转 skip → AC-013
- D-104 良性竞态以设计注记 + 测试覆盖（AC-020 并发完整性）而非新锁协议
- D-111 EXECUTE 状态从 tasks/ 文件名前缀 + plan.md T-NN 行映射推导（发现 8 实测格式）→ AC-014、D-102 同源
- D-109/D-110/D-112 为自含算术或结构约定，无外部事实断言（60s/间隔算术、目录约定、AC-021 锁定的直接推论），按 checklist 无需外部取证

## 修正段（ga-spec-design-review-2 处置，2026-09-08）

1. **发现 2 算术错误勘正（review B10）**：原文「链路 ≤6s，满足『1 个轮询间隔』」不成立（6 > 5）。修正：conductor 主循环采用 act-then-sleep（D-114），首 tick 进程启动即执行；时延 = serve 1s 检测 + spawn ≈ 0.5s + 首 tick 派发 ≈ 2s < 1 个轮询间隔（4s 默认）。
2. **发现 1 补充（review B10/D-101）**：mw serve 现状对子进程退出是检测后整体退出（break + finally terminate），**不自动重启**；「复用现有完整监护模式」表述过度。conductor 的 respawn（enabled 时意外退出重启，含快速失败退避）是新增行为，不是复用。
3. **发现 8 补充（review B7）**：tasks/ 文件名前缀非全仓唯一——`agent-team-loop/tasks/` 实存重复前缀（T-01-file-lock.md 与 T-01-task-protocol.md）。task 身份改用文件名 stem + `ap-{key}-{stem}` 队列键（D-111 改写）。
4. **新增事实（review B8）**：`worker-mode.ts parseTaskMd` 的 agenticdocRoot = `dirname(dirname(taskPath))` = `.agenticdoc/{key}/workers`——outputDir 路径契约正确，但 `goalMtime` 实际 stat `{key}/workers/goal.md` 恒 miss → [GOAL_CHECK] 记 0；全仓 trace.log 无一条 GOAL_CHECK（潜在未触发）。修复方案 D-116。
