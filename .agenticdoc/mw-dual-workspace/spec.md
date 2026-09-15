# Spec: mw-dual-workspace（控制工作区与目标工程分离）

> Key: mw-dual-workspace
> 创建时间: 2026-09-11T14:37:52+08:00
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: 已确立，存量三段有实内容）

- 对齐：goal 核心交付「文件驱动的去中心化协调：_workers.parallel、_index.parallel、goal.md」与「PM Agent 管理多个 Worker Agent 并行开发同一个项目」。本 spec 把「同一个项目」的物理位置从框架工作区解耦：协调文件留在控制工作区，被开发的目标工程（游戏/UE 工程）可位于项目根之外的任意路径，且保持零框架污染。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心，所有功能通过 Extension API 实现
  - GC-2: 不引入中心化调度器，协调通过文件系统（_workers.parallel + 文件锁）
  - GC-3: Worker 进程级隔离（独立 pi 进程）
  - GC-4: _workers.parallel / _index.parallel 并发写使用 O_CREAT|O_EXCL 文件锁
  - GC-5: 工具白名单按任务类型
  - GC-6: goal.md 是项目级目标锚点，Worker 在 phase 完成时记录 goal mtime 到 trace.log
- 冲突：无。目标工程移出项目根不改变协调语义与锁语义；goal.md 锚点随控制工作区，不随目标工程移动。
- 预期收益（done 时在 achieved.md 对照判定）：
  - 游戏/UE 类大型工程零框架污染接入 agent team 开发 —— 判定：AC-002 双树扫描计数为 0
  - 存量单目录用法零迁移成本 —— 判定：AC-001 基线一致性
  - 大型开发目标可按「控制工作区 : 目标工程」比例切割（本 key 交付 1:1 基座）—— 判定：AC-004 双目录 + AC-005 模式切换

## §1 功能概述

### 1.1 目标

为 mw + agent-team-loop 增加「双工作区」运行模式：框架协调文件（`.agenticdoc/`、`.mw/`、`_workers.parallel`、`_index.parallel`、`goal.md`、task.md/trace.log/output.md/phase 文件）全部落在**控制工作区**；实际开发目标（游戏工程等）位于独立目录（**目标工程**），保持零框架污染。控制工作区通过 target 配置认知目标工程：开发契约、编译/测试工具链、上下文防火墙。UE 工程须支持 **Game 与 Engine 两个目录**的显式配置。现有单目录模式完整保留，可通过持久化配置或 mw 指令切换。

### 1.2 技术栈 / 语言

- 扩展：TypeScript（agent-team-loop，pi Extension API）
- 服务：Python 3（mw serve / launcher / conductor）
- 主环境：Windows（盘符、大小写不敏感路径、跨盘目录）

### 1.3 核心用户场景

1. 场景 A（单目录存量）：现有用户在「框架工作区 = 开发目录」下使用，行为与当前完全一致，无迁移成本。
2. 场景 B（UE 双目录）：用户对 UE 工程开发——Game 工程（.uproject 所在）与 Engine 根是两个不同目录；worker 在目标工程上编辑源码、跑构建与测试，两个目录中都不出现任何框架文件。
3. 场景 C（模式切换）：同一控制工作区在单目录与双工作区模式间切换（配置文件或 mw 指令），不改扩展代码、不重建 bundle。
4. 场景 D（上下文防火墙）：大型游戏工程含二进制资产与生成物（.uasset、DerivedDataCache、Intermediate 等），worker 的 read/ls/find/grep 被 deny 规则拦截，上下文不被打爆（实测量级：ProjectH\Content 下 .uasset 1,429,392 个、.umap 2,318 个——调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）。
5. 场景 E（项目认知）：控制工作区维护目标工程的 profile（工具链命令、开发契约、忽略规则），派发任务时注入 worker 上下文；目标工程树不需要放置 AGENTS.md 或任何框架注入文件。

