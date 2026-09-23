# Spec: mw-parallel-protocol（PM 窗口常驻「并行优先协议」注入）

> Key: mw-parallel-protocol
> 创建时间: 2026-09-22
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（已确立，非 draft）

- 对齐：goal 的核心命题是「一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，解决单 Agent 无法并行的问题」。并行的**能力**已经具备（launcher 并发 spawn、`agent_settled` 一次扫描批量入队、逐条终态回读），缺的是 PM **每次拆解都从并行度出发**这一行为约束——本 key 补的就是这条默认行为。
- 继承约束（GC 编号）：
  - GC-1: 不修改 pi 核心——只改 agent-team-loop 扩展内的 PM 编排（`pm/pm-orchestrator.ts`），走扩展 API（`before_agent_start`），不 fork pi。
  - GC-2: 文件驱动协调不变——不引入中心化调度，不新增服务端状态。
  - GC-3: 框架只提示不劫持 turn——注入的是系统提示文本（每 run 一次、非持久消息），不主动发起生成、不代替用户决策。
- 冲突：无（不触及 dispatch 路由、target/partition 语义、RAG 配置、门禁阈值）。
- 预期收益：PM 窗口在 spec/design 调研、证据收集、plan/tasks 拆解、编码派发四类动作上默认先做并行性分析并按并行单元派发，而不是顺序单发；调研类角色只读，冲突面仅「同一输出文件」，因此批量派发零风险。判定：新窗口首轮起系统提示含协议文本，且协议文本对 research/coding 两类冲突面给出不同规则（不再是"不可并行的串行"这一句）。

## §1 功能概述

### 1.1 目标

在 PM 模式（`pmActivate`）注册一个 `before_agent_start` 处理器，把一段**静态的**并行优先协议追加进当轮系统提示，使 PM 在每次 agent run 都带着并行拆解规则工作。

### 1.2 技术栈 / 语言

TypeScript（agent-team-loop 扩展，erasable syntax only）。

### 1.3 核心用户场景

1. 用户开 PM 窗口提问 → 协议已在本轮系统提示中，PM 拆 plan/tasks 时会先给并行性分析。
2. spec/design 阶段调研 → PM 拆出 RQ-1..N，一次性写 N 个 `type: research` 的 task.md，各自写唯一 `evidence/research/<phase>-<rq-slug>-<date>.md`。
3. worker 终态回读唤醒的续跑轮 → 协议同样在场，PM 补派下一批而不是串行等待。
4. worker 窗口（`PI_WORKER_TASK` 已设）→ 走 `workerModeActivate`，**不受影响**（结构性保证：`index.ts` 的 if/else 分支）。

### 1.4 范围说明（不做什么）

- 不注入持久 `message`（会每 run 往 session 累积 token）。
- 不做动态内容（空闲槽位数、冲突矩阵）——纯静态文本，保证系统提示前缀确定性、不破坏 prompt cache。
- 不加开关/配置（无用户需求；后续要开关再单开 key）。
- 不改 `core/pm-mind.md`、`core/workflows/*.md`（跨仓库 AgenticTask clone，另计）。
- 不改 gate 阈值（evidence note 仍为 `>= 1`，不强制多份）。

## §2 业务约束

### 2.1 平台 / 环境

Windows 为主的开发机；PM 窗口由 `mw serve` + launcher 体系承载，扩展以打包产物（`packages/multi-workers/dist/extensions/agent-team-loop.js`）装到 `~/.pi/agent/extensions/`。

### 2.2 性能指标

每 run 追加一次字符串拼接（< 1 KB），无 I/O、无定时器、无子进程。

### 2.3 安全约束

- 注入文本不得改变门禁语义（不能暗示可绕过 phase gate / 证据要求）。
- 注入文本不得覆盖既有系统提示，只能追加。

### 2.4 兼容性约束

- 幂等：处理器重复进入同一轮（双包加载等）不得重复追加——以标记串判重。
- 幂等失败时行为必须是「少注入」，不能是「重复注入」。

## §3 验收标准（AC）

- AC-001: PM 模式激活后存在 `before_agent_start` 处理器，其返回的 `systemPrompt` 以原 systemPrompt 为前缀并追加协议文本。
- AC-002: 协议文本包含四类动作的并行规则：拆解前的并行性分析、spec/design 调研批量派发（含「一个 RQ 一个唯一 note 文件」）、编码按文件边界并行（同文件互斥）、相位文档由 PM 串行写。
- AC-003: 幂等——把上一轮返回的 `systemPrompt` 再喂进处理器，返回 `undefined`（不追加）。
- AC-004: 空/超长/缺失 systemPrompt 不抛异常（`undefined` 输入按空串处理）。
- AC-005: worker 模式不受影响——`PI_WORKER_TASK` 存在时不注册该处理器（沿用 `index.ts` 既有分支，测试覆盖 `workerModeActivate` 不注册）。
- AC-006: `npm run check` 零 error/warning/info；新增测试通过。

## §4 证据（evidence/research）

本项目无外部依赖需要调研，零调研声明见 `evidence/research/spec-parallel-protocol-2026-09-22.md`。
