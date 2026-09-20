# Spec: mw-partition-parent-extended

> Key: mw-partition-parent-extended
> 创建时间: 2026-09-20 15:05 (+08:00)
> 状态: confirmed（AC 已锁定）
> deps: mw-target-partition（本 key 修正其交付的 parent 只读语义；旧 spec 为归档历史不回改，本 spec 为 parent 语义现行事实源）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（存量项目，无 status 行，三段有真内容，视为已确立）

- 对齐：本 spec 服务于 goal「PM Agent 管理多个 Worker Agent 并行开发同一个项目」中 partition 模式的语义闭环——大项目子目标拆分场景下，worker 把 parent 当作分片工作区的扩展目录**直接开发**（读+写），而非只读旁观；文件驱动协调与 goal 锚点机制不变。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心，全部经扩展 API（TS）+ mw Python 实现（goal 原文约束）
  - GC-2: Worker 进程级隔离——本 key 不改 spawn/隔离/看门狗模型（goal 原文约束）
- 冲突：与 mw-target-partition 已交付 spec 的「parent 只读、无写回」定性冲突。处理：旧 key 已 DONE 归档、spec 为历史记录不回改；本 key 取代该语义点（记录于 pm-state Decisions 与 _project_log 关联行）。
- 预期收益（done 时对照判定）：
  - partition 任务对 parent 默认可读可写（"开始内容在 parent 内、直接开发"语义成立）；判定 = 全部生效 AC（AC-001~006）全绿 + dual/single 既有用例零修改全绿 + `npm run check` 0/0/0

## §1 功能概述

### 1.1 目标

修正 partition 模式的 parent 语义：parent 从「只读上下文」改为「**分片工作区的扩展目录**」。被切出来单独开发的功能块，其现有代码就在 parent 内——worker（cwd = partition root）将 parent 视为工作区的直接延伸：

- **可读**：read 包含性默认覆盖 parent root（有 `read_scope:` 的任务，parent root 自动在允许集）；
- **可写**：开发动作直接发生在 parent 内（写回 = 开发中直接写，无切出/复制/合并流程）。

无专门"切出"动作、无 merge-back 流程、无写路径防火墙（deny_globs 仍为读侧可选防火墙，且先于包含性生效，可对 parent 局部路径设防）。

（调研：evidence/research/spec-parent-extended-semantics-2026-09-20.md）

### 1.2 技术栈 / 语言

TypeScript（pi 扩展，Node strip-only 可擦除语法）+ Python（mw 框架）。TS/Py 渲染 line protocol 双侧 1:1。

### 1.3 核心用户场景

1. 场景 A（扩展读）：PM/autopilot 派发带 `read_scope:` 的 partition 任务（如 `["src/"]`），worker 读 parent 内现有代码文件不被 read-scope 层拦截（parent root 默认在允许集，两条派发路径行为一致）。
2. 场景 B（直接写回）：worker 开发中直接 edit/write parent 内文件（修改功能块在 parent 中的现有实现），无任何拦截；trace.log/output.md 仍写回控制根（现行语义不变）。
3. 场景 C（可选防火墙）：partition 配置 `deny_globs`（如 `**/DerivedDataCache/**`）仍对 parent 内匹配路径生效——deny 先于包含性，parent 并入允许集不绕过 deny。
4. 场景 D（措辞与注入）：`mw partition set --parent` 的 help 与报错文案、task.md profile 块的 parent 行，均反映扩展工作区语义（不再称 read-only context）。

### 1.4 范围说明（不做什么）

- 不包含：切出/复制动作（无 carve/seed 命令——用户明确不需要）
- 不包含：合并/写回父项目流程（写回 = 开发中直接写，无独立流程）
- 不包含：写路径防火墙（保持现状零拦截；deny_globs 仅读侧）
- 不包含：`roots:` 命名根自动并入允许集（仍显式声明才可达）
- 不包含：dual/single 语义改动；worker cwd、撕裂校验、doctor、trace/output 写回控制根等语义改动
- 不包含：parent↔control 根关系新增校验（沿用现行去重规则）

## §2 业务约束

### 2.1 平台 / 环境

Windows 优先，跨平台语义（realpath / normcase 归一）。CLI：`python mw.py partition ...`；窗口内：`/mw partition ...` 转发（本 key 不改命令面）。

### 2.2 性能指标（非验收性说明）

无新增性能面：Py 展开每次派发多一次字符串追加；worker 侧 union 为 task.md 解析时一次前缀扫描，量级与现有 frontmatter 解析等同。本节为设计约束说明，不设 AC。

### 2.3 安全约束

- fail-closed 既有路径零变化：解析/派发/spawn 拒绝路径、`read_scope:` 存在但空的**全拒**形态（union 不得作用于空 scope——不凭空造出包含集）
- 本特性零接触 `~/.pi/agent/` 下任何文件（P-002 路径规避）
- .agenticdoc 与 UTF-8 文本写盘一律走 write/edit 工具或 Python 显式 utf-8（P-001）

