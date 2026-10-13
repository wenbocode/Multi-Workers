# RQ-2 卡片语料实况：现有 `tasks/*.md` 的合规度与最小格式契约

- key: `mw-dispatch-card-gate` ／ 阶段：SPEC ／ worker: `mwd-rq2-card-corpus`
- 语料：`H:\git\Multi-Workers\.agenticdoc\*\tasks\*.md`（全仓全部 key）
- 仓库基线：`git rev-parse HEAD` = `6c5189831e938712040b84e0db0b6fadb1a3d1d8`
- 环境：Windows；bash 后端 PowerShell 5.1；Python 3.14.3；Node v24.19.0（`node_modules\.bin\tsx.cmd` 直跑 TS 单源模块）
- 唯一写入：本文件。只读语料，无 git 写操作，未跑 vitest/pytest/`npm run check`/`build`

## 0. 方法与环境记录

### 0.1 临时脚本写面

任务书要求临时脚本写 `.tmp/`。实测被守卫拦截（原文）：

```
write-scope: blocked bash write to .tmp: outside the worker write surface [rule=scope];
allowed: H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2-card-corpus or H:\git\Multi-Workers\.agenticdoc\mw-dispatch-card-gate\evidence
```

（同一守卫对 `workers\mwd-rq2-card-corpus\probe.txt` 以**相对路径**同样拦截，改用绝对路径后放行；`progress.md` 不受限。）
因此全部脚本、中间产物落在 worker 自身目录：`.agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2-card-corpus/`。脚本清单：

| 文件 | 作用 |
|---|---|
| `scan1.py` / `scan1-out.txt` | 语料清点、字节统计、全量标题词表 |
| `scan2.py` / `scan2-signatures.txt` | 每卡 H1/H2/H3 签名（345 行） |
| `scan3.py` + `scan4.py` / `scan4-report.txt` / `scan4-variants.txt` / `scan4-cards.tsv` | 三段判定、计数矩阵、变体频次、逐卡明细 |
| `typecheck.mts` / `typecheck2.mts` / `typecheck-out.json` / `typecheck-summary.txt` | 直接 import `shared/task-frontmatter.ts` 跑 `readTaskType` |
| `extra.py` / `scan4-extra.txt` | 分 key 通过率、BOM、H2=0 名单 |
| `tsum.py` / `enc-probe.md` | 汇总、编码回环验证 |

### 0.2 判定规则（三段 + 语义兜底）

标题侧（H2 及以下，正文非空的节）用**前缀匹配**（先剥编号前缀 `1.` `(1)` `A.` 等），族归属按 `交付` → `背景/问题/现状` → `目标/描述/输入` → `要求/验收/必须…` → `约束/禁止/纪律` → `元信息/状态/执行记录` 的顺序取首个命中：

| 槽位 | 标题族（正则族） | 证据别名 |
|---|---|---|
| 上下文 ctx-strong | `背景|上下文|问题|现状|动机|根因|缺陷|偏差|Context|Motivation|Rationale|Why` | 30 种写法 / 57 次 |
| 上下文 ctx-intent（备选槽） | `目标|描述|输入|前置|范围|Goal|Objective|Description|Input|Scope` | 10 种写法 / 312 次 |
| 要求 req | `要求|任务|必须|实现|步骤|改动|变更|契约|验收|验证|完成判定|完成判据|判据|行为|测试|接口|用例|协议|内容|标准|做法|策略|断言|规范|编码|对照|反例|反向|Acceptance Criteria|Requirement|Expected Behavior|[VERIFY]|AC |VC |TDD` | 104 种写法 / 469 次 |
| 交付物 deliv | `交付物|交付|预期产出|预期产物|产物|输出|证据|证据格式|报告要求|回执|Deliverable|Expected Output|Artifact` | 17 种写法 / 304 次 |

段落侧（无语义标题时兜底）：
- ctx-sem：正文含 `背景|动机|原因|由于|因为|现状|痛点|为什么|为何|根因`，或出现键值 bullet `^-\s*(背景|动机|问题|现状|范围|规格|目的|前提)\s*[:：]`；
- req-sem：正文含 `AC-\d+` 或 `VC-\d+`，或键值 bullet 键名含 `要求|规格|验收|必须|步骤|实现|改动|协议|契约|条件`；
- deliv-sem：正文含 `report.md|progress.md|output.md|evidence/|回执`，或键值 bullet 键名含 `产物|交付|佐证|证据|输出|结果|报告`。

「节正文非空」判据：该 H2 之后到下一个同级/更高级标题之间至少有 1 行非空内容（`d["nlines"] >= 1`）。

> 实现备注（透明度）：首版 `classify()` 对 `[VERIFY]`/`AC `/`VC ` 这类全大写 pattern 走错了分支（被当字面量转义），导致 47 张卡的 `[VERIFY]` 节与 8 张 `AC 摘录` 节被判成 `other`。已修正为统一 `re.I` 前缀匹配并重跑，本文所有数字均为修正后结果（修正使 req 槽命中 238→240，T1e 合规 106→108）。

### 0.3 三分骨架与两个反例

本仓 `tasks/*.md` 实际存在**两种体裁**，这是后面所有比例数字的分母性质：

1. **派发卡**（给 worker 的作业书）：`# Task T-xx: …` + 5~8 个 H2 节；
2. **结案记录卡**（事后回填的完成记录，很短，常无 H2）：例如
   `.agenticdoc/mw-ue-toolchain/tasks/T1-mw-common-helpers.md`（521 B / 5 行，只有 H1 + `- 状态: / - 产物: / - 佐证:` 三个 bullet）。

H2 数直方图（`scan4-report.txt`）：

```
H2-count histogram: {"0": 17, "1": 1, "2": 23, "3": 53, "4": 42, "5": 102, "6": 47, "7": 46, "8": 12, "10": 1, "13": 1}
```

即 **209/345 卡有 >=5 个 H2**，**41/345 卡 H2<=2**（其中 17 卡完全没有 H2）。

## 1. 语料清点

### 1.1 命令与原始输出

```powershell
Get-ChildItem -Path .agenticdoc -Recurse -Directory -Filter tasks | Measure-Object | Select -ExpandProperty Count
# -> 37
Get-ChildItem -Path .agenticdoc -Recurse -File -Filter *.md | Where-Object { $_.DirectoryName -like '*\tasks' } | Measure-Object | Select -ExpandProperty Count
# -> 345
```

`scan1.py` 原始输出（`scan1-out.txt` 前 6 行）：

```
glob: H:\git\Multi-Workers\.agenticdoc\*\tasks\*.md
card_count: 345
key_dirs_with_cards: 37
cards_per_key: {"agent-team-loop": 23, "ai-baseline-repair": 5, "autopilot-monitor": 2, "goal-autopilot": 18, "mw-autopilot-advance-root": 6, "mw-autopilot-slot-capacity": 24, ... "xkey-repair-mechanism": 9}
total_bytes: 1111668
bom_files: 15
```

补充：`tasks/` 下**没有深层嵌套**（`...tasks\*\*.md` 匹配 0 个），所以 345 就是全量。

### 1.2 计数矩阵（卡数 × 三段 → 有/无）

**矩阵 A：只认显式标题，上下文 = ctx-strong 族**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 29 | 8.4% |
| 0 | 0 | 1 | 76 | 22.0% |
| 0 | 1 | 0 | 80 | 23.2% |
| 0 | 1 | 1 | 103 | 29.9% |
| 1 | 1 | 0 | 13 | 3.8% |
| 1 | 1 | 1 | 44 | 12.8% |

单槽 yes 计数：ctx 57/345 = 16.5%，req 240/345 = 69.6%，deliv 223/345 = 64.6%。

**矩阵 B：上下文槽放宽到 `ctx-strong ∪ ctx-intent`（目标/描述/输入）**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 17 | 4.9% |
| 0 | 1 | 0 | 19 | 5.5% |
| 0 | 1 | 1 | 39 | 11.3% |
| 1 | 0 | 0 | 12 | 3.5% |
| 1 | 0 | 1 | 76 | 22.0% |
| 1 | 1 | 0 | 74 | 21.4% |
| 1 | 1 | 1 | 108 | 31.3% |

单槽 yes：ctx 270/345 = 78.3%，req 240/345 = 69.6%，deliv 223/345 = 64.6%。

**矩阵 C：标题 或 段落语义**

| ctx | req | deliv | 卡数 | 占比 |
|---|---|---|---|---|
| 0 | 0 | 0 | 1 | 0.3% |
| 0 | 0 | 1 | 7 | 2.0% |
| 0 | 1 | 0 | 17 | 4.9% |
| 0 | 1 | 1 | 20 | 5.8% |
| 1 | 0 | 1 | 1 | 0.3% |
| 1 | 1 | 0 | 26 | 7.5% |
| 1 | 1 | 1 | 273 | 79.1% |

单槽 yes：ctx 300/345 = 87.0%，req 336/345 = 97.4%，deliv 301/345 = 87.2%。

原始输出见 `scan4-report.txt` 的 `== A/B/C) ==` 小节；逐卡布尔值见 `scan4-cards.tsv`；345 行完整清点表见**附录 A**。

### 1.3 分 key 通过率（矩阵 B 口径，pass = ctx_ext ∧ req ∧ deliv）

```
key                                  cards  T1e-pass  T1e-fail
agent-team-loop                         23         6        17
ai-baseline-repair                       5         0         5
autopilot-monitor                        2         2         0
goal-autopilot                          18         0        18
mw-autopilot-advance-root                6         3         3
mw-autopilot-slot-capacity              24        24         0
mw-autopilot-stall-feedback              9         0         9
mw-autopilot-verify-cli                 10         0        10
mw-crosskey-risk-escalation              2         2         0
mw-dispatch-flow-fixes                  14         0        14
mw-dispatch-reliability                 15         0        15
mw-dispatch-role-escape                  3         0         3
mw-dispatch-settle-gates                12         8         4
mw-done-closure-repair                  11         0        11
mw-dual-workspace                       12         0        12
mw-gate-verdict-hardening               23        22         1
mw-guard-form-hardening                 19         3        16
mw-implementation-gate                   4         0         4
mw-l3-fail-marker-forms                  7         0         7
mw-parallel-protocol                     1         1         0
mw-partition-parent-extended             4         0         4
mw-provider-routing                      6         0         6
mw-rag-config-guide                      3         0         3
mw-rag-integration                      14         0        14
mw-rag-integration-fix                   5         1         4
mw-rag-window-parity                     5         4         1
mw-target-partition                     12         0        12
mw-task-scope-isolation                  3         0         3
mw-ue-toolchain                          6         0         6
mw-vision-role                          19        16         3
mw-widget-terminal-lifecycle             9         0         9
mw-worker-progress-persist               6         5         1
mw-worker-timeout-convergence            8         0         8
mw-worker-tree-kill                      3         0         3
mw-worker-visibility-gate                6         5         1
timi-gpt-pi-routing                      7         5         2
xkey-repair-mechanism                    9         1         8
```

