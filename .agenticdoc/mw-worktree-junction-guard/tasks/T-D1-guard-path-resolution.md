# T-D1 — G1 guard 的命令解析与路径解析可行性（design 期 RQ-D1）

- type: research
- key: mw-worktree-junction-guard
- 角色约束: 只读；允许 read/find/grep/ls/bash，但禁止任何破坏性命令
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-guard-path-resolution-20261013.md`

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 核心交付是「一个常驻 mw 服务 + 多 Worker 并行开发同一个项目」，其可行性前提是共享工作树/依赖环境在并发下不被破坏；G1（执行前拦截）是「危险路径不可达」的第一道机械保证。
- **事故事实（可直接引用，不必重做）**: `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md`（v3）§1 —— 元凶命令**原文**是 PowerShell 形态：`cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"`（来源 `2026-10-09T12-07-43-157Z_01a1208f-e335-....jsonl:142`）。**目标是环境变量插值，不是字面路径**；同一事故中 `packages/tui` 被删 156/236。
- **spec 期已坐实（直接引用，不要重做）**:
  - guard 落点/注册范式：`packages/coding-agent/src/extensions/agent-team-loop/shared/protected-config.ts:247-274`（`registerProtectedConfigGuard`），注册点 `packages/coding-agent/src/extensions/agent-team-loop/index.ts:42`；
  - 拦截点：`pi.on("tool_call")` → `ToolCallEventResult={block?,reason?}`（`packages/coding-agent/src/core/extensions/types.ts:1236` / `:1071-1074`），**无结构化错误码**；
  - 可复用解析件：`parseBashSegments`（`packages/coding-agent/src/extensions/agent-team-loop/shared/implementation-gate.ts:361`，**模块私有、未导出**）、`checkBashWriteTarget`（同文件 `:612-637`，已导出）；
  - handler 内做 fs 有先例：同文件 `:761` → `:247`（readdirSync）。
- 相关 spec 验收：`spec.md` AC-001（命中即 block）、AC-002（报错含可照抄的 `mw worktree rm <path>`）、AC-003（**不含** reparse point 的 worktree 必须零副作用放行，不得误拦）。

## 要求（必须给「原文 + 文件:行号」）

1. **hook 能拿到什么 / 能做什么**：读 `types.ts` 中 tool_call 事件的类型定义与实际 handler 原文，回答：handler 能否拿到命令**原文**、cwd、环境变量、工具名；能否在 handler 内**同步**做文件系统枚举（有无异步限制/超时/抛出语义）；多个 handler 的 block 短路路径。给类型与原文行号。
2. **从命令文本取出 `<path>`**：对下列形态逐类给出结论（读源码 + 可用本地最小复现验证解析结果，**不要碰真树**）：
   - PowerShell：`cd X; <cmd>`、`Set-Location`、`$env:TEMP\qg-head`、`$t` 前置赋值 + 后引用、双引号插值、单引号、`;` 分段、`|` 管道、`2>&1`；
   - POSIX：`rm -rf <path>`、`Remove-Item -Recurse <path>`、引号/反斜杠/正斜杠三种拼写；
   - `parseBashSegments`（与 `checkBashWriteTarget`）对这些形态**具体能/不能**处理什么（引用其常量与分支行号；特别指出 PowerShell 变量与环境变量插值是否在能力范围内）。
3. **路径不可静态解析时的策略（本次最重要的设计输入）**：对四种情形给出可判定规则草案 + 理由（并说明各自对 AC-003 误拦风险的影响）：(a) 字面路径可解析；(b) 含 `$env:` / `$var` / `%VAR%` 插值；(c) 含通配或尾分隔符；(d) 命令含多段/`cd`，目标为相对路径。**至少要给出能拦下本次事故命令（形态 b）的最小规则**。
4. **目标已不存在时**：`git worktree remove` 的目标目录可能已被删（事故当天就是这样）；枚举失败（不存在/权限/断链）时应当 block 还是放行，给判据与理由。
5. **未坐实项**显式列出（不得把推测写成结论）。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-guard-path-resolution-20261013.md`（本卡唯一允许写入的文件；其余路径只读）

单一文件 `evidence/research/design-guard-path-resolution-20261013.md`，结构：

- `## TL;DR`（≤10 行，含每条要求的结论一句话）
- `## 事实`（逐条 `[VERIFY]` 行：命令/函数原文 + `文件:行号` + 实测输出）
- `## 对 design 的直接含义`（可直接写进 design.md 的接口/判定草案）
- `## 未坐实 / caveat`

约束：只读；禁止执行任何破坏性命令，禁止触碰真树 `H:\git\Multi-Workers` 的 junction 或 `node_modules`（可在 `%TEMP%` 内造 fixture）；数值一律实测，推算值必须标注为推算。
