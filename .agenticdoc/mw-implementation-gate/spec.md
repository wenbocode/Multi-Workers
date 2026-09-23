# Spec: mw-implementation-gate（实施准入门禁机械化）

> Key: mw-implementation-gate
> 创建时间: 2026-09-21
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：goal 的核心交付是 PM Agent 管理多 Worker 的协作框架；本 key 把协作框架自身的纪律（实施准入门禁）从 advisory 文字升级为机械拦截——保护的是 PM 工作流的可追溯性与 goal 对齐这条主线。
- 继承约束（GC 编号）：
  - GC-1: 不修改 pi 核心——守卫必须经 pi 扩展 API（Extension API）实现，不 fork。
  - GC-2: 文件驱动协调——active key 判定读 `.agenticdoc/_index.parallel`（文件即事实），不引入中心化服务。
- 冲突：无（不碰 timi-proxy / 派发路径）。
- 预期收益：野生实施从"靠 agent 自觉"变为"工具层拦截"——无 key 的窗口写代码路径被拒绝并给出建 key 指引；done 时对照判定（AC-001~006 全勾 + 真机验证）。

## §1 功能概述

### 1.1 目标
消除本轮已发生两次的流程逃逸（update-env、ue-toolchain 均为中途插入需求直做）：write/edit 命中代码路径且窗口无 active key claim 时拒绝执行，附建 key / mini fast path 指引；同时扩大框架 skill 的触发词覆盖，让"即将实施"场景能命中 skill 加载。

### 1.2 技术栈 / 语言
TypeScript（pi 扩展，packages/coding-agent 扩展体系）+ Markdown（框架 SKILL.md）。

### 1.3 核心用户场景
1. agent 在无 key 的 pi 窗口写 `packages/multi-workers/mw.py` → 守卫拒绝，提示建 key。
2. agent 在已 claim `mw-implementation-gate` 的窗口写同一路径 → 放行。
3. 真实 trivial 修复（一行）→ 显式 mini fast path 声明后放行，留审计痕迹。
4. 用户在其他装了 AgenticTask 的项目说"实现 X" → skill 触发词命中，读 SKILL.md 走准入门禁。

### 1.4 范围说明（不做什么）
- 不做 AGENTS.md 仓级规则（已完成，独立于本 key——见 key-decision）。
- 不做会话中途新需求的 turn hook 提醒（若扩展 API 有天然挂点则顺手做，否则记遗留）。
- 不做 _index.parallel 写锁/并发改造（读侧判定即可）。

## §2 业务约束

### 2.1 平台 / 环境
pi 0.83.0 扩展体系（built-in extension 机制）；多窗口并行（多 host:pid 同时持有不同 key claim）。

### 2.2 性能指标
守卫判定（读一次 _index.parallel + 路径匹配）不显著拖慢 write/edit（<10ms 量级，文件读缓存可接受）。

### 2.3 安全约束
守卫不得成为绕过点：mini fast path 必须留审计（写入记录），不能静默放行。

### 2.4 集成依赖
pi Extension API（tool-call 拦截能力待调研 W1）；`_index.parallel` 格式（update_index.py 维护）；P-002 protected-config-guard 先例（实现方式待调研 W2）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-21T23:00:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在无 active key claim 的测试窗口里，经工具层调用 write/edit 目标为代码路径（如 `packages/multi-workers/mw.py`）时，操作被拒绝（文件未被写入/修改）且错误消息含建 key 指引（含 "mini" 一词提示 fast path） |
| AC-002 | 在窗口持有 active key claim（`_index.parallel` 中该窗口 claim 存在且 status=active）时，对同一路径的 write/edit 成功 |
| AC-003 | 在显式声明 mini fast path（机制以 design 定案为准，如一次性 env/标志）后，无 key 写代码路径成功且留下可查的审计记录（≥1 行日志/记录文件） |
| AC-004 | 对守卫白名单外路径（`.agenticdoc/**`、`docs/**`、`README.md`、`tmp/**`）的 write/edit 不受守卫影响，行为与无守卫时一致 |
| AC-005 | 框架仓 `.agents/skills/agentic-task/SKILL.md` 的 description 含 "non-trivial implementation" 触发词；改动 commit+push 后 `diff-installed.py` 对本仓报 clean（clone 与 HEAD 一致） |
| AC-006 | 守卫逻辑有自动化测试（`packages/coding-agent/test/suite/` 下，harness + faux provider，无真实 provider 调用）覆盖 AC-001/002/004 路径 |

## §4 风险与未决项

- 风险：pi Extension API 可能没有 tool-call 前拦截点（只能事后审计或 UI 提示）——W1 调研结论直接决定 design 形态（硬拦截 / 事后警告 + 审计）。
- 风险：白名单边界（哪些路径算"代码路径"）过宽会误伤文档轮次，过窄漏拦——design 需给出清单并可在扩展配置中调整。
- 待确认：mini fast path 的声明机制（env var / 会话内一次性命令 / 配置文件）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产
- P-002 protected-config-guard 先例（2026-09-15，会话乱改跨窗口共享文件的前置警戒——实现方式 W2 调研后复用其模式）。
- agent-team-loop 扩展既有代码（事件挂点、UI 消息通道——ui-bridge.ts / pm-orchestrator.ts）。
- `_index.parallel` 读写语义（update_index.py claim/release，claim_id = host:pid）。
- ue-toolchain key 的教训记录（野生实施偏差 + 补登记模式）。

### 需规避坑点
- P-001（PS mojibake）：调研输出走文件。
- P-002（跨窗口共享文件）：守卫实现不得修改其他窗口正在写的 `_index.parallel` 行（只读判定）。
- P-003（open(p,"w") 截断）：审计记录追加写，不读-改-写。
- ue-toolchain 教训：单测绕过 argparse 层的盲区——守卫测试必须在真实工具调用层验证，不能只测纯函数。
