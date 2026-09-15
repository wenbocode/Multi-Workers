# Spec: goal-autopilot

> Key: goal-autopilot
> 创建时间: 2026-09-06
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（存量格式，三段有真内容，视为已确立）

- 对齐：本 spec 服务于 goal「PM Agent 管理多个 Worker Agent 并行开发」中尚未覆盖的一环——PM 的编排认知工作（拆 key、推进验证、门禁裁决）本身仍需人工逐轮驱动；autopilot 把这部分变为可无人值守的结构化循环，同时保留人工门禁，是「文件驱动的去中心化协调 + goal.md 目标对齐」的自然延伸
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——conductor 必须是文件驱动的机械状态机，无独立状态存储，崩溃重启零成本恢复
  - GC-2: 不修改 pi 核心——console 增强全部经 Extension API
  - GC-3: Worker 进程级隔离——每个判断/执行步骤是独立 worker 进程
  - GC-4: 文件锁并发控制——conductor 与人工会话并发写共享文件走 O_CREAT|O_EXCL 锁
  - GC-5: goal.md 只读锚点——conductor 永不写 goal.md（仅读作对齐输入）
  - GC-6: 30 分钟 worker 超时看门狗（继承现有机制）
  - GC-7: 凭证隔离——每个 worker 只拿到所需 provider 凭证
  - GC-8: 工具白名单按任务类型——新增判断-worker 类型必须有显式白名单条目；autopilot 派发路径下未知 type 一律拒绝派发，不得回退全量工具集（fallback 全集行为仅限手动模式保持不变，additive 原则）
- 冲突：无。goal 约束「不引入中心化调度器」与 conductor 的关系已澄清：conductor 复用既有 `_workers.parallel` 派发通道与 advance_phase.py 门禁，自身不持有调度状态库，属于文件驱动的推进器而非调度器
- 预期收益：本 key 达成后对项目目标的具体贡献（done 时在 achieved.md 对照判定）：
  - 人工交互频率从「每 phase 一次」降为「每 stage 一次」——判定方式：一个 stage 生命周期内人工门禁应答次数（预期 = 2：stage 确认 + stage 闭环）与 phase 自动推进次数（预期 ≥ stage 内 key 数 × 3）之比
  - token 发散结构性受控——判定方式：全部发散回路（L1↔L2 / L3 收敛 / retry）无一超过配置上限，超限一律升级人工（时间线可审计）
  - 手动工作流零回归——判定方式：现有手动工作流测试套件全绿 + 未启用项目无任何 conductor 写入

## §1 功能概述

### 1.1 目标

在 mw + AgenticTask 工作流之上增加一层自主编排能力：给定已确立的项目 goal，系统自动生成按 stage 分批的 key 路线图（`_roadmap.md`），人工确认 stage 批次（各 key 的 roadmap 作用、相互依赖、闭环后达成的阶段目标）后，conductor 自动循环推进该 stage 内全部 key 的完整生命周期（spec→design→plan→tasks→execute→verify），推进中的门禁判断由三层机制完成（L1 证据审计脚本 → L2 门禁裁决 worker → L3 QG 后终局裁决），所有发散回路有硬上限，key 内 phase 边界自动放行、stage 边界与异常路径必停人工。人工通过无状态监控台（console）随时观测、回答门禁、介入或接管，监控台关闭不影响自主推进。

（调研：evidence/research/spec-existing-capability-survey-2026-09-06.md、evidence/research/spec-gate-semantics-2026-09-06.md）

### 1.2 技术栈 / 语言

- conductor + L1 审计脚本：Python（mw 服务内新增模块）
- console 命令与视图：TypeScript（agent-team-loop extension 内新增 `/autopilot` 命令集）
- 判断-worker：复用现有 worker 协议（task.md + type 路由 + 工具白名单）
- 复用既有：advance_phase.py、_workers.parallel 派发通道、ClaimId 体系、file-lock

### 1.3 核心用户场景

