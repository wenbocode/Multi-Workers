# Mini-Spec: mw-pm-save-snapshot

- Date: 2026-09-14
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

用户需要一条指令把当前窗口的上下文状态完整保存到 pm-state，便于重启 pi 窗口（加载新框架后）接续工作。重启丢失的不是框架状态（watch/claim/phase/tasks 均文件驱动、restoreWatch 自动恢复），而是**会话的对话脉络**（当前在做什么、关键决策、下一步）。

## Change

新增 `/pm-save [note]` 命令（ui-bridge.ts `registerPmSaveCommand` + `writeSessionSnapshot`）：

- **机械快照**（handler 直写，StateManager 同款文件锁 + tmp/rename 原子写）：watch key、窗口 claim、`_index.parallel` 行（status/phase/desc）、worker 统计（固定顺序 pending/running/done/failed/needs-clarification）、用户自由备注，插入 `{watchKey}/pm-state.md` 的 `## Notes` 区顶部（`### Session Snapshot — <ts> (<claim>)` 小节）。
- **机器接口行不动**：`- Phase:` / `- Claim-Id:` 保持字节级原样（pm-state-guard 原则的框架侧镜像）；已有 Notes 内容全部保留（快照插在标题后）。
- **语义部分由 agent 补全**：handler 完成后 `sendUserMessage` 明确要求 agent 把当前工作脉络/关键决策/进行中/下一步补写进快照小节（用户显式调用命令 = 用户意愿，与被移除的自动 evidence nudge 性质不同）。
- **恢复侧**：`restoreWatch` 尾部检测 `{key}/pm-state.md` 存在 → `ctx.ui.notify` info 提示（含 mtime），指向 Notes 区，让用户决定是否让 agent 读取——遵循 notice 原则（框架提示、不注入）。
- 前置：需 watch key（无 → warning 提示先 `/pm-key switch` / `/mw-watch`）；`_scratch` 同样支持。

## Files

- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（writeSessionSnapshot + registerPmSaveCommand + acquireLock import）
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（restoreWatch 恢复提示 + pmActivate 注册）
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（2 个新用例）
- `packages/coding-agent/CHANGELOG.md`

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 无 watch key → warning，不写文件 | 单测 |
| AC-002 | 有 watch → 骨架创建 + 快照小节（key/claim/index 行/worker 统计/备注）插入 `## Notes` 顶部 | 单测 |
| AC-003 | 已有 pm-state.md：接口行字节不变、prior notes 保留、快照位于 Notes 标题与旧内容之间 | 单测 |
| AC-004 | handler 明确请求 agent 补全上下文状态（sendUserMessage，用户显式触发） | 单测 |
| AC-005 | restoreWatch 对存在 pm-state.md 的 key 发 notice（不注入），指向 Notes 区 | 单测 |

## Result

- 测试 120/120 passed；`npm run check` 全绿；`mw.py build --install` 已重建重装。
- 用法：重启前 `/pm-save 简短备注` → agent 补全上下文 → 重启窗口（resume 或新会话均可，restoreWatch/`/pm-key switch` 会提示）→ 让 agent 读取该 key 的 pm-state.md Notes 区接续。
- 状态：完成。
