# Mini-Spec: mw-evidence-nudge-notify

- Date: 2026-09-14
- Mode: pm mini fast path (direct execution, no plan/tasks)
- Deps: agent-team-loop

## Problem

用户报告：框架默认启动了一个"自动审批"——`[agent-team-loop] <key>：spec 阶段证据已就位…请立即执行证据复查` 消息出现后，窗口 agent 立即开始自动复查并改写 spec.md，未经用户同意。

## Root Cause

`nudgeEvidenceReview`（pm-orchestrator.ts）在 phase doc 与 research note 共存时（写 spec/design.md 且 evidence ≥1，或写 evidence/research/ spec-*/design-*.md 且 doc 已存在），用 `pi.sendUserMessage(..., { deliverAs: "followUp" })` 以用户身份注入"请立即执行证据复查"指令。模型把它当作用户的直接命令执行：无确认环节、用户不可否决、打断当前任务；且触发不看 watch key——任何窗口写中任一路径都被劫持。

## Change

方案 A（用户选定）：降级为 UI 提示。`nudgeEvidenceReview` → `evidenceReviewNotice`：

- 签名 `pi: ExtensionAPI` → `ctx: ExtensionContext`（类型层面不再存在注入路径）
- `sendUserMessage`（进模型上下文、followUp 排队、命令式）→ `ctx.ui.notify(..., "info")`（UI 气泡，不进模型上下文，headless 安全——autopilot cmdMonitor 同模式）
- 措辞从命令式（"请立即执行…修正直接写入…"）改为建议式（"建议对照…复查…何时执行复查由你决定"），保留四项复查要点关键词（断言-证据对照 / 数字口径 / 内部一致性 / 可证伪性）；删除 SPEC_REVIEW_CHECKLIST / DESIGN_REVIEW_CHECKLIST 全文常量
- 触发检测与去重语义不变：每 (key, phase) 每会话一次，doc ≥500 字节且 evidence ≥1
- 框架角色边界：门禁/提示（advance gate 拦缺失证据 + notice 提示复查时机），不主动下令执行工作

## Files

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`（evidenceReviewNotice + 调用点 + 常量删除）
- `packages/coding-agent/test/extensions/agent-team-loop.test.ts`（用例重写为 notice 断言；followUp 注入用例随前提消失删除）
- `packages/coding-agent/CHANGELOG.md`

## Acceptance Criteria

| AC | 内容 | 验证 |
| --- | --- | --- |
| AC-001 | 证据齐时发 UI notice（info 级，含 key/doc/复查要点），不进模型上下文 | 单测 |
| AC-002 | 每 (key, phase) 每会话一次；spec/design 独立去重 | 单测 |
| AC-003 | doc 或 evidence 缺失时不提示（复查需要两侧对照） | 单测 |
| AC-004 | 无 sendUserMessage 注入路径（签名只有 UI ctx） | 单测注释 + 类型 |

## Result

- 测试 118/118 passed；`npm run check` 全绿；`mw.py build --install` 已重建重装。
- 状态：完成。