1. **stage 启动**：goal 已确立的项目所有者开启 autopilot → roadmap-writer 从 goal + 记忆文档产出 `_roadmap.md` stage 提案 → 所有者确认 stage 1（key 作用/依赖/阶段目标）→ 系统自主运行整个 stage
2. **门禁判断**（系统侧，无人在场）：spec→design 推进前，L1 审计证据齐全性并输出结构化 dossier；有缺口则 L2 worker 裁决（补证/升级）；L1↔L2 循环 ≤ 2 轮，超限转人工门禁
3. **监控与断点重开**：所有者随时打开/关闭 console——打开即见 stage 进度、未决 gate 队列、离线期间事件回放；回答 gate 后流程继续；关闭期间自主推进不停
4. **异常升级**：某 key L3 两轮不收敛 → 标记 stalled + 证据链 + 人工门禁 + 遗留问题草稿 + pattern 沉淀；依赖它的 key 阻塞，无依赖的继续
5. **混合模式**：所有者手动驱动某 key 一段时间后交给 autopilot 接续；autopilot 正在跑的 key 被人工强制接管——两个方向都无缝（状态全在文件）；autopilot 永不碰人工 live-claim 的 key

### 1.4 范围说明（不做什么）

- 不做图形界面（console = TUI 命令 + 文件输出）
- 不修改 AgenticTask 框架的 phase 语义与门禁规则（conductor 只调用 advance_phase.py，不重写）
- 不自动 git commit / push / PR（执行层遵守既有规则，提交决策留人工）
- 不写 goal.md（GC-5）；goal 变更只经 `/goal` 工作流或用户明确指示
- 不做跨项目调度（单项目内）
- 不替代人工对 spec 的最终责任：goal 级歧义、L2 无法裁决的缺口一律升级人工，不猜测推进
- V1 不含：replanner-worker 的自动重规划（预留升级出口，见 §4 待确认）

## §2 业务约束

### 2.1 平台 / 环境

- Windows（用户裁决 2026-09-10：Unix/Linux 覆盖出范围，Q-X-UNIX 关闭；原「Windows + Unix 跨平台」双平台要求作废，文件锁/原子替换/newline 对称读写以 Windows 语义为准）
- conductor 常驻 mw 服务（`mw serve` 管理生命周期，随服务启停）；mw serve 托管多项目时，每个启用 autopilot 的项目各一个 conductor 实例，按项目隔离，不跨项目共享状态
- 未启用 autopilot 的项目：conductor 不启动，项目内零新增行为（opt-in per project，默认关闭）

### 2.2 性能指标

- conductor 轮询间隔 ≤ 5s（与 launcher 一致）
- gate 回答文件落盘后，conductor 在首个后续 tick 内读取并推进（AC-016，erratum 2026-09-10：回答可能落在 tick 睡眠期，消费时延 ≤ interval + tick 处理开销；原「≤ 1 个轮询间隔」的字面阈值在竞态下不可达，AC-002 的 ≤ 2×interval 主合同不变）；stage 门禁回答后的该 stage 首个派发行 ≤ 2 个轮询间隔（AC-002，含 key 认领与 spawn 准备）
- console 重开后视图重建 ≤ 10s（仅凭文件）
- 回合预算（全局单处配置，默认 2）：L1↔L2 循环、L3 收敛循环、task retry 三类回路共用同一上限源；token 消耗由回合上限结构性约束，不依赖 agent 自觉

### 2.3 安全约束

- 凭证隔离继承（GC-7）：判断-worker 与执行 worker 同样只拿所需 provider 凭证
- L2 worker 的文件读取限于 dossier 指针集合 + 白名单路径（有界定点读取，禁自由浏览）
- conductor 仅访问项目内 `.agenticdoc` 相关文件；无 goal.md 写权限（GC-5）
- 人工门禁回答以文件为准（谁写的 gate 由 ClaimId/时间线审计）

### 2.4 集成依赖