### 2.4 集成依赖

- Py 侧：`autopilot/dispatch.py`（`_expand_read_scope` partition 分支）、`mw.py`（两处文案）、`mw_common.py`（`render_partition_profile_md` 标签）
- TS 侧：`worker/read-scope.ts`（union 纯函数）、`worker/worker-mode.ts`（wiring：从 task.md 提取 parent root）、`pm/task-dispatcher.ts`（`renderPartitionProfileBlock` 标签）
- golden 双侧：`packages/multi-workers/test/fixtures/partition-profile-block.golden.md`、TS `agent-team-loop-profile-injection.test.ts` 断言
- `packages/multi-workers/dist/extensions/agent-team-loop.js` bundle 重建；`packages/coding-agent/dist` 随重建对齐

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-20T15:05:00+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 active: partition、三根（control/parent/partition）互异、任务 read_scope 非空且含相对条目时，`_expand_read_scope`（Py）返回值逐项等于 [相对条目按 partition root 锚定的绝对路径（保持原顺序与既有绝对条目）, control root, parent root]；parent 或 control 已在条目中（normcase 判定）时不重复追加；dual/single 模式同输入返回值与现行完全一致（零变化） |
| AC-002 | 在 task.md 含 `[mw] mode: partition` 模式行与 `Parent root` 前缀行（`:` 后为路径）、frontmatter `read_scope` 存在且非空时，worker 侧 read-scope 层将该 parent root 并入允许集：对 parent 内路径的 read/ls/find/grep 调用 verdict.allowed=true 且照常计入 caps；无模式行、非 partition 任务、或 `read_scope` 缺失/存在但空（全拒形态）时，允许集与现行完全一致（union 不生效） |
| AC-003 | 在 deny_globs 匹配 parent 内路径（如 `**/DerivedDataCache/**`）且 parent root 已并入允许集时，该 read 调用仍被拒且 rule="deny-glob"——deny 先于 scope 的判定次序不变 |
| AC-004 | 在 worker 工具调用 wiring 上，read-scope 拦截覆盖的工具集合仍为且仅为 {read, ls, find, grep}：对 parent 内路径的 write/edit/bash 调用不产生任何 read-scope rejection（现行写路径零拦截行为的回归锁定） |
| AC-005 | 在措辞与注入上：(a) `mw partition set` 缺 --parent 报错文案与 argparse --parent help 均不含 "read-only"（改为扩展工作区表述）；(b) profile 块 parent 行标签为 `Parent root (extended workspace, writable):`，`mw_common.render_partition_profile_md` 与 TS `renderPartitionProfileBlock` 输出保持逐字节一致；(c) Py golden fixture 与 TS 注入断言同步为该标签 |
| AC-006 | 在零回归上：dual/single 全部既有用例零修改全绿；partition 既有用例中仅 AC-001（`_expand_read_scope` 展开断言翻转）与 AC-005（标签/golden 断言）直接关联处更新，其余零修改；`npm run check` 输出 0 error / 0 warning / 0 info |

## §4 风险与未决项

- 风险：worker 侧 union 新增 profile 块解析点（`Parent root` 前缀行提取）——以 `[mw] mode: partition` 模式行门控，与撕裂校验共用块内锚点语义；解析器须兼容新旧两种标签形态（升级时在途 task.md）
- 风险：标签变更触碰双侧 golden 与既有断言（AC-006 限定修改面，防扩散）
- 风险：`_expand_read_scope` 追加顺序变化影响依赖精确列表的既有测试——AC-001 锁定顺序 [条目…, control, parent]
- 待确认：无

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- mw-target-partition 全套渲染/golden/parity 基建：`render_partition_profile_md` ↔ `renderPartitionProfileBlock` golden parity 用例、`test_partition_dispatch.py`、`agent-team-loop-profile-injection.test.ts`——标签变更直接复用其同步机制
- mw-dual-workspace 的 read-scope 层（`read-scope.ts` 纯函数 + `worker-mode.ts` wiring + dual-basis deny 匹配）——union 作为纯函数扩展进该层，caps/deny 逻辑零改动
- `_expand_read_scope` 既有测试布局（`TestExpandReadScopePartition`）——AC-001 断言原地翻转

### 需规避坑点

- P-001（PowerShell 文本管道损坏无 BOM UTF-8）：本 key 的 spec/golden fixture/测试文件写盘一律 write/edit 工具或 Python 显式 `encoding="utf-8"`；禁止 PS 读-改-写往返
- P-002（跨窗口共享凭据文件）：本特性实现与测试不得引入对 `~/.pi/agent/` 下任何文件的写路径
