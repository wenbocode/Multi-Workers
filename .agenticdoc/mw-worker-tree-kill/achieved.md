# Achieved: mw-worker-tree-kill

> 完成日期 2026-09-19（同日 review+qg 增量收口）
> 质检：✅ 通过（三轮：初版 19✅/2⚠️ → 补验复版 21/21 → 独立 review + 处置复验终版，evidence/quality-gate-report-2026-09-19.md）
> review：独立 worker 审查 0 Critical / 1 Warning / 5 Suggestion，全部采纳（W-1 CHANGELOG、S-1 hook try/catch、S-3 早期位点用例×2、S-4 mock 语义注释、S-2 记入遗留）

## 系统行为变化

mw worker 进程退出语义从"裸 process.exit(1)（Windows 上挂起中的 bash 工具子进程树随父进程死亡孤儿化）"变为"退出前终止本进程 tracked 子进程树"。修复 2026-09-19 事故链：目标项目 worker 被 idle watchdog 杀死后，其 bash 工具启动的挂死 python 探针进程孤儿化存活 50 分钟，WS 涨至 151 GB。

- **四个显式退出位点**（worker-mode.ts）：existsCheck（:414）、任务拒绝 refusal（:441）、watchdog timeoutExit（:683，idle/wall 两分支共用）、agent_settled catch（:884）——均在同步写盘（trace/output/heartbeat）之后、`process.exit(1)` 之前调用 `killTrackedDetachedChildren()`
- **exit 安全网**（:483）：`process.on("exit")` hook 兜底绕过显式清理的退出（未捕获异常、意外 exit），补写 output 兜底逻辑之前执行；kill 调用独立 try/catch 包裹（review S-1：未来 kill 路径若引入抛错不致跳过兜底写盘）
- **终止机制**：复用 pi 既有 `utils/shell.ts`——bash 工具 spawn 时跟踪 shell pid（tracked-Set），终止时 win32 `taskkill /F /T /PID`（火后即忘、独立于父进程存活）、POSIX `kill(-pgid)`（detached 组长）。零 pi 核心改动；成功路径 tracked-Set 为空，调用为 no-op，零开销
- **语义边界**：`cmd &` 后台进程超出其 shell 生命周期后不在 tracked 语义内（pi 既有设计，事故链不涉及：探针为前台挂起命令）；Windows 窄窗口——tracked 直接子进程在同步写盘与 taskkill 之间自然退出而孙进程仍存活时，`taskkill /F /T` 无法从死根遍历（POSIX `kill(-pgid)` 无此窗口，pgid 在组长死后仍有效；review S-2）——真正修复归 launcher 侧 Job Object 后续项；本修复覆盖 process 内全部退出路径，硬崩溃兜底由 exit 安全网承担
- **影响面**：worker-mode.ts（+15 行 + review 增量 S-1）；新增 2 测试文件（单测 7 用例 + live）；CHANGELOG [Unreleased] Fixed 条目（review W-1）；双 dist 重建（coding-agent/dist 23:07 + mw bundle 与全局安装 23:08，`mw build --install`）；serve 已重启（4448 → 91432），此后派发的 worker 均含修复

AC/VC 勾销与证据链见 quality-gate-report-2026-09-19.md（21 问全闭合 + 独立 review 轮：Q-D-2 全链派发 smoke 实测零孤儿升级 ✅、Q-D-3 POSIX 分支用户确认接受组合证据、review 0 Critical 全处置）与 runs/run-2026-09-19.md（单测 7/7 + 原套件 158/158 + live 真实树 2.11s 全灭 + 全链 smoke ppid 探活两轮全空 + review 处置复验 166/166 + 全量回归 new-failures=0）。

## 目标如何达成

- 根因定位：pi 的 `killTrackedDetachedChildren()` 此前仅挂在 print-mode 等信号处理器上；worker-mode 的四个 `process.exit(1)` 不触发信号 → tracked pid 永不清理 → Windows 上挂死子进程树孤儿化（git-bash `-c` 单命令 exec 优化使 tracked pid 即真实 python 探针的直系祖先）
- 修复策略：最小侵入复用（一处 import + 五处调用 + 写盘→杀→退出的顺序不变量），不新增进程管理机制；以 grep 不变量（每个 `process.exit(` 前一行均为清理调用）做机械防回归
- 验证分层：mock 层单测（kill 先于 exit 的 invocationCallOrder 断言 ×6 位点含早期两处 + 成功路径零调用）→ live 真实进程树（2 tracked 父 + 1 孙进程，watchdog 退出后探活全灭）→ 全链 mw 派发 smoke（真实 worker 挂起 Start-Sleep 109s → wall kill → ppid=44776 探活零残留，output.md kill 前落盘）→ 独立 review worker（静态审查复核全部维度）+ 处置复验

## 经验教训

- ESM 模块内闭包：vi.mock 同模块导出函数的内部调用不可观测（mock `killProcessTree` 看不到 `killTrackedDetachedChildren` 的调用）→ mock 必须打在模块导出边界（H-001，D-004 执行期修订），per-pid 证据下沉到 live 层
- pi bash 工具的 shell 在本机解析为 PowerShell：`sleep N` 是 Start-Sleep 别名、进程内挂起、无外部 sleep.exe——smoke 的探活判据须按实际 shell 形态选（ppid 探活比按进程名扫描更鲁棒）
- 全链 smoke 里 checkpoint 的机器 risk 判据（零写纯读=high）对故意挂死的 smoke 任务必然误报——判定权在 PM，此类通知预期内直接继续等待
- 静态 review 与代跑测试互补：review worker 声明只读不代跑（正确），其"需 tsc 确认新类型写法"类行动项由 PM 复跑闭合——review 提出假设、执行侧给证据

## 遗留

- POSIX `kill(-pgid)` 分支为组合证据（pi 既有生产实现、本 key 未新增平台分支）；live 用例已随仓库就绪，Linux 环境跑一次即闭环（非欠债，质检已用户确认）
- Windows 窄窗口（tracked 子进程自然死亡→孙进程孤儿，review S-2）：真正修复为 launcher 侧 Job Object（后续候选 key）
- 未提交：工作区同时含 mw-target-partition 未提交变更与另一会话 packages/ai kimi-coding 在途工作（root `npm run build` 暂不可用，包内 build 与 `mw build` 可用），勿混提；本 key 文件清单见 runs/run-2026-09-19.md