- mw 服务（launcher.py / proxy_multi.py / PID 管理）——conductor 作为新增模块挂载
- agent-team-loop extension（PM 模式的命令注册、watch widget、poll loop）——console 增强基础
- AgenticTask 框架脚本（advance_phase.py / update_index.py / guard_pm_state.py）——唯一推进通道与 claim 体系
- 既有 worker 协议（task.md / output.md / trace.log）——判断-worker 复用（含 [GOAL_CHECK]：autopilot 派发的 worker 每个 phase 完成时同样记录 goal mtime，goal 约束第 7 条后半段的显式继承）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-08T20:31:02Z，编号永不回收

> **Errata（2026-09-08，design review ga-spec-design-review-2 B1/N6 处置；编号与语义不变，仅措辞勘误）**
> - AC-020 「全部行 7 列完整性校验通过」→ 「全部行按各文件实际列数完整性校验通过（`_index.parallel` 7 列 / `_workers.parallel` 8 列含 model，与现网格式一致）」；意图不变：无半写行、无丢失更新
> - AC-017 「含时间戳与 key 标识」→ 「含时间戳与 key 标识（key 级事件填 key；stage 级/全局事件填 stage 编号或 '-' 哨兵，不得为 null）」；意图不变：每行可归属

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 goal 已确立且 autopilot 已启用的项目上，roadmap 生成流程完成后，`_roadmap.md` 中每个 stage 节均包含 key 清单（≥1 个 key）、key 间依赖声明、阶段目标三要素，roadmap 校验脚本对全部 stage 校验 exit 0 |
| AC-002 | 在 stage 提案已生成且 stage 门禁未回答的条件下，conductor 对该 stage 派发的 worker 任务行数为 0（查 `_workers.parallel`）；stage 门禁回答文件写入后 ≤ 2 个轮询间隔内出现该 stage 首个派发行 |
| AC-003 | 在 stage 内全部 key 到达终态（done 或人工裁决关闭）的条件下，conductor 在 1 个轮询间隔内生成 stage 闭环 dossier（含各 key L3 裁决与证据引用）并创建下一 stage 人工门禁文件，且在回答前对下一 stage 的派发行数为 0 |
| AC-004 | 在 stage 已激活、某 key 依赖全部满足且未被人工窗口 live-claim 的条件下，conductor 在 10s 内派发该 key 的首个 phase worker；两个无依赖 key 同时满足条件时并行推进（默认 max-parallel-keys ≥ 2） |
| AC-005 | 在任何 phase 推进路径上，conductor 对 pm-state.md Phase 字段的直接写入次数为 0 且对 goal.md 的写调用次数为 0，全部推进经 advance_phase.py 完成（静态检查 conductor 代码无 Phase 直写、无 goal.md 写调用 + 调用日志留痕） |
| AC-006 | 在某 key L3 连续 2 轮裁决不达预期的条件下，该 key 被标记 stalled，1 个轮询间隔内生成含证据链引用的人工门禁文件，achieved.md 遗留问题节写入条目草稿并生成 pattern 文件；依赖该 key 的 key 派发行数为 0，无依赖 key 照常推进（1 个轮询间隔内派发行数 ≥ 1） |
| AC-007 | 在给定 `{key}/spec.md` 与 `evidence/` 目录的条件下，L1 审计脚本输出 JSON dossier，含 AC 清单、决策点→证据文件映射、缺口列表三部分；对证据齐全样例 exit 0，对缺失 research 留底样例 exit 1 且缺口列表非空 |
| AC-008 | 在 L1↔L2 裁决回路达到配置上限（默认 2 轮）的条件下，conductor 对第 3 轮 L2 worker 的派发数为 0，并在 1 个轮询间隔内生成人工门禁文件 |
| AC-009 | 在 L2 worker 执行期间，其文件读取限于 dossier 引用的指针集合加白名单路径，白名单外读取调用被拒绝且在 output.md 留拒绝记录（含被拒路径与命中规则） |
| AC-010 | 在 quality gate 已通过的条件下，L3 review worker 输出 meets/below 二值裁决；below 时派发修复 task 后复评，复评总轮数 ≤ 2 |
| AC-011 | 在全局回合预算配置修改为 1 的条件下，L1↔L2、L3 收敛、task retry 三类回路均在 1 轮后升级（人工门禁或 stalled），第 2 轮派发数为 0 |
| AC-012 | 在 autopilot 未启用的项目上，conductor 进程不存在（`mw status` 不显示），现有手动工作流测试套件（packages/multi-workers/ 下 test_*.py 与 smoke_test.sh，按 mw-dispatch-reliability key 的 L0/L1/L2 矩阵执行）结果与引入前一致（全绿），`.agenticdoc` 下无 conductor 写入的新文件 |
| AC-013 | 在某 key 被人工窗口 live-claim 的条件下，conductor 跳过该 key 且时间线记录 1 条 skip 事件；人工 force 接管 conductor 持有的 key 后，conductor 在 1 个轮询间隔内对该 key 的新增派发行数为 0 |
| AC-014 | 在某 key 已由手动方式推进到 EXECUTE 后交给 autopilot 的条件下，conductor 从 pm-state.md 恢复其 phase 继续推进，已完成 phase 的 artifact 文件 mtime 不变（不重做） |
| AC-015 | 在 console 进程关闭后重新打开的条件下，console 在 10s 内仅凭文件（roadmap / 索引 / gate 队列 / 时间线）重建 stage 进度视图与未决 gate 队列，并按 last-seen 时间戳过滤回放离线期间事件；`/autopilot status --json` 输出同一状态集（stage 进度 / gate 队列 / 时间线水位），作为可机械校验面 |
| AC-016 | 在人工通过 `/autopilot gate <id> approve` 回答门禁的条件下，回答文件落盘后 conductor 在首个后续 tick 内读取并推进对应流程（时延 ≤ interval + tick 处理开销；erratum 2026-09-10：原「1 个轮询间隔（≤5s）」字面阈值在回答落盘于 tick 睡眠期的竞态下不可达，AC-002 的 ≤2×interval 主合同不变） |
| AC-017 | 在 conductor 发生状态转换（phase 推进 / worker 派发与完成 / gate 生成与回答 / stalled / skip）的条件下，事件时间线文件对每个事件追加 ≥1 行条目（含时间戳与 key 标识），条目追加与 console 是否打开无关 |
| AC-018 | 在 console stage 视图打开的条件下，每个 key 显示其各回路（L1↔L2 / L3 / retry）已用轮数与剩余预算，数值与 `/autopilot status --json` 暴露的回合计数一致（持久化位置由 design 定义，--json 为唯一校验面） |
| AC-019 | 在 conductor 存活期间，以时间线/日志循环节拍度量：任意 60s 观测窗内 ≥ 12 个节拍事件（最大轮询间隔 ≤ 5s） |
| AC-020 | 在 conductor 与人工 PM 会话并发写 `_workers.parallel` 与 `_index.parallel` 的条件下，双方写入均不丢失、无半写行（全部行 7 列完整性校验通过） |
| AC-021 | 在 autopilot 派发路径上，roadmap-writer（含 write，需写 `_roadmap.md` 提案）/ L2 verifier（review 级：read/find/grep/ls）/ L3 review（review 级）/ repair（coding 级）各类型均有显式工具白名单条目；对未注册 type 的派发请求，conductor 拒绝派发（行数 0）并记录时间线，不回退全量工具集 |
| AC-022 | 在 conductor 于 stage 执行中被杀死并重启的条件下，重启后 2 个轮询间隔内从文件恢复状态继续推进：同 key 同 phase 的 worker 进程数 ≤ 1（无重复派发）、回路预算计数与重启前一致、已完成步骤的 artifact mtime 不变 |
| AC-023 | 在 autopilot 派发的 worker 以任意方式失败（exit 1、看门狗超时、spawn 凭证失败）的条件下，该失败计入所属回路的 retry 预算并按 AC-011 升级；且单个 worker 失败不阻塞同 stage 其他 key 的派发（其他 key 派发行数照常 ≥ 1） |
| AC-024 | 在 stage 门禁被 reject 的条件下，roadmap-writer 重新提案一次（计入其回合预算）；再次 reject 后 conductor 停止自动提案并等待人工直接编辑 `_roadmap.md`；在 stalled 门禁被 reject 的条件下，该 key 按遗留问题路径关闭（achieved.md 草稿保留），不阻塞 stage 闭环 |
| AC-025 | 在未启用项目执行启用流程（配置开启）后，`mw status` 显示 conductor 运行中，且 1 个轮询间隔内 roadmap 提案流程启动（roadmap-writer 派发行出现） |

