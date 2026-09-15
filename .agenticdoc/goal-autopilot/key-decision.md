# KDR: goal-autopilot

## R（需求）

- 技术栈: Python（conductor + L1 审计脚本，mw 服务内）+ TypeScript（console `/autopilot` 命令集，agent-team-loop extension）+ 复用 AgenticTask 脚本与 worker 协议
- 边界: 不改 AgenticTask phase 语义、不做 GUI、不自动 commit/push、不写 goal.md、V1 单项目、V1 不含 replanner-worker（预留出口）
- 关键约束:
  - additive 零侵入：未启用时手动工作流行为与测试完全不变；autopilot 功能全部走独立命名空间（/autopilot 命令、_roadmap.md、conductor 模块）
  - 全部发散回路回合上限默认 2，单处配置（L1↔L2 / L3 收敛 / retry 共用），超限一律升级人工——token 失控在结构上不可能
  - conductor 是文件驱动的机械状态机，无独立状态存储，崩溃重启零成本；phase 推进只经 advance_phase.py
  - 人工门禁（硬地板）＝ stage 确认 / stage 闭环 go-no-go / stalled key / goal.md 变更 / 预算耗尽；key 内 phase 边界分层自动（L1 脚本审计 → L2 worker 裁决 ≤2 轮；L3 QG 后终局裁决 ≤2 轮）
  - console 无状态：一切从文件推导（roadmap / 索引 / gate 队列 / 时间线），断点重开 = 正常重开，离线事件按 last-seen 回放
  - 所有权互斥：conductor 不碰人工 live-claim 的 key；人工可 force 接管；模式互换无缝（状态全在文件）

## A（架构）← system-design 追加（v2，含 ga-spec-design-review-2 处置）

- D101 conductor 进程模型: 选 mw serve 第三 Popen 子进程 + respawn，否线程/独立守护（崩溃域非对称；respawn 为新增）
- D102 状态存储: 选零私有文件全推导 + 孤儿和解 + goal 基线，否 state.json（GC-1 + console 同源一致）
- D103 claimId 互操作: 选真实 host:pid，否自定义前缀（parseClaim 兼容，互斥有效）
- D104 派发竞态: 选 origin: conductor 标记 + TS 扫描跳过，否接受良性/跨语言锁（竞态按构造消除）
- D105 gate 协议: 选 per-gate md + frontmatter + 完整 schema（roadmap stage 状态机/key-status/seq 单写者），否单 JSON/pm-state 节
- D106 L2 定点读取: 选 read_scope + tool_call block + containment 算法（段边界/realpath/win32），否 OS 沙箱/自觉
- D107 typed 注册表: 选双侧表 + per-type 精确奇偶 + worker fail-closed，否单源文件/仅 conductor 拒（双保险）
- D108 L3 产物: 选 output 结构化节 + 机械落盘 + done 三件套后验，否给 L3 write（AC-021 锁定不动摇）
- D109 时间线: 选单 jsonl + beat + 轮转 + seq/watermark 协议，否双文件（去重/超代语义闭环）
- D110 配置: 选 _autopilot/config.json，否 .mw/（任务状态邻接、人可见）
- D111 EXECUTE 状态: 选文件名 stem 身份 + ap- 前缀队列键 + 每 key 串行，否 T-NN 前缀/任务清单文件（文件系统唯一性）
- D112 L3 验证方式: 选证据记录制不重跑，否重跑命令（review 级无 bash 的直接推论）
- D113 stale lock: 选 conductor 侧 age>30s 窃取，否全局锁协议改造（自恢复不侵入 TS 侧）
- D114 循环节律: 选 act-then-sleep 首 tick 即动作，否 sleep-first（AC-025 时延 ≈2s < 1 间隔）
- D115 进程观测: 选 [START] pid 行入 trace.log，否行数代理（VC-024 进程级口径）
- D116 agenticdocRoot: 选语义拆分，否改 outputDir 契约（存量 bug：goalMtime 恒 0）
- GC-1 语义澄清（review N5）: 「不引入中心化调度器」= 无中心调度状态库 + worker 间不直接通信（文件驱动协调）；conductor 是单实例控制面推进器（spec §0 已澄清），决策中心化不在禁令范围——此解释经用户 4 轮决策确认

## I（实施）← PM 执行中追加