关键观察：**最近一批 key 家族已经天然合规**（`mw-autopilot-slot-capacity` 24/24、`mw-gate-verdict-hardening` 22/23、`mw-vision-role` 16/19、`mw-worker-visibility-gate` 5/6、`mw-worker-progress-persist` 5/6、`mw-dispatch-settle-gates` 8/12、`mw-crosskey-risk-escalation` 2/2、`mw-parallel-protocol` 1/1），说明三段标题契约对**新派发卡**是可执行的；失败集中在 2026-09 前后的旧家族与结案记录卡。

### 1.4 规模分布（非空门槛用）

```
bytes: min=379  p5=803  p25=1823  p50=2744  p75=4375  p95=7301  max=11338
lines: min=5    p5=15   p25=27    p50=45
cards < 800 bytes: 17 ；cards < 1000 bytes: 44 ；cards < 1500 bytes: 69
cards < 15 lines: 16 ；cards < 20 lines: 39 ；cards < 30 lines: 99
coding/记录卡无关：T1-pass 卡 bytes min=2271 p50=4321 ；T1-fail 卡 bytes min=379 p50=2516
```

## 2. 命名变体频次表

（`scan4.py` 对 H2+ 且正文非空的节做族归属；occ = 出现次数，cards = 涉及卡数）

TOP 变体（完整表见**附录 B**）：

| occ | cards | 族 | 标题 |
|---|---|---|---|
| 118 | 118 | meta | `基本信息` |
| 116 | 116 | ctx-intent | `描述` |
| 92 | 92 | ctx-intent | `输入` |
| 90 | 90 | ctx-intent | `目标` |
| 89 | 89 | meta | `执行记录` |
| 77 | 77 | meta | `状态与证据` |
| 77 | 77 | deliv | `预期产出` |
| 74 | 74 | deliv | `交付物` |
| 72 | 72 | meta | `卡住记录` |
| 66 | 66 | meta | `Error Fingerprint` |
| 47 | 47 | req | `[VERIFY]` |
| 47 | 47 | deliv | `回执` |
| 43 | 43 | req | `步骤` |
| 41 | 41 | deliv | `交付` |
| 40 | 40 | req | `契约（不得重定义）` |
| 35 | 35 | meta | `风险与注意` |
| 32 | 32 | req | `验证` |
| 29 | 29 | req | `必须实现` |
| 29 | 29 | other | `非空洞对照（必须附在回执里）` |
| 29 | 29 | req | `验收命令` |
| 26 | 26 | req | `验收` |
| 25 | 25 | meta | `元信息` |
| 18 | 18 | req | `完成判定` |
| 18 | 18 | constraint | `禁止` |
| 18 | 18 | deliv | `证据` |
| 18 | 18 | other | `非空洞对照` |
| 16 | 16 | constraint | `约束` |
| 16 | 16 | deliv | `证据格式` |
| 15 | 15 | deliv | `报告要求` |
| 15 | 15 | meta | `注意` |
| 13 | 13 | meta | `卡元信息` |
| 13 | 13 | constraint | `源码` |
| 12 | 12 | req | `测试` |
| 11 | 11 | constraint | `依赖与阻塞` |
| 11 | 11 | req | `契约（逐字遵守）` |
| 10 | 10 | req | `完成判据` |
| 10 | 10 | req | `对照协议（plan.md §5）` |
| 10 | 10 | constraint | `硬约束` |
| 10 | 10 | ctx | `背景` |
| 7 | 7 | ctx | `背景（实测）` |
| 6 | 6 | ctx | `现状（以符号名为准）` |
| 6 | 6 | ctx | `问题（实证）` |
| 6 | 6 | req | `Acceptance Criteria` |
| 6 | 6 | ctx-intent | `Description` |
| 6 | 6 | req | `内容` |
| 6 | 6 | deliv | `Expected Output` |
| 6 | 6 | other | `Do NOT` |
| 6 | 6 | other | `Tool Constraints` |
| 3 | 3 | ctx | `背景（PM 实测，勿再声称未验证）` |
| 2 | 2 | ctx-intent | `前置（R1 纪律）` |
| 2 | 2 | req | `反向用例（必须真跑）` |

族总量（按出现次数）：`{"meta": 534, "intent": 312, "deliv": 304, "req": 469, "other": 194, "constraint": 102, "ctx": 57}`。
去重后**全仓 714 个互不相同的标题文本**（`scan1-out.txt`：`distinct_headings: 714`）；H1 364 次 / H2 1607 次 / H3 368 次。按槽位看写法碎片化：上下文槽 57 次出现用了 **30 种**标题文本，要求槽 469 次用 **104 种**，交付槽 304 次用 **17 种**（`famcount.py`）——这是"必须收成闭集"的直接依据。

要点：
- **上下文槽没有共识标题**：`背景` 只有 10 次，`问题（实证）` 6 次，而占据上下文位置的通常是 `目标`(90) / `描述`(116) / `输入`(92)——它们语义上混合了"做什么"和"为什么"。
- **要求槽**的高频形式是 `契约（不得重定义）`(40) / `必须实现`(29) / `验收命令`(29) / `步骤`(43)。
- **交付物槽**的高频形式是 `交付物`(74) / `预期产出`(77) / `交付`(41) / `回执`(47) / `证据`(18) / `证据格式`(16) / `报告要求`(15)；`非空洞对照（必须附在回执里）`(29) 与 `非空洞对照`(18) 是"证据形态"约束，但前缀规则把它们判成 `other`（以 `非` 开头，不匹配任何槽位前缀）——这正是前缀匹配的已知盲区，见 §6.1。
- 元信息槽（`基本信息`/`元信息`/`卡元信息`/`状态与证据`/`执行记录`/`卡住记录`/`Error Fingerprint`）不属于三段，但几乎每张旧卡都有。

## 3. 最小格式候选（可机器判定）

### 3.1 候选契约

```
C1 结构：首个 H1 标题（`# …`）存在，且正文至少 3 个 H2 节。
C2 三槽（每槽取其节正文非空，>=1 非空行）：
   上下文 ∈ { 背景 | 上下文 | 问题 | 现状 | 动机 | 根因 | 缺陷 | 偏差 }      -- 强式
            ∪ { 目标 | 描述 | 输入 | 前置 }                                -- 兼容式（ctx-intent）
   要求   ∈ { 要求 | 任务 | 必须实现 | 契约 | 验收 | 验收命令 | 完成判定 | 完成判据 | 判据 |
              步骤 | 改动 | 变更 | 测试 | 行为要求 | Acceptance Criteria }
   交付物 ∈ { 交付物 | 交付 | 预期产出 | 预期产物 | 证据 | 证据格式 | 报告要求 | 回执 | Expected Output }