### 1.4 范围说明（不做什么）

- 不包含：多控制工作区共享同一目标工程的跨工作区锁（N:1 形态，后续 key）
- 不包含：UE 专用任务类型与 dispatch 表扩展（editor-script 资产路由等，基座稳定后单独 key）
- 不包含：二进制资产（.uasset/.umap 等）的直接编辑能力
- 不包含：目标工程内 AGENTS.md 与 profile 的合并自动化（本期目标工程零文件，遇到时的行为由 design 定义）
- 不包含：pi 核心改动（GC-1）

## §2 业务约束

### 2.1 平台 / 环境

- Windows 主开发环境；控制工作区与目标工程可能位于不同磁盘分区（跨盘绝对路径）
- 开发机验证 fixture（用户指定 2026-09-11）：Game=F:\ProjectH（UE 工程，Perforce 工作区）、Engine=E:\CFHEngine（引擎 git fork），两独立本地卷；跨盘用例以此为基准（CI 门控见 §4 待确认 9，调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）
- 扩展代码遵守仓库 erasable TypeScript 约束（Node strip-only）
- 目标工程形态：UE（Game + Engine 双目录）或普通单目录工程

### 2.2 性能指标

- 协调层 IO 不因跨盘显著劣化：双根 fixture 下单条 trace.log 追加延迟 p95 < 1ms、max < 50ms [REVISED @ 2026-09-11，原目标 < 100ms 未实证，据实测收紧]——已实测锚定（调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）：现状为同步 fs.appendFileSync 逐行追加（output-writer.ts:78/89/211/223），跨盘 F:/E: 与同盘 H: 中位数 0.06–0.10ms、p95 ≤ 0.2ms、max ≤ 8.9ms（n=500/盘，node v24.19.0，本地卷），跨盘不劣于同盘；阈值较实测 p95 保留 >5x 余量
- 双根路径解析不得使 read-scope 判定出现每调用新增的可感知开销——现状基线已实测：单次 realpathSync（跨盘 junction 路径）mean 0.088ms / p95 0.110ms（n=1000，调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）；双根改造的回归判定方法为 read-scope 单测套件（test/suite/autopilot-read-scope.test.ts）改造前后同机耗时对照（实施时取证），设计须给出缓存或一次性解析方案避免逐调用新增 realpath

### 2.3 安全约束

- 凭证隔离不变：worker 只拿到所需 API key（launcher 现有机制）
- read_scope fail-closed 语义保留：scope 存在但为空 → 阻断全部读取类调用
- deny 规则优先于 allow；deny 命中必须拦截 read/ls/find/grep 全部读取类工具并记录 block 原因（工具集口径：worker-mode.ts:477-483 现拦截 read/ls/find/grep 四类；:105 的 READ_TOOLS 含 glob 但仅用于 checkpoint 收敛信号计数，不参与 scope 拦截——调研 note 补充核查）

### 2.4 集成依赖

