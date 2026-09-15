# Task T-07: state.py（零私有状态全推导）

## 基本信息
- Stage: 1
- 代码状态: 代码完成（autopilot/state.py）
- 验证状态: 验证通过（test_autopilot_state.py 11 passed，[VERIFY] VC-015/016/020/024 ×7；全量 228 passed 零回归）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-013, AC-014, AC-018, AC-022]
- vc_refs: [VC-015, VC-016, VC-020, VC-024]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/state.py`（D-102 / D-111 / D-115）。conductor 零私有状态文件，一切从文件推导：

- **phase 推导**：读 `_index.parallel`（7 列格式）→ key → phase/status/claim_id 映射；解析容错（trailing-space/空行 filter，_workers 7|8 列容错在并读时同规则）
- **claim 存活**：复刻 TS parseClaim/claimState 语义——claimId = `host:pid`；存活检查 = host 匹配本机 && `mw_common._is_alive(pid)`；无法解析 → 视 stale（F9）
- **loop 回合计数**：扫 `{key}/workers/<task>/task.md` 的 `loop:` 标签 + 队列行终态 → 各回路已用回合数（l2:{key}:{edge} / l3:{key} / exec:{key}:{stem} / repair:{key} / roadmap:stage-{N}；一回合定义见 design §4.1 round 单位表）
- **[START] 进程观测**：task 目录 trace.log 内 `[START] pid=<pid>` 行计数 + pid 活性（D-115；进程唯一性口径，非行数代理）
- **孤儿检测**：`_workers.parallel` 中 ap- 前缀行 vs task 目录 / loop 状态的对账辅助（孤儿和解由 conductor 主循环调用，D-102：同 attempt 重插不新计）
- **artifact mtime**：key 目录内 spec.md/design.md/plan.md/tasks/ 的 mtime 快照接口（AC-014/AC-022 不变断言的取数点）

## 输入
- 依赖文件: `_index.parallel`、`_workers.parallel`、`mw_common._is_alive`、既有 trace.log 约定
- 依赖 Task: T-02（包结构）
- AC 约束:
  > AC-013: 在某 key 被人工窗口 live-claim 的条件下，conductor 跳过该 key 且时间线记录 1 条 skip 事件；人工 force 接管 conductor 持有的 key 后，conductor 在 1 个轮询间隔内对该 key 的新增派发行数为 0
  > AC-014: 在某 key 已由手动方式推进到 EXECUTE 后交给 autopilot 的条件下，conductor 从 pm-state.md 恢复其 phase 继续推进，已完成 phase 的 artifact 文件 mtime 不变（不重做）
  > AC-018: 在 console stage 视图打开的条件下，每个 key 显示其各回路（L1↔L2 / L3 / retry）已用轮数与剩余预算，数值与 `/autopilot status --json` 暴露的回合计数一致（持久化位置由 design 定义，--json 为唯一校验面）
  > AC-022: 在 conductor 于 stage 执行中被杀死并重启的条件下，重启后 2 个轮询间隔内从文件恢复状态继续推进：同 key 同 phase 的 worker 进程数 ≤ 1（无重复派发）、回路预算计数与重启前一致、已完成步骤的 artifact mtime 不变
- 设计约束:
  > D-102: 零私有状态 + 孤儿和解 + goal 基线
  > D-103: claimId 互操作 = 真实 host:pid
  > D-111: round 单位表（修复派发属同回合修复动作不另计）

## 预期产出
- `packages/multi-workers/autopilot/state.py`
- `packages/multi-workers/test_autopilot_state.py`（fixture task 目录 + index/workers 样例）：
  - phase 推导（7 列解析、空行/trailing-space 容错）
  - claim 存活/死亡/stale 三态（含 host 不匹配 → 死）
  - 回合计数：多 loop 标签混合、修复同回合不另计、exec 终态计数
  - [START] 计数 + pid 活性
  - 孤儿对账辅助 + artifact mtime 快照
- 验证方式: `[VERIFY]` 行输出；rounds 推导源同时是 VC-020 parity 的 Python 侧
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 12:20-12:50 | 读 design §4.1 round 单位表 / D-102 / D-103 / D-115 + TS ui-bridge claimState + 框架 update_index 解析协议 → 实现 state.py：KeyState 推导（7 列容错 + legacy 5 列迁移）、claim_state 四态、used_rounds（distinct attempt 去重，缺 attempt 退化为按目录计数）、[START] pid 观测、孤儿对账（normcase/normpath 归一化匹配）、artifact mtime 快照 + test_autopilot_state.py 11 用例 | 11 passed；[VERIFY] 行 ×7（VC-015/016/020/024）正常 emit；全量 235 passed（含 t04 在途 7 个临时收集，本 task 独立贡献 228） |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 设计取舍备注
- claim 非对称（有意）：TS claimState 对 host 不匹配返回 held-live（人工接管需 --force）；conductor 侧按任务书返回 dead——conductor 在本机跑本 checkout，无法验证外部 pid，保守 skip 会让外部窗口崩溃后永久阻塞 key。已在模块 docstring 锁定
- 回合计数：round = loop 内 distinct attempt 值；同 attempt 修复派发不另计、孤儿同 attempt 重插不新计、在飞（未终态）也计消耗（task.md 从派发事务起即存在）；缺 attempt 标签退化为 D-102 原始文件计数（按目录身份去重）
- mw_common 复用而非重造：_is_alive（Win32 退出码口径，与 TS/框架不 disagreed）与 parse_workers_file（7|8 列容错）；state.py 带脚本模式 sys.path 引导（conductor.py 直跑场景）
- 孤儿匹配路径归一化：os.path.normcase + normpath（行内正斜杠 vs 盘上反斜杠、Windows 大小写均兼容）

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
