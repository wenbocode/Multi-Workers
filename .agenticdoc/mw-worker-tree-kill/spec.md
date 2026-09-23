# Spec: mw-worker-tree-kill

> Key: mw-worker-tree-kill
> 创建时间: 2026-09-19T17:11:39+08:00
> 状态: draft
> deps: —（独立缺陷修复；与 mw-provider-routing 无交付物交集，用户 2026-09-19 会话拍板新建）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「Agent Team 协作框架」中「Worker 进程级隔离」与「Worker 超时看门狗」两条——Worker 的死亡（含 watchdog 终止）必须干净，不得向宿主机泄漏存活子进程（2026-09-19 目标项目事故：孤儿 python 吃掉 151 GB）。
- 继承约束（GC 编号 = goal.md Key Constraints 顺序，供 design/plan 引用）：
  - GC-3: Worker 进程级隔离——Worker 是独立 pi 进程，其生死不得影响其他 Worker 与宿主机资源
  - GC-6: Worker 超时看门狗（2026-09-09 修订，mw-worker-timeout-convergence）——idle/wall 终止语义保持不变，本 key 只补终止时的子进程树清理
  - GC-2: 不修改 pi 核心——只读复用 `utils/shell.ts` 具名导出，与扩展既有 `core/extensions/types.ts` import 同类，不改 pi 任何行为
- 冲突：无（GC-6 的终止时机/证据格式不变，仅新增退出前清理动作）。
- 预期收益：worker 因 watchdog/异常退出后，其 bash 工具遗留的挂起子进程树（含孙进程）随之终止，不再孤儿化吃内存。判定方式：单测 spy 断言树杀先于 `process.exit(1)` 且覆盖全部 tracked pid；live smoke 下真实进程树在 worker 退出后消亡。

## §1 功能概述

### 1.1 目标

修复 worker 退出路径的子进程泄漏：`worker-mode.ts` 所有以 `process.exit(1)` 终止的路径（idle/wall watchdog 的 `timeoutExit`、`agent_settled` 异常 catch）在退出前显式调用 `killTrackedDetachedChildren()`；既有 `process 'exit'` 安全网同步补上同一清理，覆盖其余退出形态（启动 refusal、硬崩溃）作 best-effort 兜底。复用 pi 既有设施，不引入新杀进程逻辑。

### 1.2 技术栈 / 语言

