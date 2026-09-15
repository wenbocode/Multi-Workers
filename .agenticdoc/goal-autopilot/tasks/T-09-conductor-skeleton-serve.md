# Task T-09: conductor 骨架 + mw serve 集成

## 基本信息
- Stage: 2
- 代码状态: 代码完成（autopilot/conductor.py + mw.py + mw_common.py）
- 验证状态: 验证通过（test_autopilot_conductor.py 15 passed，[VERIFY] VC-021 ×3 / VC-027 ×2；全量 276 passed 零回归）
- 负责 Agent: PM 窗口（WENBOZHOU-PC4:8420，用户指令直执）
- ac_refs: [AC-005, AC-019, AC-025]
- vc_refs: [VC-007, VC-021, VC-027]
- pattern_refs: []

## 描述
新文件 `packages/multi-workers/autopilot/conductor.py` + 改 `packages/multi-workers/mw.py`。

**conductor.py 主循环骨架**（§5.1）：
- CLI：`python autopilot/conductor.py --project <dir> [--poll-interval S] [--once]`（--once = 单 tick 可测入口）
- **act-then-sleep**（D-114）：进程启动立即执行首个 tick，不等第一个间隔
- 每 tick 顺序：追加 beat 事件 → 检查 `enabled && not paused`（config mtime 缓存）→ goal.md mtime 变化检测（对比启动时基线快照，D-102）→ halt + goal-change gate 一次 → 后续步骤（stage/gate/per-key 机在 T-10/T-11/T-12 接入，本 task 留接口）
- **tick 级异常捕获**：任何未捕获异常 → 捕获 + timeline config 事件 + 下一 tick 继续（单 tick 失败不终止循环）
- **stale lock 窃取**（D-113）：conductor 侧统一锁包装（workers.lock / gates.lock / roadmap.lock / key-{key}.lock）——acquire 重试耗尽后检查锁文件 mtime，age > 30s → 删除后重取 + timeline config 事件；依据 = conductor 持锁均为毫秒级，>30s ⟹ 持有者已死。TS 侧锁协议不动
- **启动门禁**：advance.py 框架缺失 → 拒绝启动（stderr + exit 1）

**mw.py serve 集成**（D-101）：
- serve 1s 主循环检查各项目 config（mtime 缓存）→ enabled 且 `.mw/conductor.pid` 无存活进程 → spawn conductor.py；disabled → terminate
- finally 终止集合加入 conductor（复用 launcher 的 terminate/wait 逻辑，无孤儿）
- conductor 死 → serve 1s 内 respawn（存活自愈）
- `mw status` / `mw doctor` 增 conductor 行（PID、存活、最近 tick 水位 = timeline 最新 seq/ts）
- conductor.log 由 serve 重定向（与 launcher.log 同模式）；Windows CREATE_NO_WINDOW spawn

## 输入
- 依赖文件: mw.py（serve 循环/terminate 集合）、autopilot/config.py + advance.py + timeline.py（T-02/T-04）
- 依赖 Task: T-01（基线）、T-02、T-04
- AC 约束:
  > AC-005: 在任何 phase 推进路径上，conductor 对 pm-state.md Phase 字段的直接写入次数为 0 且对 goal.md 的写调用次数为 0，全部推进经 advance_phase.py 完成（静态检查 conductor 代码无 Phase 直写、无 goal.md 写调用 + 调用日志留痕）
  > AC-019: 在 conductor 存活期间，以时间线/日志循环节拍度量：任意 60s 观测窗内 ≥ 12 个节拍事件（最大轮询间隔 ≤ 5s）
  > AC-025: 在未启用项目执行启用流程（配置开启）后，`mw status` 显示 conductor 运行中，且 1 个轮询间隔内 roadmap 提案流程启动（roadmap-writer 派发行出现）
- 设计约束:
  > D-101: conductor = mw serve 第三子进程；崩溃域非对称；serve 专属监护
  > D-114: act-then-sleep；AC-025 链路时延 ≈2s < 1 间隔
  > D-113: 仅 conductor 侧锁自恢复，非全局协议变更

## 预期产出
- `packages/multi-workers/autopilot/conductor.py`
- `packages/multi-workers/mw.py` 改（serve 监护 + status/doctor 行）
- `packages/multi-workers/test_autopilot_conductor.py`：
  - --once tick：beat 追加、disabled/paused → idle、goal mtime 变化 → halt + gate 一次（重复 tick 不重复建 gate）
  - tick 异常注入 → 循环存活 + config 事件
  - stale lock：age>30s 窃取、<30s 等待
  - serve 集成单测（config mtime 缓存、spawn/terminate 决策函数；真实进程链路在 T-16）
- 验证方式: `[VERIFY] VC-021`（beat 单元级）/ `[VERIFY] VC-027`（act-then-sleep 首 tick 即动作，真实链路 T-16）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10 14:50-15:20 | 读 mw.py 全文 + S1 模块 API（config/gates/timeline/advance）→ conductor.py：beat 首位/enabled 门/goal mtime 基线检测→halt+goal-change gate 一次（锁内幂等重查，重启存活）/gate 答复后基线重置/tick 异常→config 事件存活/编排钩子 orchestrate() 留 T-10/11/12/陈锁窃取包装（快取 4 重试→mtime age>30s 窃取+config 事件/<30s ConductorLockHeld）/启动门禁（locate_platform_dir 失败→stderr+exit 1）/--once 单 tick 入口/act-then-sleep 首 tick 即动作 → mw.py：serve 循环每秒监护步（config mtime 缓存 + pid 文件活性 + 内存 proc 三源判定→spawn/terminate）、conductor 死不破 serve、finally 终止集合加 conductor、conductor.log 同 launcher.log 模式、status/doctor 增 conductor 行（PID+存活+timeline 尾 seq/ts 水位） → mw_common.format_doctor_text 增 conductor 行渲染（informational 不翻 healthy） + 测试 15 用例 | 15 passed；全量 276 passed 零回归 |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E1 | 测试自伤 | test_autopilot_conductor.py | `FileNotFoundError: ...\.mw\conductor.pid`（pid 文件父目录未建）+ state 基线在 goal.md 存在前捕获致误触 goal-change | 已修：先建目录；两阶段构造（disabled 先行再 enable） |
| E2 | 环境抖动 | test_integration.py::TestConcurrentWrites | 首跑 1 failed；单独复跑 ×2 + 全量复跑均 passed——并发时序抖动，非本改动（不触碰 launcher 队列写路径） | 无需处置 |

### 设计取舍备注
- goal-change 幂等以目录真相为准（pending gate 扫描）而非内存标志：conductor 重启后 open gate 仍 halt（测试覆盖）；启动基线取启动时 mtime，重启天然吸收已发生的变更
- goal-snapshot 事件在启动与 gate 答复后基线重置两处写入（D-109 事件枚举语义）
- 陈锁窃取判定链：快取（4 重试×0.02s 指数）→耗尽后 stat age→ >30s 删+重取+config 事件 / <30s 抛 ConductorLockHeld 由 tick 下一轮重试；锁消失克竞态用普通全重试克取
- serve 监护活性三源：pid 文件（check_pid）∪内存 proc.poll()——spawn 后 pid 文件写入前的窗口由内存 proc 填补，不会双 spawn
- AC-005 静态检查实现为机械断言：conductor.py 全部 write 调用行不含 goal/phase 字样（pid 文件是唯一写入点）

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