C3 非空门槛：卡 >= 800 B（语料 p5 = 803 B）且 >= 15 行（语料 p5 = 15 行）。
C4 允许无标题？**不允许**用于新派发卡；但"无标题 + 键值 bullet"（`- 产物: …`）应作为**结案记录卡**的替代形态单列（见 3.3）。
```

### 3.2 两档门槛下的合规/不合规计数

| 门槛 | 判定 | 合规 | 不合规 | 不合规比例 |
|---|---|---|---|---|
| **T1 严**（`背景`族 + req族 + deliv族 三个显式 H2） | ctx ∧ req ∧ deliv | **44** | **301** | **87.2%** |
| **T1e 中**（上下文槽允许 `目标/描述/输入`） | ctx_ext ∧ req ∧ deliv | **108** | **237** | **68.7%** |
| **T2 宽**（标题 或 段落语义，二者之一） | (heading ∨ semantic) × 3 | **273** | **72** | **20.9%** |

叠加非空门槛的敏感性（不合规数）：

```
T1e 不合规中 bytes<400: 1  ; <600: 3  ; <800: 15 ; <1000: 38
T2  不合规中 bytes<400: 0  ; <600: 2  ; <800: 7  ; <1000: 14
T2 口径 + 仅统计 >=800B 的卡: 不合规 65（18.8%）
```

原始输出（`scan4.py` stdout）：

```
cards=345 T1fail=301 T1efail=237 T2fail=72 T2fail_ge800=65 h2zero=17
```

**建议采用 T1e（68.7% 历史卡不合规）+ C3 非空门槛，但对新派发卡收紧到 T1（背景族显式标题）**：T1e 相对 T1 多救回 64 张卡（不合规 301 → 237），这部分几乎全部来自 `目标/描述/输入` 这三个人为混合槽，若把它们当上下文，那么"上下文"这个词就失去判别力（矩阵 B 中 ctx=yes 78.3% 是虚高）。反过来 T1 只认 `背景/问题/现状`，与最近一批 key 家族的实际写法（`问题（实证）` / `目标` + `交付物` + `契约` + `回执`）不完全对齐 —— 这就是"要求必须收成闭集"的核心张力，宜由 SPEC 决定：**要么把 `目标` 正式收编为上下文槽（T1e），要么规定新卡必须写 `背景`（T1）**。

### 3.3 结案记录卡（无 H2）

17 张 H2=0 的卡全部来自 3 个旧 key，字节 521~2974：`mw-implementation-gate`(4)、`mw-l3-fail-marker-forms`(7)、`mw-ue-toolchain`(6)。它们用键值 bullet 表达同一信息：

`.agenticdoc/mw-ue-toolchain/tasks/T1-mw-common-helpers.md`（全文 5 行）：

```
# T1: mw_common 三纯函数
- 状态: done（主窗口直做）
- 产物: `sha256_eol_normalized`…、`discover_build_targets`…、`scan_build_error_lines`… + 节头 scope 注释
- 佐证: `packages/multi-workers/mw_common.py`…；`test_toolchain_cli.py::TestHelpers` 3 用例。
```

建议：机器契约只约束**派发卡**（`.agenticdoc/{key}/workers/*/task.md` 与作为输入的 `tasks/*.md`），记录卡走单独宽松门（键值 bullet 三键：`产物|佐证` + `状态`），否则历史记录卡会被整体误判。

## 4. 不合规典型样例（T1e 口径）

按"新派发卡是否会踩"选取，给路径 + 缺的槽：

| 路径 | 字节 | H2 数 | 缺什么 |
|---|---|---|---|
| `.agenticdoc/goal-autopilot/tasks/T-01-baseline-freeze.md` | 4459 | 5 | ctx：只有 `基本信息/描述/输入/预期产出/状态与证据`，无背景（`描述` 里混了动机） |
| `.agenticdoc/mw-dispatch-reliability/tasks/T-01-mw-common-credentials.md` | 2555 | 5 | ctx：同上模板 |
| `.agenticdoc/mw-rag-integration/tasks/T-02-ADAPTER.md` | 6629 | 3 | deliv：只有 `基本信息/描述/完成判定`（产物写在 `描述` 里，没有独立交付节） |
| `.agenticdoc/mw-provider-routing/tasks/T1-providers-prefix.md` | 852 | 3 | ctx + deliv：`内容/测试点（VC-004）/完成判据` |
| `.agenticdoc/mw-target-partition/tasks/T-09-BUNDLE-REBUILD.md` | 621 | 2 | 只有 `基本信息/描述`（最小卡，无要求无交付节） |
| `.agenticdoc/mw-ue-toolchain/tasks/T1-mw-common-helpers.md` | 521 | 0 | 三槽全缺（H2=0，键值 bullet 体裁） |
| `.agenticdoc/mw-l3-fail-marker-forms/tasks/T-00-baseline-sync.md` | 929 | 0 | 三槽全缺（H2=0） |
| `.agenticdoc/mw-autopilot-verify-cli/tasks/T-03-mw-common-surface.md` | 2195 | 2 | ctx + deliv：只有 `契约（plan.md §2.1/§2.2）/验证` |

注意第 7 行：`T-00-baseline-sync.md` 是 T2 宽口径下唯一 `ctx/req/deliv` 全 0 的卡（`scan4-report.txt` 矩阵 C 的 `ctx=0 req=0 deliv=0 = 1`）。

## 5. `type:` 头实况

### 5.1 命令与原始输出

用**真模块**判定（`packages/coding-agent/src/extensions/agent-team-loop/shared/task-frontmatter.ts`，零 import 纯函数），经 `node_modules\.bin\tsx.cmd` 直跑：

```powershell
.\node_modules\.bin\tsx.cmd ".agenticdoc\mw-dispatch-card-gate\workers\mwd-rq2-card-corpus\typecheck2.mts"
```

```
tasks n=345 typeDist={"undefined":345} srcDist={"missing":339,"body":6}
workers n=342 typeDist={"review":28,"coding":219,"research":93,"undefined":1,"vision":1} srcDist={"header":341,"missing":1}
```

### 5.2 结论：`tasks/*.md` 里 `type:` 头为 0

**345 张正式卡一张都没有 `type:` 头**（`source=missing` 339 张）。其余 6 张是**body 里的 `type:` 行**，且取值是旧的角色词表以外的历史值：

```
.agenticdoc/agent-team-loop/tasks/T-01-task-protocol.md    line 3  value=design/synthesis   region={startLine:0,endLine:0}
.agenticdoc/agent-team-loop/tasks/T-02-dispatch-table.md   line 3  value=design/synthesis   region={startLine:0,endLine:0}
.agenticdoc/agent-team-loop/tasks/T-03-proxy-multi.md      line 3  value=code-gen/impl      region={startLine:0,endLine:0}
.agenticdoc/agent-team-loop/tasks/T-04-worker-mode-ts.md   line 3  value=code-gen/impl      region={startLine:0,endLine:0}
.agenticdoc/agent-team-loop/tasks/T-05-launcher.md         line 3  value=code-gen/impl      region={startLine:0,endLine:0}
.agenticdoc/agent-team-loop/tasks/T-06-smoke-test.md       line 3  value=test-gen/debug     region={startLine:0,endLine:0}
```

即 `readTaskType` 对这 6 张返回 `type=undefined, source="body"` —— **与模块头部注释的 spec F-10 一致（body 值永不返回）**；它们是 2026-08 的旧模板，line 1 是 H1 标题、line 2 空行，故 header 区 = 第 1 行，`type:` 落在 body。

`Select-String` 交叉验证（同一结论）：

```powershell
(Select-String -Path ".agenticdoc\*\tasks\*.md" -Pattern '^type:' -Encoding UTF8 | Measure-Object).Count
# -> 6
```

### 5.3 对照：真正的派发卡在 `workers/*/task.md`，那里 `type:` 头是标配

`.agenticdoc/*/workers/*/task.md` 共 **342** 张：`header` 341、`missing` 1；取值分布 `coding 219 / research 93 / review 28 / vision 1`。唯一 `missing` 是
`.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md`（`region={startLine:0,endLine:0}`，既无 `type:` 行也无 body `type:`）。

### 5.4 抽样验证（人工核对首行 vs `readTaskType` 判定）

| 卡 | 首行（原文） | header 区 | `readTaskType` |
|---|---|---|---|
| `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-t16-docs-closure/task.md` | `type: coding` / `phase: EXECUTE` / `images: no` / 空行 | `{startLine:0,endLine:2,fenced:false}` | `type=coding, source=header` ✅ |
| `.agenticdoc/mw-dispatch-settle-gates/workers/mds-t05-output-sections/task.md` | `type: coding` / `phase: EXECUTE` / 空行 | `{startLine:0,endLine:1}` | `type=coding, source=header` ✅ |
| `.agenticdoc/mw-l3-fail-marker-forms/workers/fmr-rq1-code-facts/task.md` | `type: research` / 空行 | `{startLine:0,endLine:0}` | `type=research, source=header` ✅ |
| `.agenticdoc/mw-rag-window-parity/workers/mw-rwp-t5-verify-delta/task.md` | `type: coding` / 空行 | `{startLine:0,endLine:0}` | `type=coding, source=header` ✅ |
| `.agenticdoc/mw-dispatch-flow-fixes/workers/smoke-ac016b/task.md` | 无 `type:` | `{startLine:0,endLine:0}` | `type=undefined, source=missing` ✅ |
| `.agenticdoc/agent-team-loop/tasks/T-01-task-protocol.md` | `# T-01: task-protocol.md（L2 协议文档）` + `Design/Synthesis Task` + 空行 + `type: design/synthesis` | `{startLine:0,endLine:0}` | `type=undefined, source=body` ✅ |

**BOM 交叉验证（强证据）**：模块注释称"7 historical task.md files carry one"。实测 `workers/*/task.md` 语料 BOM=true 恰好 **7** 张（`_scratch/workers/mw-dr-autodispatch`、`mw-dispatch-flow-fixes/workers/smoke-ac015-ac016`、`mw-dispatch-reliability/workers/mw-dr-*` 5 张），而 `tasks/*.md` 另有 15 张带 BOM。数量与注释吻合，说明 tsx 跑的是同一份单源实现、判定可信。

## 6. 未验证怀疑清单

1. **标题族归属是启发式**：714 个不同标题里 342 个（H2+非空）被判族，`other` 族（`scan4-variants.txt` 中 family=other）逐个未经人工复核；`occ==1` 的长尾里存在明显误判（如 `1) 零回归（记原始输出/exit code）` 被判 deliv、`1. 逐 VC 证据链` 被判 deliv）。矩阵 A/B/C 的 ±2% 量级误差应视为未定。
2. **`状态与证据`（77 张卡）的归属未决**：本报告按前缀把它判为 meta（记录区）。若门禁把它算作交付物槽，deliv=yes 会从 223 升到 ~300，T1e 合规数会显著上升。该二选一必须在 SPEC 定死，本报告不给结论。
3. **`workers/*/task.md`（342 张，真正的派发输入）没有做三段结构分析**：只跑了 `type:` 判定。若把三段契约直接套到它们身上，通过率未知 —— 这是本 key 最该补的下一步实测（同一脚本改 glob 即可）。
4. **段落语义层的阈值未标定**：`AC-\d+/VC-\d+`、`report.md`、以及"键值 bullet 键名"三组兜底规则的召回/精确率没有 ground truth，T2 的 20.9% 不合规里混有"其实写了但没被识别"的卡。
5. **体裁边界是政策问题不是技术问题**：59 张卡（H2<=2，其中 17 张 H2=0）是结案记录卡而非作业书。门禁是否该管它们，本报告只给了证据（3.3 节），未给裁决。
6. **`目标/描述/输入` 是否等价于"上下文"未证实**：这三个标题在 agent-team-loop / goal-autopilot 模板里同时承载"做什么"和"为什么"，把它们并入 ctx 槽（矩阵 B）会让 ctx 命中率从 16.5% 跳到 78.3%，这个跳变是语义含混造成的，不是覆盖率提升。
7. **BOM 与编码未做门禁影响评估**：`tasks/*.md` 15 张带 BOM（如 `mw-dispatch-reliability/tasks/T-01..` 系列）。BOM 会不会破坏卡片头区解析之外的消费面（PM 派发、goal 对齐），本报告未测。
8. **非 UTF-8 字节未清点**：脚本用 `errors="replace"` 解码，未统计替换字符数量；若有 GBK 残留会静默降级，未验证。
9. **`_index.parallel` / `phase` 头与卡片三段的关系未测**：本轮只回答"卡片本身"，未看 key 级索引是否重复承载了上下文/要求信息。

## 附录

### 附录 A：全量语料清点表（345 行）

列：key | 文件 | 字节 | ctx(背景族) | ctx-intent(目标/描述/输入) | req | deliv | ctx-sem | req-sem | deliv-sem

