# Mini-Spec: mw-activation-rearm

- Date: 2026-09-14
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

用户报告：`/pm-key switch <key>` 后窗口底部不出现 key 概要（watch widget）。

## Root Cause（实证）

`agent-team-loop/index.ts` 的防双载守卫把 `__agentTeamLoopActivated` 记在 `globalThis` 上且永不清除。pi 的会话替换（`/new`、`/resume`、`/fork`、`/reload`）会重建 runtime（`createRuntime` → 新 resource loader → 对每个扩展重新调用 `activate(pi)`），守卫使二次激活 no-op——新 session 的扩展对象为空：无命令、无工具、无事件处理器、无 poll 循环、无 widget。之后 `/pm-key switch` 成为未知命令，整行文本作为 prompt 发给 LLM，永远没有 widget。

RPC 复现（`pi --mode rpc`）：`new_session` 前命令集 30 个（含 pm-key/mw/worker/mw-watch/autopilot），替换后 25 个，mw 系全消失。

## Change

守卫语义收窄为"同一次加载内防双载"：`activate()` 在守卫检查**之前**注册 `session_shutdown` 处理器删除 flag（幂等）。会话替换/reload 的 teardown 先触发 session_shutdown → flag 清除 → 重新激活完整执行；同次加载内的双副本（全局 + 残留本地副本）之间没有 shutdown，防双载保持原效。旧 poll 循环本就由 session_shutdown 清除，重激活启动新循环，`pmActivate` 假设的 "a fresh runtime re-runs pmActivate" 恢复成立。

## Files

- `packages/coding-agent/src/extensions/agent-team-loop/index.ts`（守卫 re-arm）
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（新增 describe "activation guard re-arm"）
- `packages/coding-agent/CHANGELOG.md`（[Unreleased] Fixed）

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 同次加载双副本仍被挡（防 tool-conflict 崩溃） | 单测 fourth copy |
| AC-002 | session_shutdown 后 flag 清除、重激活完整注册（命令/工具/处理器） | 单测 third copy |
| AC-003 | 重激活后同次双载仍被挡 | 单测 |
| AC-004 | 真实运行时会话替换后命令存活 | RPC：new_session 前后 30=30，pm-key/mw 在 |
| AC-005 | 真实运行时替换后 /pm-key switch 渲染 widget | RPC：setWidget(agent-team-loop-watch) FIRED + notify |

## Result

- 测试：`agent-team-loop.test.ts` 119/119 passed（含新增守卫用例）。
- `npm run check` 全绿。
- `mw.py build --install` 已重建 bundle + pi dist 并全局重装；RPC 端到端验证通过（AC-004/005）。
- 状态：完成（直接执行；诊断期临时脚本已清理）。