## §4 风险与未决项

- 风险：判断粒度细化（spec/design/plan 分属不同 worker 上下文）导致跨阶段一致性下降——缓解：dossier 与 artifact 作为交接契约，L1 在每个 phase 门禁点校验前序 artifact 完整性
- 风险：conductor 与 AgenticTask 框架语义漂移——缓解：AC-005 强制只调脚本；框架升级时 conductor 零改动跟随
- 风险：roadmap stage 划分错误发现过晚——缓解：stage 门禁滚动复核 + 闭环判定显式化（AC-003 dossier）；错误成本限制在单个 stage 内
- 风险：人工不在场时 gate 堆积导致 stage 长期停滞——接受（自主性暂停优于错误推进）；时间线与 gate 队列保证可见性
- 风险：Windows 文件锁与原子替换边界情况——缓解：复用 file-lock 既有实现，AC-020 并发测试双平台覆盖
- 风险：worker 失败/超时在无人值守下无人察觉——缓解：AC-023 计入 retry 预算并升级，时间线留痕；spawn 凭证失败 per-task 隔离（§5 坑点）
- 风险：新增判断-worker 类型白名单缺失导致越权工具——缓解：GC-8 + AC-021 显式条目 + 未知 type 拒绝派发
- 待确认：max-parallel-keys 默认值（下限 ≥2 已由 AC-004 锁定，具体值 design 定）、gate 文件 schema、L2 定点读取上限（文件数/字节预算）、回合计数持久化位置、roadmap-writer 的 CLI 路由——均在 design 阶段定
- 待确认：replanner-worker（execute 期自动重规划）是否进 V1——当前设计为预留升级出口（stalled 即人工），V1 不含