TypeScript（pi built-in extension：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`）；vitest 单测。

### 1.3 核心用户场景

1. 场景 A（事故链）：worker 经 bash 工具启动一个挂死命令（如无限循环脚本）→ 无活动达 idle 阈值 → watchdog 杀 worker → 该命令的整棵进程树（含 shim/孙进程）随之死亡，不残留。
2. 场景 B：wall budget 到期终止（与 A 共用 `timeoutExit`）→ 同上。
3. 场景 C：agent_settled 处理中抛异常 → catch 路径退出 → 同上。
4. 场景 D（回归底线）：worker 正常完成（无挂起子进程）→ 行为与现状完全一致，不做任何额外杀进程动作。

### 1.4 范围说明（不做什么）

- 不包含：worker **硬崩溃**（扩展代码没机会运行）时靠 OS 机制回收子树的 launcher Job Object（Windows）/进程组收尸方案——独立交付物，后续 key。
- 不包含：bash 工具自身超时/abort 的树杀（pi 已有，bash.ts:112/120）；launcher / mw serve 侧任何杀进程逻辑（现状它们不杀 worker）。
- 不修改 watchdog 的判定语义、trace/output 格式、退出码。

## §2 业务约束

### 2.1 平台 / 环境

Windows（taskkill /F /T /PID）与 POSIX（kill(-pgid)，bash 工具 detached 组长语义）双平台正确；跨平台行为由被复用的 `killProcessTree` 承担。

### 2.2 性能指标

清理调用为 fire-and-forget（taskkill detached spawn），不得阻塞退出路径的同步写盘（trace.log / output.md 先落盘，后杀树，再 exit）。

### 2.3 安全约束

无新凭证/权限面。强杀目标是本 worker 自己 spawn 的 tracked 子进程树，不触碰他人进程。

### 2.4 集成依赖

`packages/coding-agent/src/utils/shell.ts` 的 `killTrackedDetachedChildren()`（唯一 tracked pid 事实源，必须同模块实例 import）；部署依赖：重建 dist bundle + `/mw restart` 后方对 worker 生效。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-19T17:11:39+08:00，编号永不回收
> （锁定依据：2026-09-19 会话用户基于前轮代码级归因批准方案并指示开 key 实施）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 worker 存在挂起的 bash 工具子进程（tracked pid 集合非空）且 idle watchdog 触发（PI_WORKER_IDLE_MS 缩短的测试环境下无活动达阈值）时，worker 在 `process.exit(1)` 之前调用 tracked 集合清理（遍历全部 tracked pid 的树终止），且 trace.log/output.md 均已先写入 —— 量化：单测断言清理调用恰一次且先于 exit 调用；tracked pid 全覆盖与真实树终止由 live 用例（AC-006 同机制）以真实进程探活复核 [REVISED @ 2026-09-19：ESM 闭包使 killProcessTree 层 mock 不可观测，量化口径改为清理调用层级，per-pid 证据移至 live] |
| AC-002 | 同前置条件但由 wall budget 触发（timeout: 头缩短）时，杀树与退出顺序行为与 AC-001 完全一致 —— 量化：同一 spy 断言复用通过 [REVISED @ 2026-09-19：同 AC-001 口径] |
| AC-003 | 在 `agent_settled` 处理抛异常（catch 路径 `process.exit(1)`）且 tracked pid 集合非空时，同样先调用 tracked 集合清理再退出 —— 量化：单测注错后 spy 断言清理调用先于 exit [REVISED @ 2026-09-19：同 AC-001 口径] |
| AC-004 | 在 worker 已激活（'exit' 安全网已注册）后未经显式退出路径而进程退出（硬崩溃兜底：直接调用注册的 exit listener 模拟）时，安全网 hook 先对每个 tracked pid 执行树终止再做 output 补写 —— 量化：单测直接调用注册的 exit listener，断言树终止调用次数 = tracked pid 数 [REVISED @ 2026-09-19：design 阶段发现启动 refusal 在 hook 注册前退出（worker-mode.ts:439 早于 :475），refusal 改由显式调用覆盖，本 AC 收敛为硬崩溃兜底语义] |
| AC-005 | 在 worker 正常完成（agent_settled 无异常、无挂起子进程）时，不产生任何树终止调用、退出码 0、trace [END] exit=0 —— 量化：单测 spy 断言零调用 + 既有成功路径用例不回归 |
| AC-006 | 在真实 Windows 宿主上经 mw 派发的 worker 被 watchdog 终止且其 bash 命令挂起时，该命令进程树（含孙进程）在 worker 退出后 ≤ 60s 内全部消失 —— 量化：live smoke 中按 PID 复查存活数 = 0 |

## §4 风险与未决项

- 风险：taskkill fire-and-forget 与紧随的 `process.exit(1)` 存在理论竞态——taskkill 已 detached spawn（CreateProcess 同步完成），父进程死亡不影响其执行，风险低；live smoke（AC-006）验证。
- 风险：POSIX `kill(-pid)` 在组长已死时回退单 pid（pi 既有语义，非本 key 引入）。
- 风险：'exit' hook 内 spawn 属 best-effort（Node 退出阶段只保证同步代码），主路径已由 AC-001/002/003 的显式调用覆盖。
- 部署注意：修复对 worker 生效需重建 dist + `/mw restart`（当前 serve PID 4448 本就是 stale code）。
- 待确认：无。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

（`_arch_snapshot.md` 尚未建立；对着现有代码资产与 `_project_log.md` 点名）
- `packages/coding-agent/src/utils/shell.ts` 的 `killProcessTree` / `trackDetachedChildPid` / `killTrackedDetachedChildren` —— 唯一 tracked pid 事实源，本 key 直接复用，禁止在扩展内重造杀树逻辑。
- `modes/print-mode.ts:51-60` 信号处理器先例 —— 证明清理入口挂靠方式，本 key 把同一入口补到扩展退出路径。
- `test/extensions/agent-team-loop.test.ts` 的 watchdog 集成测试 harness（fakeWorkerPi + fake timers + process.exit spy + fs.writeSync 静音，见 3868 行 describe 块）—— AC-001/002/003/005 的测试直接在其上扩展。

### 需规避坑点

- P-001（PowerShell 文本管道损坏无 BOM UTF-8）：本 key 全部 `.agenticdoc/` 与源码改写只用 write/edit 工具，不经 PS 管道。
- mw-stale-builtin-fix 教训（stale dist 双重加载/不生效）：TS 改动完成后必须重建 dist bundle 才算交付，且 live smoke 用新 bundle 跑。
