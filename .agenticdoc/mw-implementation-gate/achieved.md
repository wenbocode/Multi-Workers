# Achieved: mw-implementation-gate

> Key: mw-implementation-gate
> 结案时间: 2026-09-22

## 系统行为变化

- **新增实施准入门禁（机械 enforcement）**：agent-team-loop 扩展 `shared/implementation-gate.ts`（738 行，纯判定 + register 分离）+ index.ts 三模式注册（PM/Worker/交互）。write/edit（及 bash 写目标收窄判定）命中仓库代码路径（`packages/**` 代码扩展名，排除 node_modules/dist/.tmp）且窗口无 active key claim 时拒绝执行，reason 给出两条合规路径（建 key / mini fast path）。
- **三条件放行**：本窗口 host:pid 的 active claim（写 spec.md 自动 claim）∨ `PI_WORKER_TASK`（派发 worker 预授权）∨ 新鲜（≤24h）`.agenticdoc/<key>/mini-spec.md`（trivial 快路径）。`_index.parallel` 缺失/损坏 fail-closed。
- **审计**：每次 block 与 mini 放行追加一行 `.agenticdoc/_impl_gate.log`（best-effort，不影响判定）——修 P-002 先例的"仅 worker 模式落盘"缺口。
- **测试**：`test/suite/agent-team-loop-implementation-gate.test.ts` 9 用例走真实工具调用派发层（唯一 stub 为 bash 后端记录器）；接线敏感性实证（去注册行 9/9 红）。
- **修真缺陷**：bash 词法器 Windows 反斜杠路径漏拦（POSIX 转义误用）→ 真实 POSIX 转义集修复（`BACKSLASH_ESCAPES_UNQUOTED`/`BACKSLASH_ESCAPES_DOUBLE_QUOTED`）。
- **框架仓**：SKILL.md description 扩 non-trivial implementation 触发词（commit `e9360db`，origin/master，diff-installed clean）。
- **文档**：coding-agent CHANGELOG 门禁条目（含非沙箱边界 + 生效面）；multi-workers README「实施准入门禁」节 + `MW_IMPL_GATE_ROOT` 变量行。
- **仓级规则先行**（独立交付，非本 key AC）：AGENTS.md 新首节「AgenticTask Workflow」。

影响面：`packages/coding-agent/src/extensions/agent-team-loop/`（新模块 + index.ts +13 行）、`test/suite/`（新测试）、CHANGELOG ×1、multi-workers README、AGENTS.md、框架仓 SKILL.md ×1。**生效条件：`mw setup --build` + 窗口重启**。

## 遗留

- **部署落地**：`mw setup --build` 重建 dist + 重启各窗口——重启前所有窗口仍无门禁 → 用户操作项（本 key 无法代做）。
- **bash 逃逸事后扫描器**（python -c 内联写、预写脚本等已知漏过的会话级扫描）→ 立新 key 候选，与 `_impl_gate.log` 审计配合。
- **protected-config 词法器同型反斜杠风险**：P-004 关联项提示其同型逻辑需在出现 Windows 反斜杠形态时同步检查（当前 11/11 回归未受影响）→ 接受暂不处理，已记录。
- **多项目配置化**：代码路径集当前为本仓默认（硬编码 + 注释），其他项目接入需按 P-002 模式复制适配 → 接受暂不处理。
- 本 key 自身即流程示范：4 worker 派发（2 research + 2 coding）+ PM 吸收闭环，无野生实施。
