# T-14: 终态自动回读（AC-014 / VC-020）

- Stage: 5（评审后用户决策：worker 成果自动交付）
- 代码状态: 代码完成
- 验证状态: 验证通过
- ac_refs: AC-014
- vc_refs: VC-020
- Error Fingerprint: 无

## 背景

L2 评审轮暴露的交付缺陷：终态消息只回 `## Summary` 节选，PM 必须手动读 output.md 才能处理完整成果（用户 2026-09-08 反馈「结果没有回读回来，需要我主动触发」）。

## 变更

- `readOutputBody(taskDir)`（ui-bridge）：读 output.md 全文，≤20,000 字符原样返回；超出截断并附 `full report: <path>` 指路
- 终态消息格式：`[task] done (6m, ph 3/3):\n\n<全文>`——心跳统计保留在消息头；无 output.md 走既有 spawn-failure/无输出提示（不变）
- spec AC-014（APPENDED，用户决策）、design VC-020 + D-009、evidence-requirement VC-020 同步

## 验证

- VC-020 vitest：全文注入（含 Summary 之外的节）、20k 截断 + 指路、消息长度约束 → 66/66 内
- 既有终态摘要测试（spawn-failure/无输出路径）不改自过——fallback 语义未动

## 执行记录

| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-08 16:4x | 实现 + 测试 + 三文档同步 | PASS: VC-020 |

## 关联

- 底部 widget 每 tick 重绘（AC-012/VC-018）已是本会话未提交代码，bundle 重装 + 窗口重启后生效——旧 bundle 缺该能力是「状态条不刷新」的根因（非代码缺陷，见 evidence/runs/l2-rerun-2026-09-08.md 附注与 quality-gate 报告）
