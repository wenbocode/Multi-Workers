# T-02 RQ-2: agent-team-loop TS 入口面调研（run-detached 暴露形态）

- key: mw-console-storm-hardening · 第 1 批 · type: research
- type: research
- 唯一证据文件: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-ts-entry-surface-20261015.md`（只读调研，无其他写面）
- 写入允许面: `.agenticdoc/mw-console-storm-hardening/evidence/research/design-ts-entry-surface-20261015.md`；写入禁止面: 其余一切（纯只读调研，不改源码/测试/配置）
- 上下文: goal.md（.agenticdoc/goal.md）GC-2「不修改 pi 核心：所有功能通过 Extension API 实现」+ spec §1.1 L1（`python mw.py run-detached -- <cmd...>`）
- 锚点: `packages/coding-agent/src/extensions/agent-team-loop/worker-mode.ts:1`（worker 模式入口，PI_WORKER_TASK 分流）、`packages/coding-agent/docs/extensions.md:1`（扩展 API 总文档）、`packages/multi-workers/mw.py:506`（cmd_start）

## 写入允许面

- `.agenticdoc/mw-console-storm-hardening/evidence/research/design-ts-entry-surface-20261015.md`

## 写入禁止面

- 仓库其余一切（纯只读调研，不改源码/测试/配置）
- ac_refs: AC-008 · deps: 无（与 T-01/T-03 并行）
- 预计: 30-45min

## 目标

为"PM/Worker 会话内派发 `mw run-detached`"确定 TS 侧入口形态（AC-008），输出带 file:line 锚点的推荐方案。约束锚点：goal.md GC-2「不修改 pi 核心：所有功能通过 Extension API 实现」；spec §1.1 L1（Python CLI 已定为 `python mw.py run-detached -- <cmd...>`）。

## 调研面（只读）

1. **pi 扩展 API 事实**：`packages/coding-agent/docs/extensions.md` 与 `packages/coding-agent/examples/extensions/`——扩展能注册什么（custom tool？slash command？keybinding？），注册函数签名、工具 schema 定义方式、工具结果回传格式。列出与"派发后台命令并回传 marker/log 路径"最匹配的 API。
2. **agent-team-loop 现状模式**：`packages/coding-agent/src/extensions/agent-team-loop/` 全目录——PM 模式与 worker 模式各自的注册入口（`worker-mode.ts` / `pm/`）、已有 slash 命令的注册写法（如 `/worker`、`/mw-watch`）、已有 custom tool（如有）的写法、PM/Worker 模式判据（`PI_WORKER_TASK`）。找出"PM 和 Worker 都能用同一入口"的注册位置。
3. **进程派生先例**：agent-team-loop / pi 扩展里现有的 `child_process` 使用点（spawn/execFile）及其参数风格——TS 侧若直接 spawn `python mw.py run-detached`，应照抄哪个先例（stdin/stdout 处理、windows 隐藏语义是否需要 TS 关心——**预期不需要**：flag 契约在 Python 侧，AC-003 已锁定；TS 只是透传）。
4. **约束核对**：erasable TS（无 enum/namespace/参数属性）、top-level import（无 inline `await import()`）、biome 规则——列出实现时必须遵守的 3-5 条硬规则及出处。

## 必须回答的决策问题

- D1: 入口形态选 **registered tool**（LLM 可调用，类似 read/bash）还是 **slash command**（`/mw-run ...`，人/PM 手动）还是**两者共用一个内部函数**？给出推荐 + 理由（对照 spec AC-008 的"PM/Worker 会话内可发起后台命令派发并获知 marker/log 路径约定"）。
- D2: 若做 registered tool：工具名、参数 schema（cmd 数组 / cwd / log / marker / timeout-min）、结果返回字段；注册在哪个文件哪一节（file:line）。
- D3: Worker 模式下 PI_WORKER_TASK 会不会屏蔽 PM 工具注册（现有代码如何分流）？入口必须在两种模式都可用——指出可行挂点或明确"仅 PM 模式可用 + worker 用 bash 直调"的取舍。
- D4: 该入口是否需要进 `/mw build` bundle 之外的任何构建步骤（dist 镜像、settings 注册）？

## 硬契约

- 只读；唯一写面 = evidence 文件。禁止改任何源码/测试。
- 每个论断带 `路径:行号` 或 docs 锚点；无出处的结论不算证据。
- 不臆测 pi API——以 docs + examples + 现有源码三方交叉为准；docs 与代码冲突处显式标注。

## 步骤

1. 读 docs/extensions.md 全文 + 2-3 个 examples（挑与 tool/command 注册相关的）。
2. grep agent-team-loop 的注册点（`registerCommand`/`registerTool`/`pi.on(` 等），列出清单表。
3. 按 D1-D4 逐项给结论表。
4. 给一个最小实现草图（≤30 行伪代码，标注落点 file:line），design 阶段 PM 直接引用。

## 证据格式（写进 evidence 文件末尾）

```
[VERIFY] RQ2: register_points=<n> recommended=<tool|command|both> worker_mode_ok=yes|no build_step=<none|mw-build-only>
```

## 非空判定

D3 结论若为"仅 PM 可用"→ 必须给出 worker 侧替代路径（bash 直调 `python mw.py run-detached`）的论证，不得留"待定"。

## 交付

唯一 evidence 文件（注册点清单表 + D1-D4 结论 + 最小草图 + [VERIFY] 行）。
