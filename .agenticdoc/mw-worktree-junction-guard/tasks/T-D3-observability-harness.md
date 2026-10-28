# T-D3 — G4 可观测判据的数据源/代价 + AC-012 端到端验证夹具（design 期 RQ-D3）

- type: research
- key: mw-worktree-junction-guard
- 角色约束: 只读；允许 read/find/grep/ls/bash，禁止任何破坏性命令
- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-observability-and-verification-20261013.md`

## 上下文

- **目标锚点**: `.agenticdoc/goal.md` —— 并行承诺的可行性前提是共享工作树不被破坏；G4 要求同类事故**可被机器发现**而非靠人撞见。
- **事实锚点**: `.agenticdoc/mw-workspace-incident-probe/evidence/incidents-timeline-20261009.md`（v3）§6 G4 —— 本次 **3,456** 个已跟踪文件消失、约 **5.5 分钟**零报警（08:32:18.452Z 起删、08:38 才被恢复）；v2 漏报面：`@earendil-works` 下仅剩 1 条 junction 也无人自动报警。spec 对应 AC-010（文件数骤降）、AC-011（junction 目标丢失）、AC-012（端到端复现：主树 mtime 与内容零变化）。
- **spec 期已坐实（直接引用，不要重做）**:
  - 断链判据（AC-011 可直接用）：`Test-Path <link>` 对 reparse point 本身为 True（**不能**当"目标完好"）；`Get-Item -Force <link>` 可读 `.LinkType/.Target`；`Test-Path <Target>` 为 False 才是目标丢失 —— 见 `evidence/research/spec-junction-semantics-20261009.md` §7.3；
  - 枚举原语与最小实现（显式栈、命中 reparse point 不再下钻）：同上 §7.1；仓库内**无**现成探测工具（0 命中）；
  - 测试基线：TS 侧 `packages/coding-agent/test/suite/harness.ts` + faux provider（范式示例 `packages/coding-agent/test/suite/xkey-gate-guard-coverage.test.ts:121-131`）；Python 侧 `packages/multi-workers/test_doctor_gates.py`、`test_rag_cli.py`；非 e2e 全量入口 `./test.sh`（见 `spec-guard-and-mw-seams-20261009.md` §6）。
- **spec 期已坐实（mw 侧）**: doctor 挂载点 `packages/multi-workers/mw_common.py:2957-2996` / `:2780` / `:2999`，注入点 `packages/multi-workers/mw.py:522-532`。

## 要求（必须给「原文 + 文件:行号 + 实测数字」）

1. **「已跟踪文件数骤降」判据（AC-010）的数据源与代价**：在本仓实测 `git ls-files` 计数与 `git status --porcelain` 计数的**耗时与输出量**（给命令与实测数字）；在 mw 侧找出**周期性/可挂钩的采样点**（`mw serve` 循环、看门狗、`mw status`、`mw doctor`，给 `文件:行号` 与现有调用频率）；给出一个可复算的实现草案（采样窗口、阈值建议、与"正常波动"的区分，例如单文件编辑/一次 commit），并说明为什么不会误报。
2. **「junction 目标丢失」判据（AC-011）的数据源与代价**：枚举根 `node_modules/@earendil-works/*` 的链接状态（`LinkType`/`Target`/目标存在性）实测耗时与输出；区分断链、真目录、指向仓库外的链；给出该判据挂在哪（doctor 段 vs 看门狗）与理由。
3. **AC-012 端到端夹具（本次最重要的设计输入）**：给出在 `%TEMP%` 内**安全**复现"worktree + 指回仓库的 junction"的做法（不得指回真树 ⇒ 用什么替代"真树"才能复现同一伤害面/同一 API 穿透行为；可参考 `spec-junction-semantics-20261009.md` §1/§10 的 fixture 做法并给行号）；「主树 mtime 与内容零变化」的**机器判据**怎么做（manifest 草案：`git ls-files -z` + `hash-object`，或 mtime+size 清单；给可执行片段与实测输出）；仓内是否已有同类 before/after 夹具可照抄（给 `文件:行号`）。
4. **误报/漏报对照**：为 AC-010/AC-011 各给一个**阴性对照**的可执行想法（正常波动不触发 / 完好链不触发）。
5. **未坐实项**显式列出。

## 交付格式

- 唯一证据文件（唯一写面）: `.agenticdoc/mw-worktree-junction-guard/evidence/research/design-observability-and-verification-20261013.md`（本卡唯一允许写入的文件；其余路径只读）

单一文件 `evidence/research/design-observability-and-verification-20261013.md`，结构：

- `## TL;DR`
- `## 事实`（逐条 `[VERIFY]`：命令原文 + 实测输出 + `文件:行号`）
- `## 对 design 的直接含义`（可直接写进 design.md 的判据/夹具接口草案）
- `## 未坐实 / caveat`

约束：只读；**不得修改任何生产文件**；fixture 只在 `%TEMP%` 内建，禁止触碰真树 `H:\git\Multi-Workers` 的 junction 或 `node_modules`；数值一律实测，推算值标注为推算。
