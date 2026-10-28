# Spec: claim-driven-review

> Key: claim-driven-review
> 创建时间: 2026-10-20
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（无 status 行但三段有真内容 → 存量项目，视为已确立）

- 对齐：本 spec 服务于 goal「解决单 Agent 长上下文溢出和无法并行的问题」中的**溢出侧**（审查类 worker 的上下文失败）与「文件驱动的去中心化协调」中的**证据契约侧**（断言裁决以文件落盘、可回读）。不涉及并行调度本身。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心——本 key 全部落在 Extension API 与 mw Python 侧。
  - GC-2: 工具白名单按任务类型——本 key 不改变任何角色的工具集（包含"是否给 review 加 bash"这一未决项）。
  - GC-3: 文件锁并发控制——派发期校验必须在既有 `workers.lock` 临界区内完成，拒绝零副作用。
  - GC-4: goal.md 作为项目级目标锚点——派发卡仍须携带 goal 引用 + 路径:行号种子。
  - GC-5: 不引入中心化调度器——triage/扇出/merge 的协调只通过 task.md 与证据文件。
- 冲突：与「审查结论独立性」存在潜在冲突——把审查变成可机检表格会诱导"只写能自动判的断言"。处理：`unverified` 是一等裁决档位（不得静默 PASS），且 `未覆盖面声明` 保持必填。
- 预期收益：本 key 达成后对项目目标的具体贡献（可观察、可验证；done 时在 achieved.md 对照判定）：
  - 审查成本与断言数量绑定、与仓库规模解绑：单 review 单元的取数次数从实测 159 次降到 ≤60 次，死亡上下文从 214k 降到 ≤120k（判定方式：`trace.log` 的 `[FLOW] tool_call` 计数 + 会话 usage）。
  - review 因超窗进入模型降级链的次数归零（判定方式：`[MODEL_FALLBACK]`/`model unavailable` 在 review 类 run 上的计数 == 0）。
  - 每份 review 报告的可判定率可测：`tokens_per_closed_claim` 作为跨 key 可比指标（判定方式：`mw status` / usage 报表列）。

## §1 功能概述

### 1.1 目标

把 review 从"读工程"改成"判断言"：由卡片声明可证伪的断言集（每条带反证条件、最小取证定位、机检判据、取数预算），由 worker 在预算内定点取证并逐条裁决，由框架在结算期强制校验覆盖与证据引用，并由度量面给出可比较的成本指标。目标不是让 review 读得更少，而是让**成本与断言数量绑定**，从而与仓库规模无关。

### 1.2 技术栈 / 语言

TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/**`）+ Python（`packages/multi-workers/**`），无 pi 核心改动。

### 1.3 核心用户场景

1. PM 要关闭上一轮 QG 的 6 条发现：PM 写断言卡（6 条 claim + 定位 + 判据），框架拆成 4 个 review 单元并行，合并单元只读 4 份裁决。
2. conductor 在 L3 阶段自动复核一个 key 的 AC 矩阵：断言来自 spec §3 的 AC 行，判据是"AC-00N 有证据引用"。
3. 大面审查（如"扩展层是否仍有 direct-write 通道"）：triage 单元先用 diff + 反模式 grep 产出断言集，再扇出取证。

### 1.4 范围说明（不做什么）

- 不包含：review 角色的工具集变更（是否加 `bash` 另立 key 决策）。
- 不包含：pi 核心的循环内压缩（`agent-session.ts` 的 `_checkCompaction` 调用点）。
- 不包含：自动修复（只看不修）。
- 不包含：`read_scope` 既有默认值（8 次 / 65536 B）的修改。

## §2 业务约束

### 2.1 平台 / 环境

Windows 开发机 + Python 3.14 + Node；worker 由 launcher spawn（print mode，`pi -p`）；PM 侧为交互 pi 窗口。

### 2.2 性能指标

- 单 review 单元：≤60 次证据取数、≤120k tokens 峰值上下文。
- 派发期校验：纯字符串/正则解析，≤50ms，不读文件内容（仅 stat 尺寸）。
- 结算期校验：产物已在内存，≤20ms。

### 2.3 安全约束

- claims 块**不得**成为绕过写面守卫的通道：它是约束消费者（预算/覆盖），不授予任何写权限。
- worker 仍受 `write_face` / `read_scope` / `deny_globs` 约束；本 key 只新增"预算来源"，不新增放行面。
- 断言证据引用必须是 `path:line` 或"命令 + 期望结果"形态，禁止裸结论。

### 2.4 集成依赖

- 派发卡 gate（`shared/dispatch-card.ts`）：envelope + type extras + seed 最小项。
- 结算恢复契约（`worker/output-sections.ts`）：`RECOVERY_SECTIONS` / `checkRecovery` / 一次性 self-check steer。
- 读面预算（`worker/read-scope.ts` + `autopilot/dispatch.py::_read_scope_caps`）。
- 度量（`usage.py` 与 `pm status` / `status-model.ts`）。
- 类型平价锁（`test_autopilot_l0.py` T-17、`test_autopilot_dispatch.py`）与词汇表单源（P-08）。

## §3 验收标准（AC）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | review 卡可声明机器块 `<!-- mw-claims: v1 -->`：每行 `id/类型/陈述/反证条件/定位/判据/预算`。派发期判定（出处 `evidence/research/spec-rq3-claim-taxonomy-20261020.md` §2/§5/§6）：① id 形如 `C-\d{2,3}`；② `类型` 自报 ∈ {`cmd`,`grep`,`struct`,`manual`} 且与 `判据` 前缀（`cmd:` / `grep:` / `shape:` / `manual:`）一致；③ 陈述与反证条件非空，且去否定归一化相似度 < 0.90（防同义反复）；④ 定位为 `path:line` / `path:a-b` / symbol，目标文件 >32768 B 时必须带行段；⑤ `Σ预算`（manual 按 2 计）≤ 角色上限 40，manual 条数 ≤ `min(4, ceil(n/3))`；⑥ `判据: cmd: TBD(<测试名>)` 属合法待定通道，放行并计入预算。**不得**校验“判据必须可执行”（实测 21 个 cmd 类判定单元中 11 个在卡里没有任何执行串）。不满足 → 拒绝且零副作用，原因含 claim id 与失败条款号；校验对象是卡文与 claims 块，**不得**以渲染后 task.md 的自动填充值为依据（`dispatch.py:467-469` 自动填 `审计目标`、`launcher.py:1867-1875` 注入 `[ENVELOPE_FALLBACK]`）。 |
| AC-002 | 结算期覆盖判据（schema 出处 RQ-3 §5）：产出必须含 `## 断言裁决` 七列表 `claim/类型/裁决/判定/证据/取数/原因`。（a）`裁决` ∈ {`closed`,`partial`,`unverified`}，`判定` ∈ {`成立`,`不成立`,`无法判定`}，**两列分置**（closed ≠ PASS）；（b）卡内 claim id 与表内 id **双向相等**；（c）`closed`/`partial` 行必须有 1–3 条证据 ref，语法 `path:line[-line][「excerpt」]` 或 `verb … => rc=<n>`；路径必须相对且存在、行号 ≤ 文件行数、`b-a ≤ 200`；（d）`unverified` 行原因 ∈ 7 词闭集 {`budget`,`no-access`,`not-found`,`ambiguous`,`environment`,`out-of-scope`,`awaiting-input`} 且单源（TS/Python 平价锁）；（e）解析容忍表头别名/列序/全角/fenced-block（P-048）；（f）缺项 → 一次 self-check steer，仍缺 → `exit 2`（needs-clarification），不新增终态、不静默 `done`。 |
| AC-003 | 预算承载（标定值，出处 `evidence/research/spec-rq1-review-corpus-20261020.md` §3/§5）：单元派发时由 claim 数推导读面 caps —— `fileCap = min(30, 6×claims)`、`byteCap = min(393216, claims×65536)`；窗口安全带依据：累计取数结果 >650k chars 必降级、<400k chars 全部存活（p50 单次取数成本 3,230 tokens、p90 4,854）。超预算未取证的 claim 必须记为 `unverified` 且原因含 `budget`，不得记 `closed`。 |
| AC-004 | 编排形态：支持 `triage → 扇出 → merge` 三步，手工 `dispatch_worker` 与 conductor 两条通道语义一致；**每 worker 默认 5 条 claim**（30 次取数 ÷ 历史 p50 5.97 次/单元）；merge 单元只读各单元裁决文件。端到端判据：一张 20-claim 卡（判定单元 p90）跑出 4 个取证单元 + 1 个 merge 单元，全部 `exit=0` 且 merge 产出含 20 行裁决；拆分判定式为 `claims > 5`。 |
| AC-005 | 度量：每次 run 记录 `claims/closed/partial/unverified/fetches/tokens`，并按 `类型` 与 `档位`（machine/manual）分列输出覆盖表；`mw status`（或 usage 报表）输出 `tokens_per_closed_claim`。（a）判据：同一任务两种拆法（1×20 与 4×5）跑出的该指标可在报表中并排比较。（b）前置判据：每个派发的 worker 必须留下 `~/.mw/usage/runs.jsonl` 的 `start` 行且含 `session_id`——现语料仅 6/115 attempt 可精确 join（`usage.py:1010-1014`），token 不可归因时该指标必须显示为 `n/a` 而非近似值。 |
| AC-006 | 灰度：claims 块默认 advisory（告警不拒绝），开关 `claim_gate: advisory\|enforce` 在 TS/Python 两侧同名同义；advisory 期间既有 review run 的退出码分布与完成率相对基线不变（附前后对比证据）。 |
| AC-007 | 零回归：未带 claims 块的 review 卡行为逐字节不变；`read_scope` 默认值（8 / 65536）不变；T-17 类型平价锁、P-08 词汇表测试、`output-sections` 既有恢复契约测试保持全绿。 |
| AC-008 | 反绕过判据集（RQ-3 §4 B-1…B-10，零成本、不调 LLM）：① 证据不得以自证集合 `{report*.md, output.md, progress.md, task.md, 卡自身}` 作唯一来源；② `unverified` 占比 > 40%（review 角色 ≤60%）时不得 PASS，需升级 PM；③ `Σ取数` ≤ `min(卡 Σ预算, fileCap)` 且 ≤ trace 中读类 `tool_call` 计数；④ `struct` 行不计入 closed 分子，子行仅允许 `C-01.3` 且父为 `struct`；⑤ 含 `[ENVELOPE_FALLBACK]` 的 extras 视为缺失；⑥ 复用上轮裁决必须写 `carried-from: <path:line>`。每条判据附一条负例测试（构造一份合规但空跑的产出，断言被拦）。 |

## §4 风险与未决项

- 风险（Goodhart）：可机检断言挤出难以机检但更重要的发现。缓解：`unverified` 一等档位 + `未覆盖面声明` 必填 + PM 抽检 3 条/报告。实测支撑：104 个真实判定单元中 **26 条（25.0%）只能是 manual**，`manual` 上限 `min(4, ceil(n/3))` 正是按这个自然比例定的。
- 风险（误拒）：P-048 的 schema 过严教训。RQ-3 的自动分类规则与人工裁决一致率仅 **66/104（63.5%）**，故分类器只能当**筛查器**：判据类由卡自报，validator 只校验“自报类与判据前缀一致”，不推断、不拒绝。
- 风险（产物自证）：46 次 review 派发中 **12 次（26.1%）只产出 `output.md`**，这 12 份 **0 份含 `[VERIFY]`**；29 份 report 中 17 份也没有 → “引用自证文件”必须是硬拒绝，不是告警。
- 风险（预算冲突）：`verifier` 的 8 次取数默认值是历史饥饿点（FeatureMigrator 0/23、0/31）。本 key 只新增 review 的预算配置项，**不改**该默认值。
- 风险（预算口径）：`chars/4` 实测**低估 20.5%**（est/真实 = 0.795，`compaction.ts:266` 注释所谓 conservative 对 toolResult 不成立），按它排预算会系统性超支 26% → 预算一律用**实测系数 ×1.26** 或直接按字节设。
- 待确认 1：`claim-review` 类型是否携带 `bash`（影响能否执行判据命令；也影响 AC-005b 的守卫覆盖面）。
- 待确认 2：enforce 的开关粒度（全局 vs 按 key 灰度）。
- 待确认 3：`read_scope` 是否有“单次取数”字节口径；若只有累计口径，AC-003 的单次 12 KiB 约束要另找落点（RQ-2 判定）。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- 派发卡 gate：envelope 三段 + 按类 extras + seed 最小项，落点 `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:150-270`。
- 结算恢复契约与一次性 self-check：`packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:48-210`（`RECOVERY_SECTIONS` / `checkRecovery` / `recovery-gap` steer）。
- 读面预算：`packages/coding-agent/src/extensions/agent-team-loop/worker/read-scope.ts:31-210`（`DEFAULT_READ_FILE_CAP=8`、`DEFAULT_READ_BYTE_CAP=65536`、`checkReadScopeCall`）+ `packages/multi-workers/autopilot/dispatch.py:224-270`（`_read_scope_caps`）。
- 机读证据行：`trace.log` 的 `[FLOW] tool_call` / `[TOOL]` / `[READ_SCOPE]` / `[END]`，可用于取数计数与成本度量。
- 会话 usage join：`packages/multi-workers/usage.py`（mw-usage-monitor key 沉淀），`tokens_per_closed_claim` 直接复用其解析。
- “N 值闭集 + 单源”先例：`packages/multi-workers/decision_points.py:111-120`（`ESCALATED_REASONS` 7 值，同模块注释记录了“两处各写一份就漂移”的教训）→ claims 的 `unverified` 7 词闭集照此单源，不要两侧各写。
- fence 状态机与 H2 别名匹配：`worker/output-sections.ts:128-188`（已处理 fenced block / blockquote / 别名 `includes`）→ 断言裁决表解析直接复用，不重写。
- 一次性 self-check 机制：`worker/worker-mode.ts:3962-4008`（`selfCheckSent` 每进程一次）→ AC-002 的“缺项只补一次”不需要新建状态。
- 类型平价与词汇表单源：`packages/multi-workers/test_autopilot_l0.py:234-263`（逐类 order-exact）、`shared/dispatch-card.ts::DISPATCH_TYPE_VOCABULARY`（P-08）。

### 需规避坑点

- P-007：review 无落盘通道 → 长报告流中断即全丢（`worker_file` 已补窄通道，但 64 KiB / basename-only）。
- P-048：`worker_file` 参数 schema 过严导致连续误拒、30 分钟零产出 → 新判据必须宽容解析。
- P-049：review 默认模型 `timi/gpt-6.1-sol` 出现 `stream closed` → 降级链；断言单元更短，但派发时仍需 fallback 就绪。
- P-046：派发描述里"动词+斜杠"被写面守卫误判为外部写路径 → claims 块文案避免该形态。
- `read_scope` 饥饿：8 次默认值曾使两个 L3 reviewer 花光配额、0/23 与 0/31 VC 无法断言（`autopilot/dispatch.py:224-250` 自记）→ review 预算要用新配置项，不套旧默认。
- extras 兜底与自证：`dispatch.py:467-469` 会用 prompt 首行自动填 `审计目标`，`launcher.py:1867-1875` 会注入 `[ENVELOPE_FALLBACK]` 骨架；`output-sections.ts` 只判“段名是否出现”。故任何“卡必须声明 X”的门禁必须看**卡文**，不能看渲染后的 task.md。
- 自评产物：46 次 review 派发中 12 次只有 `output.md`，那 12 份 **0 份含 `[VERIFY]`**；证据引用必须排除自证集合。