- pi Extension API（不改核心）
- mw serve / launcher / conductor（autopilot）在双根下按既有语义运行
- TOOL_ALLOWLISTS ↔ autopilot/dispatch.py REGISTRY 的 T-17 L0 parity 同步测试继续成立（出处：worker-mode.ts:30-52 注释，调研 note §发现 8）
- git 操作与目标 repo 的绑定关系（design 澄清，见 §4）

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-11T15:01:58+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在未配置任何 target 配置（target 配置文件不存在、控制根环境变量未设置）的前置下，mw serve 与 agent-team-loop 扩展按现有单目录语义运行：`npm run check` 输出 0 error / 0 warning / 0 info，`./test.sh`（非 e2e）相对本 key 合入前无新增失败用例（Windows 按已知 89 例环境基线对照；口径与出处：AGENTS.md「13 + 76」2026-09-10 分类，调研 note §发现 9） |
| AC-002 | 在双工作区模式（控制工作区与目标工程位于不同磁盘分区）且至少 1 个 worker 任务已派发并运行的前置下，目标工程树（Game 根与 Engine 根）全树扫描以下模式计数为 0：`.agenticdoc`、`.mw`、`_workers.parallel`、`_index.parallel`、`trace.log`、`output.md`、`phase-*.md`；同时控制工作区内上述文件齐全 |
| AC-003 | 在双工作区模式派发 worker 的前置下，worker 进程工作目录为 Game 根（测试断言 spawn 的 cwd 值），相对路径 bash 调用作用于目标工程；task.md / trace.log / output.md / phase 文件解析到控制工作区路径（测试断言写入路径前缀为控制根） |
| AC-004 | 在 target 配置同时声明 Game 与 Engine 两个目录的前置下，profile 工具链命令可引用 Engine 根参数渲染，read_scope 可分别授权/拒绝 Game 与 Engine 下的路径且两个根下的 read/grep 调用按规则判定；配置缺失 Engine 目录时，引用 Engine 根的默认工具链命令的解析/渲染步骤以非零退出码失败且错误输出含明确原因（fail-closed），不静默回退到 Game 根 |
| AC-005 | 在同一控制工作区通过持久化配置修改或 mw 指令切换运行模式（单目录 ↔ 双工作区）的前置下，切换后路径解析按新模式生效（路径解析单测断言两种模式解析根不同），且切换过程不修改扩展源码、不重建 bundle |
| AC-006 | 在 read_scope 同时含 allow 条目与 deny globs（覆盖 `*.uasset` 与 `DerivedDataCache/**` 两种形态）的前置下，命中 deny 的 read/ls/find/grep 调用 100% 被拦截且记录 block 原因；同一路径同时命中 allow 与 deny 时判定为拦截（deny 优先）（拦截工具集与落点口径：worker-mode.ts:477-483 拦截器 + read-scope.ts 扩展，调研 note 补充核查） |
| AC-007 | 在控制工作区 target.yml 含 toolchain / ignore / contract 三个配置节且任务已派发的前置下，worker 任务上下文（渲染后的 task.md）包含三个节的特征内容（测试断言特征字符串存在）；目标工程树不新增任何框架注入文件（与 AC-002 一致）[REVISED @ 2026-09-11：profile 载体由三份文件改为 target.yml 配置节，用户决策] |
| AC-008 | 在双工作区模式且任务带 phase 的前置下，worker 完成 phase 时对控制工作区 goal.md 的 mtime 检查与 trace.log 记录行为与单目录模式一致：现有 goal check 测试（test/extensions/agent-team-loop.test.ts:379/417 [GOAL_CHECK] 断言、:573 goalMtime 单测）在双根 fixture 下通过，且 trace.log 含 goal check 行 |
| AC-009 | 在双工作区模式的前置下，mw serve 以控制工作区为服务根：PID / serve.meta / stop 请求 / serve 日志全部位于控制工作区 `.mw/` 下（测试断言路径前缀），且 serve staleness 判定在双根 fixture 下沿用现有 serve.meta 语义正确触发（现有测试基线：test/extensions/agent-team-loop.test.ts:635 serveStaleness fresh/stale/unknown/pid-file fallback） |

> AC-002 扫描模式口径：task.md 与 goal.md 为泛化文件名（目标工程树可能合法存在同名文件，纳入扫描会假阳性），故不在目标树模式清单内；其落点由 AC-003（task.md 写入路径前缀为控制根）与 AC-008（goal.md 自控制工作区读取）断言。trace.log / output.md / phase-*.md 在双工作区下本应位于控制工作区 .agenticdoc 任务目录内，仍独立列入扫描模式，作为「协调文件误锚到错误根」的独立回归探针。

## §4 风险与未决项

