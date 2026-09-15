# Task 007: task-dispatcher.ts profile 三节渲染

- Stage: S3
- 代码状态: 代码完成
- 验证状态: 验证通过（2026-09-11，7/7 + 关联 191/191 + check exit=0；任务级 deny_globs 时 profile ignore 节语义修正，证据 evidence/runs/007-profile-rendering.md）
- ac_refs: [AC-007]
- vc_refs: [VC-013]
- pattern_refs: []
- deps: [001]
- 预估: ~1h

## 交付物

- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`: dispatch 渲染 task.md prompt 时注入 toolchain/ignore/contract 三节要点 + 控制工作区绝对路径引用（profile 全文读取授权由 Task 006 的 scope 附加实现）
- 长 contract 支持 `docs:` 字段（存在则渲染引用行，不内联全文）
- 测试扩展（agent-team-loop 测试文件，特征标记断言）

## AC 摘录（spec.md §3，AC-007 已修订为 target.yml 三配置节）

- AC-007: dispatch 时 toolchain/ignore/contract 三节注入 task.md，worker 无需感知 target.yml 的存在

## 实现要点（design.md D-005）

- 要点渲染而非全文堆砌（task.md 自包含与上下文防火墙的平衡）；节缺失 → 跳过该节不阻断派发
- TS 侧用 Task 001 的 resolveWorkspaceConfig 读同一 target.yml（与 Py 侧同源）
- 渲染含控制工作区绝对路径（worker 需要时读 profile 全文）

## 验证方式（VC 断言）

- VC-013: 测试注入特征标记（TOOLCHAIN_MARK/IGNORE_MARK/CONTRACT_MARK 三节各一）→ 渲染产物含三标记 → `[VERIFY] VC-013: toolchain-mark=true ignore-mark=true contract-mark=true`
- 节缺失用例: 只配 toolchain 节 → 渲染含 toolchain 要点、无报错
- 证据落盘: `evidence/runs/007-profile-rendering.md`

## 依赖与阻塞

- 依赖 001（TS 配置解析）。与 006 无依赖关系，可并行。