## §5 记忆前馈（对接项目级记忆门禁）

> 记忆三件套（_project_log.md / _arch_snapshot.md / _pitfalls.md）当前不存在，本节以仓库实际资产与已完结 key 的执行记录如实填写。

### 可复用资产

- advance_phase.py / guard_pm_state.py：phase 推进唯一通道与直写拦截，conductor 直接调用（勿重造门禁）
- `_workers.parallel` 派发通道 + worker-store.ts（TS）/ launcher.py（Py）双侧读写 + file-lock.ts：conductor 派发判断/执行 worker 全部走此通道
- ClaimId 体系（update_index.py + claimState held-live 检测）：人工/autopilot 所有权互斥直接复用
- agent-team-loop PM 会话：startWorkerPollLoop / watch widget / restoreWatch——console stage 视图与断点恢复的现成基础
- worker 协议（task.md + type 路由 + 工具白名单 + output.md 四节 + trace.log [GOAL_CHECK]）：判断-worker 仅需扩 type 语义
- pm-mind 分层降级验证（L0/L1/L2）与 U9 pattern 机制、achieved.md Hook 3 遗留问题去向：L1/L3 的失败出口复用既有框架约定，不发明新机制

### 需规避坑点

- worker spawn 凭证失败必须 per-task 隔离，一个任务失败不得拖垮整批派发（来源：mw-dispatch-reliability key 的核心修复内容）
- `_workers.parallel` 陈旧条目（stale entries）需清理机制，避免 launcher 误判（来源：mw-dispatch-reliability）
- 管道分隔文件解析的 trailing-space/空行处理：split 后必须 filter 空行（来源：agent-team-loop VC-041 bug 及修复）
- Windows 下 CRLF/UTF-8 读写不对称会写出双 \r——读写必须 newline 对称 + 原子替换（来源：update_index.py P1-1 修复注释）
- mw serve 启动确认需 stability window，启动即死的进程会误报 started（来源：mw-dispatch-reliability AC-005）