- 风险（已关闭 @ 2026-09-11）：pi 工具权限模型非 cwd 沙箱——read/write 工具从 cwd=H: 跨盘读写 F: 均成功（实测，调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）；worker cwd=Game 根时写控制工作区为同机制反向，成立。
- 风险（已关闭 @ 2026-09-11）：Windows 跨盘 junction 的 realpath 行为已实测——realpathSync / realpathSync.native 对 F:→E: 与 F:→H: junction 均返回目标盘绝对路径，normalizeForCompare 包含判定跨盘成立、不可经 junction 绕过 scope（调研：evidence/research/spec-cross-drive-fixture-2026-09-11.md）；symlink（需特权创建）未测，design 补用例。
- 风险：双根拆分是横切重构（paths.ts / worker-mode.ts / launcher.py / pm-orchestrator.ts 多点），须先做纯重构零行为变更步骤再叠加新能力。
- 待确认（design 需求澄清清单）：
  1. worker cwd 定为 Game 根的最终确认（本 spec 按 AC-003 假设）
  2. target 配置载体与 schema（文件名/位置；Game、Engine、VCS、模块地图字段）
  3. 模式切换的 mw 指令形态与配置优先级（env / 配置文件 / 缺省的次序）
  4. VCS 绑定：git 子命令在双工作区下的目标 repo 语义（目标 repo、控制 repo，或双轨）；实测主 fixture 的 Game 树是 Perforce 工作区（p4config.txt/.p4ignore，无 .git）、Engine 树是 git fork——须澄清 VCS 操作范围（git-only 或 VCS 无关钩子）（调研：spec-cross-drive-fixture-2026-09-11.md §发现 1）
  5. read_scope 相对条目锚定（相对 Game 根）；Engine 路径授权写法（绝对路径或别名前缀）
  6. 目标工程已存在 AGENTS.md 时的行为定义
  7. conductor/autopilot 生成 read_scope 时双根下的取值来源
  8. Windows 长路径（>260 字符）：本机 LongPathsEnabled=1，实测 277/319 字符路径 plain fs 调用成功（调研：spec-cross-drive-fixture-2026-09-11.md §发现 7）；未开启该开关的机器需 \\?\ 前缀或长度守卫，design 决定
  9. 跨盘用例的执行环境门控：AC-002/AC-004 的跨盘前置在开发机以 F:/E:（独立本地卷）执行；CI runner 无第二盘符，需 env 检测跳过或降级为同盘模拟

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- read-scope 机制（D-106）：allow scope + file/byte caps + normalizeForCompare（win32 大小写 + realpath 祖先回退）——deny globs 在其上扩展（调研：evidence/research/spec-dual-root-code-facts-2026-09-11.md）
- PI_WORKER_TASK 绝对路径传递先例（launcher.py）——控制根环境变量同构复用
- mw-runner 的 serve.meta staleness + startMw/restartMw——双根下沿用
- mw.py `_git` 的 `-C` 参数支持——目标 repo 绑定基础
- TOOL_ALLOWLISTS 框架 + T-17 L0 parity 测试——类型扩展的同步护栏
- phase-runner / output-writer / heartbeat：路径已按 agenticdocRoot 参数化，双根下直接复用

### 需规避坑点

- mw-stale-builtin-fix（_project_log.md 2026-09-09）：过期 dist 双加载——引入第二个根后 bundle 发现与全局安装路径解析需防同类问题
- mw-dispatch-reliability（_project_log.md）：credential 失败隔离与 stale entry 清理是 dispatch 可用性基线——模式切换不得破坏
- AGENTS.md 记载的 Windows 89 例已知环境失败基线（13 + 76，2026-09-10 分类）——AC-001 判定对照基线而非绝对全绿
- P-001（_pitfalls.md 2026-09-11，本 key spec 阶段实测踩中）：PS 文本管道对无 BOM UTF-8 双重编码损坏——双工作区涉及大量跨盘路径与文件操作，实现与测试代码中的文本 IO 一律显式 UTF-8（TS/Node 侧 utf-8 参数、Python 侧 encoding="utf-8"），禁 PS 文本管道往返