```
key                                  file                                      bytes  ctx ctxI  req  del  csem rsem dsem
--------------------------------------------------------------------------------------------------------------------------
agent-team-loop                      T-01-file-lock.md                          1860   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-01-task-protocol.md                       911   -   Y    Y    Y    -    Y    Y
agent-team-loop                      T-02-dispatch-table.md                      835   -   Y    Y    Y    -    Y    -
agent-team-loop                      T-02-worker-store-index-store.md           2516   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-03-launcher-core.md                      3541   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-03-proxy-multi.md                        1423   -   Y    Y    Y    -    Y    -
agent-team-loop                      T-04-launcher-advanced.md                  2668   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-04-worker-mode-ts.md                     1418   -   Y    Y    Y    -    Y    Y
agent-team-loop                      T-05-launcher.md                           1346   -   Y    Y    Y    -    Y    -
agent-team-loop                      T-05-proxy-multi.md                        1840   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-06-mw-serve.md                           1996   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-06-smoke-test.md                          899   -   Y    Y    Y    -    Y    -
agent-team-loop                      T-07-worker-mode.md                        2600   -   Y    -    Y    Y    Y    Y
agent-team-loop                      T-08-phase-runner.md                       1973   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-09-output-writer.md                      2209   -   Y    -    Y    Y    Y    Y
agent-team-loop                      T-10-extension-index.md                    1753   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-11-state-manager-dispatcher.md           2007   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-12-goal-reader.md                        1822   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-13-pm-orchestrator-ui-bridge.md          2507   -   Y    -    Y    Y    Y    Y
agent-team-loop                      T-14-mw-init.md                            2293   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-15-extension-build.md                    2026   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-16-smoke-test.md                         1739   -   Y    -    Y    Y    Y    -
agent-team-loop                      T-17-dispatch-table-l0l1.md                2232   -   Y    -    Y    Y    Y    Y
ai-baseline-repair                   T-01-src-and-type-fixes.md                 1191   -   Y    Y    -    -    Y    Y
ai-baseline-repair                   T-02-model-id-remap.md                     2075   -   Y    Y    -    -    Y    -
ai-baseline-repair                   T-03-cross-api-types.md                    1243   -   Y    Y    -    -    Y    -
ai-baseline-repair                   T-04-verify-and-prevention.md              1540   -   Y    Y    -    -    Y    Y
ai-baseline-repair                   T-05-attribution.md                        1671   -   Y    Y    -    -    Y    Y
autopilot-monitor                    T-01-monitor-module.md                     9179   Y   Y    Y    Y    Y    Y    Y
autopilot-monitor                    T-02-verification.md                       3345   -   Y    Y    Y    -    Y    Y
goal-autopilot                       T-01-baseline-freeze.md                    4459   -   Y    -    Y    Y    Y    Y
goal-autopilot                       T-02-config-advance.md                     4794   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-03-roadmap-check.md                      3954   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-04-timeline.md                           4448   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-05-gates.md                              4427   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-06-dispatch.md                           4924   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-07-state-derive.md                       5590   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-08-audit-evidence.md                     7028   -   Y    -    Y    Y    Y    Y
goal-autopilot                       T-09-conductor-skeleton-serve.md           6701   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-10-per-key-phase-machine.md              8010   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-11-stage-gate-lifecycle.md               8661   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-12-execute-l3-done.md                    8712   -   Y    -    Y    Y    Y    Y
goal-autopilot                       T-13-worker-read-scope.md                  5824   -   Y    -    Y    -    Y    Y
goal-autopilot                       T-14-worker-protocol-increment.md          9052   -   Y    -    Y    Y    Y    Y
goal-autopilot                       T-15-autopilot-console.md                  7877   -   Y    -    Y    Y    Y    -
goal-autopilot                       T-16-l2-e2e.md                             7887   -   Y    -    Y    -    Y    Y
goal-autopilot                       T-17-l0-static-parity.md                   5684   -   Y    -    Y    -    Y    Y
goal-autopilot                       T-18-final-wrap-up.md                      8021   -   Y    -    Y    -    Y    Y
mw-autopilot-advance-root            T1-framework-root.md                        924   -   Y    Y    Y    -    Y    -
mw-autopilot-advance-root            T2-detect-root.md                           755   -   Y    Y    Y    -    Y    -
mw-autopilot-advance-root            T3-sync-push.md                             695   -   Y    Y    Y    -    Y    -
mw-autopilot-advance-root            T4-mw-advance.md                            850   -   Y    -    Y    -    Y    -
mw-autopilot-advance-root            T5-pi-utf8.md                               379   -   Y    -    Y    -    Y    -
mw-autopilot-advance-root            T6-e2e-regression.md                        766   -   Y    -    Y    -    Y    Y
mw-autopilot-slot-capacity           T-01-conductor-guards.md                   3064   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-02-ts-event-parity.md                    2444   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-03-gate-schema-v2.md                     2874   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-04-idle-heartbeat.md                     2527   -   Y    Y    Y    Y    Y    Y
mw-autopilot-slot-capacity           T-05-consumption-carrier.md                2391   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-06-evidence-provenance.md                2527   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-07-auto-decision-core.md                 5748   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-08-pending-review.md                     5623   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-09-ts-presentation.md                    2997   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-10-guard-coverage.md                     2072   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-11-parity-corpus.md                      2744   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-12-attribution-timeout.md                2441   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-13-doctor-cli.md                         2793   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-14-docs-dist-regression.md               1995   -   Y    Y    Y    -    -    Y
mw-autopilot-slot-capacity           T-15-count-locks.md                        3278   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-16-attribution-delegation.md             3783   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-17-ts-count-locks.md                     2675   -   Y    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-18-gate-default-bypass.md                3431   Y   -    Y    Y    Y    Y    Y
mw-autopilot-slot-capacity           T-19-case2-producer.md                     4776   Y   -    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-20-reason-code-scope.md                  6146   Y   -    Y    Y    Y    Y    Y
mw-autopilot-slot-capacity           T-21-defer-ledger.md                       6367   Y   -    Y    Y    Y    Y    Y
mw-autopilot-slot-capacity           T-22-evidence-line-audit.md                3693   Y   -    Y    Y    Y    Y    Y
mw-autopilot-slot-capacity           T-23-status-parity-lock.md                 4458   Y   -    Y    Y    -    Y    Y
mw-autopilot-slot-capacity           T-24-crosskey-prose.md                     5798   Y   -    Y    Y    Y    Y    Y
mw-autopilot-stall-feedback          T-01-e2feature-site-repair.md              1563   -   Y    Y    -    Y    Y    -
mw-autopilot-stall-feedback          T-02-advance-failure-classify.md           2154   -   Y    Y    -    -    Y    Y
mw-autopilot-stall-feedback          T-03-advance-stall-freeze.md               2287   -   Y    Y    -    Y    Y    -
mw-autopilot-stall-feedback          T-04-stalled-approve-resume.md             2679   -   Y    Y    -    -    Y    Y
mw-autopilot-stall-feedback          T-05-l3-no-verdict.md                      2103   -   Y    Y    -    Y    Y    Y
mw-autopilot-stall-feedback          T-06-monitor-autopilot-panel.md            2872   -   Y    Y    -    -    Y    Y
mw-autopilot-stall-feedback          T-07-monitor-autoshow.md                   2398   -   Y    Y    -    -    Y    Y
mw-autopilot-stall-feedback          T-08-docs-changelog-pitfalls.md            1887   -   Y    Y    -    -    Y    Y
mw-autopilot-stall-feedback          T-09-live-recovery-evidence.md             3404   -   Y    Y    -    -    Y    Y
mw-autopilot-verify-cli              T-01-config-basics.md                      2100   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-02-effective-config.md                   2494   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-03-mw-common-surface.md                  2195   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-04-ts-mirror-lock.md                     1941   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-05-mw-cli.md                             1980   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-06-conductor-root-anchor.md              1948   -   -    Y    -    Y    Y    -
mw-autopilot-verify-cli              T-07-crosslang-parity.md                   2062   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-08-update-env-recurrence.md              2078   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-09-cwd-placeholder-table.md              1332   -   -    Y    -    -    Y    -
mw-autopilot-verify-cli              T-10-docs-dist-regression.md               1421   -   -    Y    -    -    Y    -
mw-crosskey-risk-escalation          T-1-CROSSKEY-ESCALATION.md                 4671   -   Y    Y    Y    Y    Y    Y
mw-crosskey-risk-escalation          T-3-VERIFY.md                              3111   -   Y    Y    Y    -    Y    Y
mw-dispatch-flow-fixes               T-01-index-store-latest-active.md          2314   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-02-owner-resolve-sync.md                 2684   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-03-update-index-claim-demote.md          2562   -   Y    -    Y    Y    Y    Y
mw-dispatch-flow-fixes               T-04-heartbeat-writer.md                   2883   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-05-heartbeat-consumers.md                2460   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-06-route-default-pi.md                   2613   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-07-gate-scope.md                         2862   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-08-doctor-liveness.md                    2557   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-09-doctor-ui-summary.md                  1888   -   Y    -    Y    Y    Y    -
mw-dispatch-flow-fixes               T-10-regression.md                         2780   -   Y    -    Y    Y    Y    Y
mw-dispatch-flow-fixes               T-11-l2-rerun.md                           3850   -   Y    -    Y    Y    Y    Y
mw-dispatch-flow-fixes               T-12-review-fixes.md                       2647   -   Y    Y    -    -    Y    -
mw-dispatch-flow-fixes               T-13-claim-protocol.md                     1823   -   Y    Y    -    -    Y    -
mw-dispatch-flow-fixes               T-14-terminal-readback.md                  1587   Y   -    Y    -    Y    Y    Y
mw-dispatch-reliability              T-01-mw-common-credentials.md              2555   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-02-mw-common-precheck-archive.md         2393   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-03-launcher-isolation.md                 2299   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-04-launcher-stale-scan.md                1722   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-05-launcher-hermetic.md                  2431   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-06-serve-precheck-gate.md                2229   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-07-doctor-core.md                        2809   -   Y    -    Y    Y    Y    -
mw-dispatch-reliability              T-08-ts-stable-start.md                    1963   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-09-ts-mw-doctor.md                       1882   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-10-vitest-absorb.md                      2138   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-11-integration-framework.md              2922   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-12-integration-scenarios.md              2389   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-13-smoke-fix.md                          1664   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-14-e2e-real.md                           2101   -   Y    -    Y    Y    Y    Y
mw-dispatch-reliability              T-15-live-fix-regression.md                2452   -   Y    -    Y    Y    Y    Y
mw-dispatch-role-escape              T-01-ts-dispatch-gate.md                   1916   -   -    Y    -    -    Y    -
mw-dispatch-role-escape              T-02-python-launcher-override-log.md       1126   -   -    Y    -    -    Y    -
mw-dispatch-role-escape              T-03-docs-dist-smoke.md                    1208   -   -    Y    -    -    Y    Y
mw-dispatch-settle-gates             T-01-worker-crosskey-guard.md              3686   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-02-dispatch-satisfiability.md            4747   -   -    Y    Y    -    Y    Y
mw-dispatch-settle-gates             T-03-bash-write-scope.md                   4614   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-04-deliverable-gate.md                   4515   -   -    Y    Y    -    Y    Y
mw-dispatch-settle-gates             T-05-output-sections.md                    3908   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-06-output-informativeness.md             3689   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-07-reap-productfirst.md                  3424   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-08-doctor-blocked-on-human.md            3526   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-09-gate-stage-terminal.md                4043   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-10-dispatch-run-state.md                 3448   Y   -    Y    Y    Y    Y    Y
mw-dispatch-settle-gates             T-11-docs-errata.md                        3542   -   -    Y    Y    -    Y    Y
mw-dispatch-settle-gates             T-12-consolidation.md                      3658   -   -    Y    Y    -    Y    Y
mw-done-closure-repair               T-00-baseline-sync.md                      1807   -   Y    Y    -    -    -    Y
mw-done-closure-repair               T-01-prefix-e2e-evidence.md                1682   -   Y    Y    -    Y    Y    Y
mw-done-closure-repair               T-02-closure-module.md                     3555   -   Y    Y    -    -    Y    -
mw-done-closure-repair               T-03-return-tuple.md                       1634   -   Y    Y    -    -    Y    -
mw-done-closure-repair               T-04-marker-guard.md                       2235   -   Y    Y    -    Y    Y    Y
mw-done-closure-repair               T-05-reprompt-branch.md                    2298   -   Y    Y    -    -    Y    -
mw-done-closure-repair               T-06-l2-tests-a.md                         1863   -   Y    Y    -    -    Y    Y
mw-done-closure-repair               T-07-l2-tests-b.md                         1413   -   Y    Y    -    -    Y    -
mw-done-closure-repair               T-08-l2-tests-c.md                         1050   -   Y    Y    -    -    Y    -
mw-done-closure-repair               T-09-e2e-postfix.md                        1465   -   Y    Y    -    Y    Y    Y
mw-done-closure-repair               T-10-gitignore-docs.md                     1027   -   Y    Y    -    -    -    -
mw-dual-workspace                    001-ts-target-config.md                    2580   -   -    Y    Y    Y    Y    Y
mw-dual-workspace                    002-py-target-config-parity.md             1832   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    003-mw-target-cli-doctor.md                2125   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    004-read-scope-deny.md                     2527   -   -    Y    Y    Y    Y    Y
mw-dual-workspace                    005-worker-dual-root.md                    2114   -   -    Y    Y    Y    Y    Y
mw-dual-workspace                    006-dispatch-injection.md                  2109   -   -    Y    Y    Y    Y    Y
mw-dual-workspace                    007-profile-rendering.md                   1803   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    008-cross-drive-pollution.md               1649   -   -    Y    Y    Y    Y    Y
mw-dual-workspace                    009-goal-serve-staleness-dual.md           1344   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    010-serve-root-binding.md                  1352   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    011-regression-baseline.md                 1298   -   -    Y    Y    -    Y    Y
mw-dual-workspace                    012-changelog-wrapup.md                    1493   -   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-01-l3-aborted.md                         3346   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-02-config-keys.md                        2869   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-03-event-names.md                        2280   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-04-contract-guard.md                     5011   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-05-ts-mirror.md                          2717   -   Y    Y    Y    Y    Y    Y
mw-gate-verdict-hardening            T-06-l3-tests.md                           2790   -   Y    Y    Y    Y    Y    Y
mw-gate-verdict-hardening            T-07-gate-reminder.md                      3412   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-08-g2-surfaces.md                        2863   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-09-pm-consumer.md                        2710   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-10-g3-done-guard.md                      3371   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-11-g3-cli-doctor.md                      3080   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-12-g3-writer-g4-rearm.md                 4154   -   Y    Y    Y    Y    Y    Y
mw-gate-verdict-hardening            T-13-g4-freshness.md                       3226   -   Y    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-14-count-locks.md                        7733   -   Y    Y    Y    Y    Y    Y
mw-gate-verdict-hardening            T-15-no-silent-row-drop.md                 3347   Y   -    Y    Y    Y    Y    Y
mw-gate-verdict-hardening            T-16-docs-dist.md                         11338   -   Y    Y    Y    Y    -    Y
mw-gate-verdict-hardening            T-17-dispatch-failclosed-quota.md          3392   Y   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-18-launcher-bounded-doctor.md            6430   Y   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-19-dispatch-scope-layering.md            4133   Y   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-20-run-identity-state.md                 6590   Y   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-21-g5g6-tests.md                         6072   -   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-22-crosskey-readonly.md                  5310   Y   -    Y    Y    -    Y    Y
mw-gate-verdict-hardening            T-23-g3-anchor.md                          7107   -   Y    Y    Y    -    Y    Y
mw-guard-form-hardening              T-01-form-inventory.md                     2782   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-02-verbatim-contract.md                  3496   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-03-audit-and-alarm.md                    2307   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-04-shape-judge.md                        2677   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-05-fixture-and-corpus.md                 2808   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-06-task-frontmatter.md                   2209   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-07-parser-single-source.md               3702   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-08-python-parity.md                      2813   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-09-key-identity.md                       2639   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-10-branch-coverage.md                    3391   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-11-assertion-quality.md                  2044   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-12-contract-and-docs.md                  2631   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-13-evidence-anchoring.md                 5071   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-14-python-callsite-wiring.md             4229   Y   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-15-python-claim-narrowing.md             4712   Y   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-16-claim-family-gate-and-case-audit.md   4747   Y   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-17-repair-and-reanchor.md                7018   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-18-exe-wrapper-and-vc-labels.md          4615   -   -    Y    Y    Y    Y    Y
mw-guard-form-hardening              T-19-residual-fixes.md                     4469   -   -    Y    Y    Y    Y    Y
mw-implementation-gate               T1-t2-gate-module.md                        970   -   -    -    -    Y    Y    Y
mw-implementation-gate               T3-gate-tests.md                           1354   -   -    -    -    Y    Y    Y
mw-implementation-gate               T4-skill-trigger-words.md                   749   -   -    -    -    Y    Y    Y
mw-implementation-gate               T5-t6-pm-closeout.md                        759   -   -    -    -    Y    Y    Y
mw-l3-fail-marker-forms              T-00-baseline-sync.md                       929   -   -    -    -    -    -    -
mw-l3-fail-marker-forms              T-01-l1-truth-table.md                     2974   -   -    -    -    -    Y    Y
mw-l3-fail-marker-forms              T-02-conductor-impl.md                     2929   -   -    -    -    -    Y    -
mw-l3-fail-marker-forms              T-03-l2-scenarios.md                        889   -   -    -    -    -    -    Y
mw-l3-fail-marker-forms              T-04-e2e-stub.md                           1065   -   -    -    -    -    Y    Y
mw-l3-fail-marker-forms              T-05-regression.md                          842   -   -    -    -    -    Y    Y
mw-l3-fail-marker-forms              T-06-docs.md                               1004   -   -    -    -    -    Y    -
mw-parallel-protocol                 T-01-parallel-protocol.md                  1969   -   Y    Y    Y    -    Y    -
mw-partition-parent-extended         T-01-PY-EXPAND.md                          2069   -   Y    Y    -    -    Y    Y
mw-partition-parent-extended         T-02-TS-UNION.md                           3587   -   Y    Y    -    -    Y    -
mw-partition-parent-extended         T-03-LABEL-WORDING.md                      2516   -   Y    Y    -    -    Y    Y
mw-partition-parent-extended         T-04-VERIFY-BASELINE.md                    1824   -   Y    Y    -    -    Y    Y
mw-provider-routing                  T1-providers-prefix.md                      852   -   -    Y    -    -    Y    -
mw-provider-routing                  T2-launcher-branch.md                      1411   -   -    Y    -    -    Y    -
mw-provider-routing                  T3-serve-no-proxy.md                        534   -   -    Y    -    -    Y    -
mw-provider-routing                  T4-ts-map-bundle.md                         745   -   -    Y    -    -    Y    -
mw-provider-routing                  T5-e2e-smoke.md                             746   -   -    Y    -    -    Y    Y
mw-provider-routing                  T6-finalize.md                              966   -   -    Y    -    Y    Y    -
mw-rag-config-guide                  T-21-RAG-INIT.md                           8493   Y   -    Y    -    Y    Y    -
mw-rag-config-guide                  T-22-RAG-MANUAL.md                         7301   -   -    Y    Y    -    Y    -
mw-rag-config-guide                  T-23-VERIFY.md                             5548   -   -    Y    Y    Y    Y    Y
mw-rag-integration-fix               T-15-ROLE-DEFAULTS.md                      7449   Y   -    Y    Y    Y    Y    -
mw-rag-integration-fix               T-16-PY-ROLE-UNREACHABLE.md                4375   Y   -    Y    -    Y    Y    -
mw-rag-integration-fix               T-17-DOCS-BUNDLE.md                        6799   Y   -    Y    -    Y    Y    Y
mw-rag-integration-fix               T-18-VERIFY.md                             5212   Y   -    Y    -    Y    Y    Y
mw-rag-integration-fix               T-19-DEFAULTS-PARITY.md                    6723   Y   -    Y    -    Y    Y    -
mw-rag-integration                   T-01-TS-CONFIG.md                          8475   -   Y    Y    -    Y    Y    Y
mw-rag-integration                   T-02-ADAPTER.md                            6629   -   Y    Y    -    Y    Y    -
mw-rag-integration                   T-03-TRANSPORT.md                          5660   -   Y    Y    -    -    Y    -
mw-rag-integration                   T-04-TOOLS.md                              8324   -   Y    Y    -    Y    Y    Y
mw-rag-integration                   T-05-EVIDENCE.md                           8735   -   Y    Y    -    -    Y    Y
mw-rag-integration                   T-06-PY-CONFIG.md                          5311   -   Y    Y    -    -    Y    -
mw-rag-integration                   T-07-PY-INJECT.md                          4910   -   Y    Y    -    -    Y    -
mw-rag-integration                   T-08-PY-CLI.md                             5104   -   Y    Y    -    -    Y    -
mw-rag-integration                   T-09-RAG-RESEARCH.md                       5984   -   Y    Y    -    Y    Y    Y
mw-rag-integration                   T-10-REQUIRE-AUDIT.md                      5780   -   Y    Y    -    -    Y    Y
mw-rag-integration                   T-11-VERIFY.md                             9002   -   Y    Y    -    Y    Y    Y
mw-rag-integration                   T-12-PARITY-LOCK.md                        6226   -   Y    Y    -    -    Y    Y
mw-rag-integration                   T-13-MCP-TOOLMAP.md                        6183   Y   -    Y    -    Y    Y    Y
mw-rag-integration                   T-14-PHASE-AXIS.md                         6222   Y   -    Y    -    Y    Y    Y
mw-rag-window-parity                 T-1-SKILL-DIR-PARITY.md                    3813   Y   -    Y    Y    Y    Y    -
mw-rag-window-parity                 T-2-MW-RAG-CMD.md                          4430   Y   -    Y    Y    Y    Y    -
mw-rag-window-parity                 T-3-DOCTOR-RAG-ROW.md                      3925   Y   -    Y    Y    Y    Y    -
mw-rag-window-parity                 T-4-VERIFY.md                              4695   -   -    Y    Y    Y    Y    Y
mw-rag-window-parity                 T-5-VERIFY-DELTA.md                        4805   Y   -    Y    Y    Y    Y    Y
mw-target-partition                  T-00-BASELINE-GOLDEN.md                     921   -   Y    -    -    -    Y    Y
mw-target-partition                  T-01-PY-PARSE.md                            932   -   Y    -    -    -    Y    Y
mw-target-partition                  T-02-TS-PARSE.md                            790   -   Y    -    -    -    Y    Y
mw-target-partition                  T-03-PARITY-FIXTURES.md                     978   -   Y    -    -    -    Y    Y
mw-target-partition                  T-04-PROFILE-INJECTION.md                   912   -   Y    -    -    -    Y    Y
mw-target-partition                  T-05-LAUNCHER-SCOPE.md                      969   -   Y    -    -    -    Y    Y
mw-target-partition                  T-06-DOCTOR-CACHE.md                        849   -   Y    -    -    -    Y    Y
mw-target-partition                  T-07-PY-CLI.md                              978   -   Y    -    -    -    Y    Y
mw-target-partition                  T-08-TS-FORWARD.md                          808   -   Y    -    -    -    Y    Y
mw-target-partition                  T-09-BUNDLE-REBUILD.md                      621   -   Y    -    -    -    -    Y
mw-target-partition                  T-10-FULL-REGRESSION.md                     808   -   Y    -    -    -    Y    Y
mw-target-partition                  T-11-CHECK-EVIDENCE.md                      681   -   Y    -    -    -    Y    Y
mw-task-scope-isolation              T-01-list-tasks-scope.md                   1587   -   Y    Y    -    -    Y    -
mw-task-scope-isolation              T-02-ack-scope.md                          1242   -   Y    Y    -    -    Y    -
mw-task-scope-isolation              T-03-regression-changelog.md               1331   -   Y    Y    -    -    Y    -
mw-ue-toolchain                      T1-mw-common-helpers.md                     521   -   -    -    -    -    -    Y
mw-ue-toolchain                      T2-mw-cli.md                                742   -   -    -    -    -    -    Y
mw-ue-toolchain                      T3-tests.md                                 834   -   -    -    -    -    -    Y
mw-ue-toolchain                      T4-docs.md                                  721   -   -    -    -    -    -    Y
mw-ue-toolchain                      T5-scope-and-rename.md                     1016   -   -    -    -    -    -    Y
mw-ue-toolchain                      T6-regression-and-backfill.md               860   -   -    -    -    -    -    Y
mw-vision-role                       T-01-python-role-type-registry.md          3307   Y   Y    Y    Y    -    Y    -
mw-vision-role                       T-02-ts-role-type-allowlist.md             2430   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-03-parity-refreeze.md                    2858   -   Y    Y    Y    Y    Y    -
mw-vision-role                       T-04-image-capability-fn.md                2853   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-05-images-header-write-side.md           2159   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-06-dispatch-capability-gate.md           3499   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-07-auto-route-model-only.md              4164   Y   Y    Y    Y    -    Y    Y
mw-vision-role                       T-08-python-render-images.md               2959   -   Y    Y    Y    Y    Y    -
mw-vision-role                       T-09-worker-image-cap-backstop.md          3382   -   Y    Y    Y    -    Y    Y
mw-vision-role                       T-10-python-model-probe.md                 3567   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-11-model-set-capability-refusal.md       2816   -   Y    Y    Y    -    Y    -
mw-vision-role                       T-12-capability-visibility.md              3278   -   -    Y    Y    -    Y    -
mw-vision-role                       T-13-pm-awareness-texts.md                 2811   Y   -    Y    Y    Y    Y    -
mw-vision-role                       T-14-verification-closeout.md              4568   -   Y    Y    Y    -    Y    Y
mw-vision-role                       T-15-doctor-suggestion-vision-scoped.md    3942   Y   -    Y    Y    Y    Y    -
mw-vision-role                       T-16-quality-gate-review.md                4899   -   -    Y    Y    Y    Y    Y
mw-vision-role                       T-17-fix-description-optional.md           3875   Y   -    Y    Y    Y    Y    -
mw-vision-role                       T-18-vc003-vc007-evidence.md               4321   Y   -    Y    Y    Y    Y    Y
mw-vision-role                       T-19-evidence-refresh.md                   4838   Y   -    Y    -    Y    Y    Y
mw-widget-terminal-lifecycle         T-01-ack-store.md                          3971   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-02-mw-common-evidence.md                 4993   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-03-tldr-normalization.md                 4846   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-04-starter-conclusion.md                 3025   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-05-terminal-detail.md                    4227   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-06-widget-sections.md                    4158   -   Y    -    Y    Y    Y    -
mw-widget-terminal-lifecycle         T-07-ack-channels.md                       4653   -   Y    -    Y    Y    Y    -
mw-widget-terminal-lifecycle         T-08-reconcile.md                          6628   -   Y    -    Y    Y    Y    Y
mw-widget-terminal-lifecycle         T-09-regression.md                         3427   -   Y    -    Y    Y    Y    Y
mw-worker-progress-persist           T-1-PROGRESS-WRITER.md                     3345   Y   -    Y    Y    Y    Y    Y
mw-worker-progress-persist           T-2-WORKER-FILE-TOOL.md                    6474   Y   -    Y    Y    Y    Y    Y
mw-worker-progress-persist           T-3-CHECKPOINT-WIRING.md                   9663   Y   -    Y    Y    Y    Y    Y
mw-worker-progress-persist           T-4-DOCS-CHANGELOG.md                      2271   Y   -    Y    Y    Y    Y    Y
mw-worker-progress-persist           T-5-BUILD-SMOKE.md                         4687   -   Y    Y    Y    Y    Y    Y
mw-worker-progress-persist           T-6-VERIFY.md                              4501   -   Y    -    Y    -    Y    Y
mw-worker-timeout-convergence        T-01-checkpoint-parse.md                    803   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-02-output-writer-ext.md                   778   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-03-worker-timers.md                      1033   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-04-pm-alert-path.md                       931   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-05-parsetaskmd-timeout.md                 764   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-06-vitest.md                              926   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-07-check-bundle.md                        930   -   Y    Y    -    -    Y    Y
mw-worker-timeout-convergence        T-08-smoke.md                               954   -   Y    Y    -    -    Y    Y
mw-worker-tree-kill                  T-01-WORKER-EXIT-KILL.md                   1521   -   Y    Y    -    -    Y    Y
mw-worker-tree-kill                  T-02-UNIT-TESTS.md                         1992   -   Y    Y    -    -    Y    Y
mw-worker-tree-kill                  T-03-LIVE-REGRESSION.md                    1588   -   Y    Y    -    -    Y    Y
mw-worker-visibility-gate            T-1-PHASE-DOCS-GATE.md                     4751   Y   -    Y    Y    Y    Y    Y
mw-worker-visibility-gate            T-2-PM-STATE-CLAIM-SYNC.md                 4421   Y   -    Y    Y    Y    Y    -
mw-worker-visibility-gate            T-3-WIRING.md                              9378   Y   -    Y    Y    Y    Y    Y
mw-worker-visibility-gate            T-4-DOCS-PITFALLS.md                       2385   -   -    Y    Y    -    Y    -
mw-worker-visibility-gate            T-5-VERIFY.md                              3891   -   Y    Y    Y    Y    Y    Y
mw-worker-visibility-gate            T-6-CLAIM-INSERT.md                        4839   Y   -    Y    Y    Y    Y    -
timi-gpt-pi-routing                  001-ts-cross-protocol-history.md           3242   -   Y    Y    Y    Y    Y    -
timi-gpt-pi-routing                  002-ts-retry-boundary.md                   3691   -   Y    Y    Y    Y    Y    -
timi-gpt-pi-routing                  003-ts-model-resolver-dispatch.md          3445   -   Y    Y    Y    Y    Y    -
timi-gpt-pi-routing                  004-py-launcher-routing.md                 4181   -   Y    Y    Y    Y    Y    -
timi-gpt-pi-routing                  005-py-remove-codex-7002.md                3356   -   Y    -    Y    Y    Y    -
timi-gpt-pi-routing                  006-py-mw-supervision.md                   6126   -   Y    Y    Y    Y    Y    -
timi-gpt-pi-routing                  007-build-verify.md                        3748   -   Y    -    Y    Y    Y    -
xkey-repair-mechanism                T-01-xkey-core-module.md                   4760   -   Y    Y    Y    -    Y    Y
xkey-repair-mechanism                T-02-l1-tests.md                           3339   -   Y    Y    -    -    Y    Y
xkey-repair-mechanism                T-03-conductor-mount.md                    4707   -   Y    Y    -    Y    Y    Y
xkey-repair-mechanism                T-04-ts-mirror-guard.md                    3161   -   Y    Y    -    -    Y    Y
xkey-repair-mechanism                T-04b-ts-config-mirror.md                  2407   Y   -    Y    -    Y    Y    Y
xkey-repair-mechanism                T-05-l2-e2e-replay.md                      3527   -   Y    Y    -    Y    Y    Y
xkey-repair-mechanism                T-06-apply-verify-close.md                 5067   Y   -    Y    -    Y    Y    Y
xkey-repair-mechanism                T-07-unskip-verified.md                    2201   Y   -    Y    -    Y    Y    Y
xkey-repair-mechanism                T-08-dispatch-proposal-worker.md           3723   Y   -    Y    -    Y    Y    Y

列说明: ctx=显式 背景/上下文/问题/现状/动机 族标题; ctxI=显式 目标/描述/输入/前置 族标题;
        req=显式要求族标题; del=显式交付族标题; csem/rsem/dsem=段落语义兜底命中。
        原始机器可读版本: .agenticdoc/mw-dispatch-card-gate/workers/mwd-rq2-card-corpus/scan4-cards.tsv
```

