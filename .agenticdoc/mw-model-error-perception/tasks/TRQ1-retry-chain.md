# TRQ-1: 模型错误重试链路边界（research）

type: research

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（mw 后台服务 + agent-team-loop 扩展；worker 进程级隔离；超时看门狗收敛）。
- 问题：worker 派发后模型持续 500/连接失败时不可感知。需要先量化「一次 LLM 调用在模型持续失败时的完整重试链路与最坏耗时」，作为 fail-fast 阈值设计的依据。
- 已知事实（PM 预研，须核验）：
  - `packages/ai/src/utils/provider-retry.ts:105-122`（provider 级重试，默认 maxRetries 0，delay 上限 60s）
  - `packages/ai/src/timi-responses.ts:34`（timi 路由 `options?.maxRetries ?? 8`）
  - `packages/coding-agent/src/core/agent-session.ts:1081-1096, 2680-2730`（agent 级 auto-retry）
  - `packages/coding-agent/src/core/settings-manager.ts:806-843`（retry 默认 enabled=true, maxRetries=3, baseDelayMs=2000；provider.timeoutMs 默认未设）

## 要求

1. 核验上述事实；补齐完整链路：provider 级（SDK/raw fetch）→ agent-session auto-retry → worker 侧，对「持续 HTTP 500」「连接拒绝」「连接挂起（无响应字节）」「流中断（stream closed before response.completed）」四类故障分别给出：重试次数、退避序列、最坏墙钟时间、期间发出的会话事件序列（auto_retry_start/end 是否只在 session 事件层、扩展能否订阅）。
2. 判定默认配置下是否存在「无超时、永久挂起」路径（retry.provider.timeoutMs 未设置时 header/body timeout 行为；undici/SDK 默认），该路径能否逃逸 worker 的 10 分钟 idle 看门狗（worker-mode.ts:3403 idleTimer 以 message_update 等 delta 事件为活动源）。
3. 给出 errorMessage 的典型文本形态（500 / connection refused / stream closed），供 trace 与 Exit Reason 识别用。
4. worker 实际运行时的 retry 设置来源：launcher.py spawn env 是否注入/覆盖 settings.retry；`~/.pi/agent/settings.json` 默认是否被 mw 改写。

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-model-error-perception/evidence/research/spec-retry-chain-2026-10-15.md`（只写此一个文件）
- 结构：调研方法与出处（文件:行号）→ 四类故障逐一事实 → 无超时路径判定 → 结论→决策映射（fail-fast 阈值应设在几次 agent 级失败之后）