### 附录 B：全量标题变体频次表（H2+ 且正文非空）

```
== heading variant frequency (H2+, non-blank body) ==
occ  cards  family      pat              heading
 118    118  meta        基本信息             基本信息
 116    116  intent      描述               描述
  92     92  intent      输入               输入
  90     90  intent      目标               目标
  89     89  meta        执行记录             执行记录
  77     77  meta        状态               状态与证据
  77     77  deliv       预期产出             预期产出
  74     74  deliv       交付               交付物
  72     72  meta        卡住记录             卡住记录
  66     66  meta        Error Fingerprin Error Fingerprint
  47     47  req         \[VERIFY\]       [VERIFY]
  47     47  deliv       回执               回执
  43     43  req         步骤               步骤
  41     41  deliv       交付               交付
  40     40  req         契约               契约（不得重定义）
  35     35  meta        风险               风险与注意
  32     32  req         验证               验证
  29     29  req         必须               必须实现
  29     29  other                        非空洞对照（必须附在回执里）
  29     29  req         验收               验收命令
  26     26  req         验收               验收
  25     25  meta        元信息              元信息
  18     18  req         完成               完成判定
  18     18  constraint  禁止               禁止
  18     18  deliv       证据               证据
  18     18  other                        非空洞对照
  16     16  constraint  约束               约束
  16     16  deliv       证据               证据格式
  15     15  deliv       报告要求             报告要求
  15     15  meta        注意               注意
  13     13  meta        卡元信息             卡元信息
  13     13  constraint  源码               源码
  12     12  req         测试               测试
  11     11  constraint  依赖               依赖与阻塞
  11     11  req         契约               契约（逐字遵守）
  10     10  req         完成               完成判据
  10     10  req         对照               对照协议（`plan.md §5`）
  10     10  constraint  硬约束              硬约束
  10     10  ctx         背景               背景
  10     10  meta        设计取舍             设计取舍备注
  10     10  req         验证               验证方式（VC 断言）
   9      9  constraint  纪律               纪律
   8      8  req         AC               AC 摘录（spec.md §3）
   8      8  other                        非空洞对照（必须附）
   8      8  req         验证               验证（补记自质检报告）
   7      7  req         反向               反向用例（必须真跑并贴输出）
   7      7  req         契约               契约（冻结）
   7      7  ctx         背景               背景（实测）
   6      6  req         Acceptance       Acceptance Criteria
   6      6  intent      Description      Description
   6      6  constraint  Do NOT           Do NOT
   6      6  deliv       Expected Output  Expected Output
   6      6  constraint  Tool Constraints Tool Constraints
   6      6  req         内容               内容
   6      6  ctx         现状               现状（以符号名为准）
   6      6  ctx         问题               问题（实证）
   5      5  req         必须               必须做
   5      5  req         验证               验证状态
   4      4  constraint  约束               约束（worker 派发适用）
   3      3  req         反向               反向用例（必须真跑）
   3      3  req         契约               契约（plan.md §2.1/§2.2）
   3      3  req         实现               实现步骤
   3      3  req         实现               实现要点
   3      3  req         改动               改动点
   3      3  ctx         背景               背景（PM 实测，勿再声称未验证）
   2      2  intent      目标               1. 目标
   2      2  other                        3) 逐 VC 表
   2      2  constraint  纪律               D. 纪律
   2      2  req         验收               E. 验收命令（PM 执行）
   2      2  deliv       交付               F. 交付
   2      2  intent      前置               前置（R1 纪律）
   2      2  req         变更               变更
   2      2  req         契约               契约（design D-008）
   2      2  meta        实施记录             实施记录（2026-10-10，PM 直执，基线 `776b82d7f`）
   2      2  req         改动               改动
   2      2  req         改动               改动文件
   2      2  req         验收               验收命令（PM 执行）
   2      2  req         验收               验收（真实执行，贴原始输出）
   1      1  other                        (1) gate kind 闭集镜像（D-009）
   1      1  other                        (1) 合成 fixture 全链（VC-009）
   1      1  other                        (2) FM 语料 fixture 重放（VC-010）
   1      1  other                        (2) gate 目录写拦截（D-008 的"可观测拒绝"落点）
   1      1  other                        1) Python role 回落对齐（D-105）
   1      1  other                        1) TS：新增单一解析器 `resolveDefaults`（`rag/config.ts`）
   1      1  other                        1) VC-018 证据层级落定（D-107，二选一，必须落定）
   1      1  other                        1) 单一解析源：`renderRagBlock` 改用既有解析函数
   1      1  other                        1) 命令与实测
   1      1  other                        1) 基线与零回归
   1      1  other                        1) 新模块 `packages/multi-workers/rag_templates.py`
   1      1  other                        1) 落盘协议（防流中断）
   1      1  other                        1) 零回归（记原始输出/exit code）
   1      1  other                        1. AC/VC 覆盖矩阵（自算）
   1      1  other                        1. CHANGELOG（两包，**只在 `## [Unreleased]` 既有小节内追加**，不新建重复小节）
   1      1  other                        1. L0 静态扫描（VC-009）
   1      1  other                        1. 新文件 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
   1      1  other                        1. 逐 VC 证据链
   1      1  other                        2) F-2 的断言（TS 侧）
   1      1  other                        2) Python：rewrite 兜底对齐（`mw_common.py:866`）
   1      1  other                        2) README 用法段以 argparse 为唯一真源（D-108）
   1      1  other                        2) `mw.py`：`mw rag init`
   1      1  other                        2) 三条反例试验（**必须做**，逐条记录「改了什么 / 看到什么红 / 还原方式 / sha256 是否复原」）
   1      1  req         反例               2) 反例（**必须做**，逐条记录「改了什么 / 看到什么红 / 还原方式 / sha256 是否复原」）
   1      1  req         反例               2) 反例（逐条：改了什么 / 什么红 / 还原 / sha256 自检）
   1      1  other                        2) 命令与实测（逐条记录命令 + 结果，截图式粘贴关键行）
   1      1  constraint  角色               2) 角色回落统一为一份规则
   1      1  other                        2. CHANGELOG（coding-agent）
   1      1  deliv       交付               2. 交付物
   1      1  other                        2. 修改 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts`
   1      1  other                        2. 全量回归 + 基线对照（写进 `verify-closure.md`）
   1      1  other                        2. 全量测试与检查
   1      1  req         必须               2. 必须满足的契约
   1      1  other                        3) F-4 的两侧对照用例（VC-105）
   1      1  other                        3) R-6 实测（不得只复述我的说法）
   1      1  other                        3) `RagRuntime` 接 role/phase，`callRag` 应用默认
   1      1  other                        3) 删除死变量 `MW_RAG_ENABLED`（D-106）
   1      1  other                        3) 散文准确性抽查（**新增，重点**）
   1      1  req         测试               3) 测试 `packages/multi-workers/test_rag_init.py`
   1      1  other                        3) 跨语言对照 fixture（VC-111）
   1      1  req         VC               3. VC 复现要求
   1      1  other                        3. 修改面（零回归）审计
   1      1  other                        3. 文档同步（只做必要项，不做大改）
   1      1  other                        3. 新增用例（TDD：先红后绿）
   1      1  other                        3. 构建部署
   1      1  req         测试               3. 测试 `packages/coding-agent/test/suite/autopilot-monitor.test.ts`（新文件）
   1      1  other                        4) CHANGELOG 与 dist 重建（AC-107）
   1      1  req         实现               4) 实现/文档一致性抽查（≥6 条可证伪断言）
   1      1  other                        4) 归属与限制
   1      1  other                        4) 接线点（call site）
   1      1  other                        4) 逐 VC 表
   1      1  other                        4) 逐 VC 表（只覆盖本次 delta 涉及的）
   1      1  other                        4. L2 双 widget 验证（VC-010）
   1      1  other                        4. `runtime-cutover-runbook.md`（新文件；只写文档，不执行）
   1      1  other                        4. 变异反例（必须各做一次，结束时逐字节复原并给 sha256）
   1      1  other                        4. 文档与 CHANGELOG
   1      1  req         验收               4. 验收命令
   1      1  other                        5) 归属与限制
   1      1  other                        5) 未覆盖与限制
   1      1  other                        5) 补充实验（E-4，必做）
   1      1  deliv       证据               5) 证据（fixture 级，不是直调纯函数）
   1      1  other                        5. 回归
   1      1  other                        5. 结案材料
   1      1  intent      范围               5. 范围（禁止事项）
   1      1  deliv       证据               5. 证据落盘
   1      1  other                        6) 归属与限制
   1      1  deliv       交付               6. 交付
   1      1  other                        6. 结论
   1      1  intent      范围               6. 范围
   1      1  other                        A. C-15 / C-16：跨语言头区解析归一（AC-005 主轴）
   1      1  other                        A. VC-003（写入 `test_dispatch_models.py`，只追加）
   1      1  other                        A. `.exe` 包装器与 PowerShell 调用形态（**先实测再改码**）
   1      1  other                        A. 实测裁决（先跑，再决定改不改）
   1      1  other                        A. 门禁传相位（三处调用点）
   1      1  other                        A1（F-6，**已由 PM 读源确认，必修**）
   1      1  other                        A2（F-2，先实测）
   1      1  other                        A3（F-1，先实测）
   1      1  other                        A4（F-5，先实测）
   1      1  req         AC               AC 摘录（spec.md §3，AC-007 已修订为 target.yml 三配置节）
   1      1  req         AC               AC 映射
   1      1  other                        B. C-17：heredoc 体内的 `>` 不得当重定向（误拦）
   1      1  other                        B. VC-007（写入 `test/extensions/agent-team-loop-vision-gate.test.ts`，只追加）
   1      1  other                        B. 同族误拦（QG-B2 附带发现）
   1      1  deliv       证据               B. 证据链修复（QG-B）
   1      1  other                        B. 面板聚合行（`renderWatchLines`）
   1      1  other                        Build
   1      1  other                        C. C-18：`tar -c … -C <dir>` 的源/目标判定
   1      1  req         VC               C. VC 标签唯一性（AC-011 子判据，阻断 ①）
   1      1  other                        C. claim 同步调用点（`shared/pm-state-claim.ts` 由 T-2 提供）
   1      1  constraint  纪律               C. 纪律
   1      1  other                        D. 新测试（两个新文件，不碰既有测试文件）
   1      1  req         验收               D. 验收命令（PM 执行）
   1      1  deliv       交付               E. 交付
   1      1  other                        L0
   1      1  other                        L2
   1      1  meta        PM               PM 已备上下文
   1      1  meta        PM               PM 追记（2026-10-10 19:00，T-23 落地后必须一并刷新）
   1      1  meta        PM               PM 追记（2026-10-10 20:35，T-04 R1 的连带要求）
   1      1  meta        PM               PM 追记（2026-10-10 20:35，派发后）
   1      1  meta        PM               PM 验收备注（2026-09-10 13:30）
   1      1  meta        PM               PM 验收备注（2026-09-10 14:35）
   1      1  meta        PM               PM 验收备注（2026-09-10 15:35）
   1      1  meta        PM               PM 验收备注（2026-09-10 17:50）
   1      1  other                        Step 1: npm run check
   1      1  other                        Step 2: npm run build
   1      1  other                        Step 3: 验证 dist timi.json
   1      1  other                        Step 4: 验证 timi.js 含双 API
   1      1  other                        Step 5: 凭证扫描
   1      1  other                        Stop-request file helpers
   1      1  other                        T-06 交付接口（消费方须知，PM 于 T-06 回执后补）
   1      1  other                        [PM 追加 @ 2026-09-26] 时效类默认字段的物化（T-13 实测上报 + PM 复算确认）
   1      1  req         \[VERIFY\]       [VERIFY] 格式
   1      1  other                        _build_command 改造
   1      1  other                        _build_env 改造
   1      1  other                        _check_pid 改造
   1      1  other                        _is_alive_win32(pid) — Windows-only liveness
   1      1  other                        anthropic-messages.ts 修复
   1      1  other                        cmd_serve 改造
   1      1  other                        cmd_stop 改造
   1      1  other                        dispatch-table.md
   1      1  other                        launcher.py
   1      1  other                        model-resolver.test.ts 追加测试
   1      1  other                        model-resolver.ts
   1      1  other                        mw.py
   1      1  other                        openai-responses-shared.ts 修复
   1      1  other                        pm-orchestrator.ts
   1      1  other                        providers.json
   1      1  other                        proxy_multi.py
   1      1  other                        retry.ts 修改
   1      1  other                        smoke_test.sh
   1      1  other                        timi dispatch test (VC-002)
   1      1  other                        timi-responses.ts 修改
   1      1  other                        ⚠️ PM 决定（2026-10-10 19:10）：本卡**不重建 dist / 不跑 `npm run build` / 不做安装与重启**
   1      1  other                        与 Python 侧锁定的契约（T-06 已落地，必须对齐）
   1      1  req         任务               任务
   1      1  constraint  你的               你的角色
   1      1  other                        依据（T-06 已落地的事实，不得改写）
   1      1  other                        修改清单
   1      1  ctx         偏差               偏差（PM 在真实仓库上实测发现，非测试虚构）
   1      1  other                        入口与阶段（逐段实现，每步失败都不覆盖、不静默）
   1      1  meta        关联               关联
   1      1  req         判据               判据（追加到 `test_autopilot_pending_review.py`）
   1      1  intent      前置               前置
   1      1  ctx         卡缺陷更正            卡缺陷更正（2026-09-26 实测，语义不变）
   1      1  ctx         卡缺陷更正            卡缺陷更正（2026-09-26 实测，语义已回写 design.md §7 VC-017）
   1      1  req         反向               反向用例（必须真跑；语料回归是硬要求）
   1      1  req         反向               反向用例（本卡自身的对照）
   1      1  req         变更               变更（.agents/skills/agentic-task/scripts/update_index.py）
   1      1  other                        可达性判据（本卡的核心，必须端到端）
   1      1  req         契约               契约
   1      1  req         契约               契约与已知触点
   1      1  req         契约               契约（design D-009/D-010）
   1      1  req         契约               契约（design D-013，6 条判据）
   1      1  req         契约               契约（plan.md §2.1/§2.2，逐字遵守）
   1      1  req         契约               契约（plan.md §2.2/§4.2）
   1      1  req         契约               契约（改法）
   1      1  req         契约               契约（改法，已定）
   1      1  req         契约               契约（逐字遵守 `plan.md`「契约冻结」节的签名）
   1      1  req         契约               契约（逐字遵守，不得重定义）
   1      1  req         完成               完成判据（progress.md 记录）
   1      1  req         完成               完成判据（progress.md 里逐条记录证据）
   1      1  other                        实施要点
   1      1  meta        实施记录             实施记录（2026-10-10，PM 直执）
   1      1  meta        实施记录             实施记录（PM 核销 2026-10-10 19:12）
   1      1  req         实现               实现细节
   1      1  req         实现               实现要求
   1      1  req         实现               实现要点（design.md D-001/D-007）
   1      1  req         实现               实现要点（design.md D-002/D-010/D-014）
   1      1  req         实现               实现要点（design.md D-002/D-010）
   1      1  req         实现               实现要点（design.md D-003/D-004，实测依据 design note 补充核查）
   1      1  req         实现               实现要点（design.md D-005/D-007）
   1      1  req         实现               实现要点（design.md D-005）
   1      1  req         实现               实现要点（design.md D-011/D-013）
   1      1  req         实现               实现进度（T-18 提前完成了一半，2026-10-10）
   1      1  other                        审计（VC-008 证据）
   1      1  req         对照               对照协议（`plan.md §5`，三组都要）
   1      1  constraint  已知               已知残余（诚实记录）
   1      1  constraint  已知               已知触点（必须同卡处理）
   1      1  other                        当前实现状态（**以实跑为准**，不要照抄本文件的描述）
   1      1  req         必须               必须主动找反例（对抗式）
   1      1  req         必须               必须修的 6 处（逐条改完在报告里贴 diff 摘要）
   1      1  req         必须               必须同步的既有测试（改 prompt 措辞会碰）
   1      1  req         必须               必须同步的测试
   1      1  req         必须               必须实现（P1 档：已知写模式 + 路径判据；失败模式 = 漏放）
   1      1  req         必须               必须实现（按顺序）
   1      1  req         必须               必须独立复算的东西（不得只读结论）
   1      1  other                        手册必须包含（章节骨架固定，顺序照此）
   1      1  other                        执行期修订（必读，已写入 design/spec）
   1      1  other                        执行步骤
   1      1  other                        挂载与不变量
   1      1  other                        挂载坐标（基线 `6d98c5ee3`，逐条核验后再改，漂移即报告）
   1      1  req         接口               接口契约（design §2 钉死，命名偏差 ≤ 别名级）
   1      1  req         改动               改动（只 mirror，不放宽任何既有校验）
   1      1  other                        数据流顺序（唯一合法顺序，不得跳步）
   1      1  other                        映射表（执行版）
   1      1  other                        暴露 delegate 参数（测试 seam）
   1      1  other                        最终目标（本卡必须达成的端到端行为）
   1      1  other                        未做（范围内明确排除）
   1      1  other                        模板引文规则（parity 契约，必须严格遵守）
   1      1  req         测试               测试 `test_rag_docs.py`（unittest）
   1      1  req         测试               测试/夹具（5 处触点）
   1      1  req         测试               测试点（VC-001/002/003/006/009）
   1      1  req         测试               测试点（VC-004）
   1      1  req         测试               测试点（VC-005）
   1      1  req         测试               测试点（VC-007）
   1      1  req         测试               测试点（VC-008）
   1      1  req         测试               测试点（VC-010）
   1      1  req         测试               测试（`packages/coding-agent/test/suite/autopilot-read-scope.test.ts` 新 describe，既有 describe 零修改）
   1      1  req         测试               测试（`rag-parity.test.ts`，用共享 fixture；读法照 `test/extensions/agent-team-loop-profile-injection.test.ts:550` 的 `new URL("../../../multi-workers/...", import.meta.url)`）
   1      1  req         测试               测试（追加到 `packages/coding-agent/test/suite/rag-window.test.ts`）
   1      1  req         测试               测试（追加到 `packages/coding-agent/test/suite/rag-window.test.ts`，不要动 T-1 写的用例）
   1      1  constraint  源码               源码（4 处）
   1      1  ctx         现状               现状（先读代码确认，**以符号名为准**）
   1      1  ctx         现状               现状（实测）
   1      1  req         用例               用例流程
   1      1  req         用例               用例清单
   1      1  intent      目标               目标（两件，同一卡）
   1      1  other                        真实 key 跑批 dossier（2026-09-10T03:55:34Z，exit 1）
   1      1  ctx         缺陷               缺陷（T-14 报出，PM 已复核）
   1      1  ctx         缺陷               缺陷（T-14 报出，PM 已独立复现）
   1      1  ctx         背景               背景（RQ-5 实证）
   1      1  ctx         背景               背景（T-15 上报的两处真实偏差，PM 已复核确认）
   1      1  ctx         背景               背景（为什么做）
   1      1  ctx         背景               背景（为什么必须做）
   1      1  ctx         背景               背景（你需要知道的系统事实）
   1      1  ctx         背景               背景（实测，T-1 执行期发现 → design D-111）
   1      1  ctx         背景               背景（实测，可直接引用）
   1      1  ctx         背景               背景（实测，来源见 evidence/research/design-verify-tool-contract-2026-09-23.md）
   1      1  ctx         背景               背景（已核实的真实缺口）
   1      1  ctx         背景               背景（机制完整性缺口）
   1      1  ctx         背景               背景：T-4 之后的两次 PM 直执改动
   1      1  req         行为               行为要求（每条附 design 决策号）
   1      1  other                        补充要求：`rag_chat` 的 per-call 上限（T-05 遗留、必须由本任务闭合）
   1      1  other                        要做的
   1      1  deliv       证据               证据（写进 `report.md`）
   1      1  other                        语料来源（必须逐字引用 + 标出处）
   1      1  deliv       输出               输出格式（写入 `evidence/reviews/qg-review-mw-vision-role-20260926.md`）
   1      1  other                        运行命令（PM 已实测可用，PowerShell）
   1      1  other                        追加（PM，00:05）：`dist` 与 `src` 漂移核实（C-12，收口必办）
   1      1  other                        追加（PM，00:20）：`[WRITE_SURFACE]` 审计行的端到端 emit 覆盖
   1      1  other                        追加（PM，23:55）：`update_index.py` 副本拓扑核实
   1      1  other                        逐处方案
   1      1  ctx         问题               问题（IN-3 放大器 F1/F3/F5）
   1      1  ctx         问题               问题（IN-3 放大器 F2/F4）
   1      1  ctx         问题               问题（IN-3 根因，实测）
   1      1  ctx         问题               问题（实证，两条）
   1      1  ctx         问题               问题（用户反馈 2026-10-10）
   1      1  ctx         问题               问题（用户要求①：隔离）
   1      1  ctx         问题               问题（用户要求②③）
   1      1  constraint  阻塞               阻塞详情（已解决）
   1      1  meta        附录               附录 A — T-17/T-18 修复后复验（2026-09-26，T-19）
   1      1  other                        附注（环境性失败归属，非本 key）
   1      1  other                        附注（现场观察）
   1      1  other                        非空洞对照（`evidence/scripts/t18-controls.ps1`，六组均转红 + 还原校验 True）
   1      1  other                        非空洞对照（`evidence/scripts/t20-controls.ps1`，A~G 七组均转红 + `restored: True`）
   1      1  other                        非空洞对照（`evidence/scripts/t21-controls.ps1`，A~E 全红 + `restored: True`）
   1      1  other                        非空洞对照（必做，各贴输出）
   1      1  other                        非空洞对照（必须真跑贴红/绿，并逐字节还原）
   1      1  req         验收               验收命令（PM 执行，worker 不得自行运行全量）
   1      1  req         验收               验收（必须给真实输出）
   1      1  req         验收               验收（真实输出入报告）
   1      1  req         验证               验证方式
   1      1  req         验证               验证方式（VC 断言，测试输出含 [VERIFY] 行）
   1      1  req         验证               验证（必须有实物输出）

family totals (heading occurrences): {"meta": 534, "intent": 312, "deliv": 304, "req": 469, "other": 194, "constraint": 102, "ctx": 57}
```