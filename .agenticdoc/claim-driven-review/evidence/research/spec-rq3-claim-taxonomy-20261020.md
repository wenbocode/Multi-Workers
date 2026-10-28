# RQ-3 断言分类法、误拒反例集与绕过反例集（claim-driven-review）

- Key: `claim-driven-review` · 卡: `tasks/RQ-3-claim-taxonomy.md` · 角色: research（只读仓库，唯一证据文件即本文件）
- 产出对象：AC-001（派发期四要素校验）与 AC-002（结算期 `## 断言裁决` 表）的**分类法 + 负样本**，供 design 定 validator 宽容边界。
- 全部数字由本卡脚本实测（命令见 §1.1 与 `## 证据`）；本文件不含未经运行验证的结论。

## 0. 结论先行

1. **四类划分必须按"最便宜的充分判据"定义，而不是按题面措辞**：11 张真实 review 卡共拆出 **104 个判定单元**，其中 命令可判 21（20.2%）、grep 可判 28（26.9%）、结构可判 29（27.9%）、仅人工 26（25.0%）。四分之一的要求**天然只能是 manual**——把它压成可机检断言就是 Goodhart（`spec.md:87` 已登记该风险）。
2. **四要素校验的误拒来自"复合单元"，不是来自"要求太软"**：在 9 条误拒样本里，6 条经 split 后可落入 cmd/grep/struct（如"逐条给 PASS/FAIL"= 1 条结构 + N 条人工），只有 3 条应当直接是 `manual`。因此 validator 必须**先容忍、再要求拆分**，不能对 `判据` 字段做"必须可执行"的硬校验（`spec.md:88` 的 P-048 宽容教训同样适用）。
3. **最有价值的负样本不是"写不出断言"，而是 extras 兜底与自证证据**：`审计目标` 在服务层可用一行 `审计目标: <prompt 首行>` 自动满足（`packages/multi-workers/autopilot/dispatch.py:467-469`），envelope 兜底还会注入 `[ENVELOPE_FALLBACK] 审计目标: 服务层兜底骨架`（`packages/multi-workers/launcher.py:1867-1875`）；实测 46 张 `type: review` 的 worker 卡中 **22 张（47.8%）不含该 extras 模式**，说明"文本存在"既不充分也不必要。
4. **历史基线证明"证据只落在 output.md"是常态，不是假设**：46 次 review 派发里 34 次有独立产物（`report*.md` 或 write_face），**12 次（26.1%）只有 `output.md`**，而这 12 份 `output.md` **0 份含 `[VERIFY]`**；29 份 `report*.md` 里也有 17 份（58.6%）不含。任何以 `[VERIFY]` 或"报告存在"为判据的结算门，在历史语料上都是零检出。
5. **绕过面的廉价判据必须落在 trace 与路径集合上，而不是文本质量上**：可零成本落地的 4 条是（a）证据路径 ∉ 自证集合，（b）行号可解析且摘录可在该行命中，（c）`取数 ≤ 实际 trace 中 read/grep 次数`，（d）`unverified` 占比与原因受控词表 + 与 trace 事实对齐。这 4 条加 B-9/B-10 两条同类判据可拦住 §4 的 10 条绕过中的 7 条，且误伤面可枚举。
6. **`manual` 必须按"双倍预算 + 只能 unverified/带人工裁决的 closed + 不进 closed 比率"记账**；建议上限 `⌈claims/3⌉ ≤ 4`，超过即派发拒绝（`manual` 只能是少数派，否则审查退化为"写完就 PASS"）。

## 1. 语料盘点

### 1.1 命令与口径

```text
# 全量任务卡 / worker 卡
python -c "import glob;print(len(glob.glob('.agenticdoc/*/tasks/*.md')), len(glob.glob('.agenticdoc/*/workers/*/task.md')))"
#   608 608

# 按 header type: 统计（type 行出现在前 20 行，任务卡形如 "- type: review"）
#   见 §1.2 表；review: workers 46 / cards 14
#
# 名称或标题含 review|verif|qg|audit
#   workers 123 / tasks 82（其中 header type=review 的仍为 46 / 14）
```

口径：**"review 类任务" = worker 卡 header `type: review`（46）**；`type` 缺失或写成 coding/research 但标题含 review/qg/verif 的 77 张不计入主集，只在误拒分析里当"题面即人工审"的样本。任务卡侧 `type: review` 为 14 张，全部带 `审计目标` 与 `未覆盖面声明`（`dispatch-card.ts:191` 的 extras），故卡片侧合规率 14/14，worker 侧只有 24/46 与 23/46——**同一契约在卡片与派发物两个面上的落地率不同**，这是 §3 误拒样本 M-1 的语料基础。

### 1.2 抽样的 11 张卡与判定单元分布

| 卡 | 路径（去 `.agenticdoc/` 前缀） | 单元 | 命令可判 | grep 可判 | 结构可判 | 仅人工 |
| --- | --- | --- | --- | --- | --- | --- |
| DS-QG2 | `mw-decision-substitution/workers/ds-qg-review-2/task.md` | 16 | 4 | 6 | 3 | 3 |
| DS-QG2C | `mw-decision-substitution/workers/ds-qg-review-2c/task.md` | 7 | 2 | 4 | 0 | 1 |
| DS-QG2D | `mw-decision-substitution/workers/ds-qg-review-2d/task.md` | 11 | 9 | 1 | 1 | 0 |
| T18 | `mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/task.md` | 14 | 3 | 2 | 4 | 5 |
| QG2B | `mw-gate-verdict-hardening/workers/mwg-qg2b-code-adversarial/task.md` | 16 | 0 | 8 | 7 | 1 |
| W15 | `mw-worktree-junction-guard/workers/wjg-w15-delta-adversarial/task.md` | 8 | 1 | 0 | 3 | 4 |
| ACB-V1 | `mw-worker-output-contract/workers/acb-v1/task.md` | 6 | 1 | 3 | 2 | 0 |
| REFV | `mw-rag-integration/workers/mw-rag-integration-ref-verify/task.md` | 6 | 0 | 2 | 4 | 0 |
| DESIGN | `mw-rag-integration/workers/mw-rag-integration-design-critique/task.md` | 7 | 0 | 0 | 2 | 5 |
| R-02 | `mw-model-fallback-cli/workers/review-fallback-cli-r2/task.md` | 6 | 0 | 1 | 2 | 3 |
| CODEREV | `mw-dispatch-flow-fixes/workers/code-review-1/task.md` | 7 | 1 | 1 | 1 | 4 |
| **合计** | 11 张 | **104** | **21** | **28** | **29** | **26** |

拆分粒度：以"一个可被单独裁决的命题"为一个单元；`1. **逐条核对 4 major + 2 minor ...**` 这类外层要求不单独计数，只计其下 6 条子命题（`ds-qg-review-2/task.md:29-35`）。全部单元的行号见 §1.3 明细（按卡分组，每条给出源行）。

### 1.3 单元明细（抽样卡，逐条）


**DS-QG2** — `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/task.md`

- `A1` L29 [struct] 逐条核对 4 major + 2 minor 是否真的关闭
- `A2` L30 [grep] 工具是否完全不再读 .mw/decide-points.json（grep 级证据）
- `A3` L30 [grep] decision_id/mode/acted 是否只来自子进程
- `A4` L30 [grep] acted 是否还有任何由 mode 反推的残留
- `A5` L31 [cmd] 缺字段清单是否与 Python REQUIRED_STATE_FIELDS 真的一致
- `A6` L32 [struct] force_off 判定逐条对 _parse_row 的 L2/L3/L5
- `A7` L32 [grep] L4/L7 是否没有被误判成 off
- `A8` L33 [cmd] worker_file 写 evidence/review/sign-final.md 是否真被拒
- `A9` L33 [cmd] write、edit、bash 三个通道是否仍拒
- `A10` L34 [cmd] disagree + auto 是否 acted=false 且不写头行
- `A11` L35 [grep] 3a 超限 trace 是否为 input-oversize
- `A12` L35 [grep] 该值是否没有污染 Python 的 7 值 ESCALATED_REASONS
- `A13` L36 [manual] 修复是否引入新的 D-036 违约、新的 fail-open、新的跨层漂移
- `A14` L37 [struct] AC-001..015 是否仍全部 covered/partial 状态不变
- `A15` L38 [manual] 测试有效性抽样 >=3，证明行为级而非镜子级
- `A16` L39 [manual] 文档-代码一致性

**DS-QG2C** — `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2c/task.md`

- `B1` L23 [grep] 工具是否仍读 .mw/decide-points.json（grep 证据）
- `B2` L24 [grep] 三键是否只来自子进程 payload（缺键时必须 fail）
- `B3` L25 [grep] 全文件搜 acted
- `B4` L27 [cmd] dp1/dp2/dp3 必填字段集与 REQUIRED_STATE_FIELDS 实际一致（抄下来逐项对照）
- `B5` L28 [cmd] available=false 时 escalated_reason 是否原样透传
- `B6` L29 [grep] 3a 超限分支的 trace 原因值；是否属于 ESCALATED_REASONS
- `B7` L30 [manual] 恒为 input-incomplete 是否与 AC-012 冲突

**DS-QG2D** — `.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2d/task.md`

- `C1` L23 [cmd] 非对象行 -> 该 dp 关
- `C2` L24 [cmd] mode/note/tier 类型不合法 -> 关
- `C3` L25 [cmd] enabled 非布尔 -> 关
- `C4` L26 [cmd] tier 越界（L4）与 tier 与注册表不一致（L7）-> 不关
- `C5` L27 [grep] acted 是否来自子进程 payload
- `C6` L29 [cmd] worker_file 写 evidence/review/sign-final.md 与 evidence/sign-final.md -> 拒
- `C7` L30 [cmd] worker_file 写 evidence/review/ 下其它文件名 -> 放行
- `C8` L31 [cmd] worker_file 写 evidence/research/ 下任意证据 -> 放行
- `C9` L32 [cmd] write / edit / bash 三通道对签收路径 -> 仍拒
- `C10` L33 [cmd] MINOR-1 三态：agree+auto 采纳并写头行；disagree+auto 不写
- `C11` L34 [struct] AC 矩阵复核：只给出不变的 12/3/0 或变化条目

**T18** — `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/task.md`

- `D1` L27 [manual] 这三条在什么情况下仍会失效
- `D2` L29 [struct] 逐条 AC-NNN -> 判定 -> 证据 -> 反例或缺口
- `D3` L37 [manual] worker 往 _autopilot 树内写入是否不再被判为未记录写入
- `D4` L38 [cmd] 三面是否仍可能显示 0 pending？给出三面实测
- `D5` L39 [cmd] 被抑制的 gate 是否在 timeline 留下 remind-suppressed
- `D6` L40 [cmd] 活 serve 是否被判 STALE CODE；短 OID 是否被误用
- `D7` L41 [manual] 能否构造证据未齐却被自动 approve 的反例
- `D8` L42 [grep] 是否确实只升级、从不闭合 stage（源码+测试证据）
- `D9` L43 [grep] 编号是否绝不复用；原 gate 判定是否字节不变
- `D10` L44 [struct] 五形态是否全部 fail-closed
- `D11` L45 [manual] 人工 switch_key 是否优先且不被抢回
- `D12` L46 [struct] 16 条 AC 中哪些没有对应的可复现实测
- `D13` L47 [manual] held-conductor 端到端 4 问
- `D14` L51 [struct] 至少给出 5 条对抗用例（输入->预期->实测->结论）

**QG2B** — `.agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg2b-code-adversarial/task.md`

- `E1` L19 [manual] 凡只能由运行证实的项，结论只能是无法判定
- `E2` L30 [struct] 逐条列出该路径上所有会写盘/改状态的语句（行号）
- `E3` L31 [grep] 拒绝路径只 return gated（不写 QG/achieved/pm-state）
- `E4` L32 [struct] 五个写者逐个判定是否只重写自己那一行
- `E5` L33 [grep] 确认阶段条件只覆盖 design/plan
- `E6` L34 [grep] unparsable > 0 是否在配额/候选构造之前短路
- `E7` L35 [grep] 默认值与取值域（两侧坐标）确认相等
- `E8` L36 [grep] run.json 由 worker 自写还是 launcher 代写
- `E9` L37 [grep] 默认阈值/上限次数；已答门零残留
- `E10` L38 [grep] PANEL_STALE_MISSED_CYCLES 与 STALE PANEL 的出现条件
- `E11` L39 [struct] 抽 >=6 个 evidence/scripts/*-controls.ps1 判断是否承重
- `E12` L40 [struct] 两侧镜像逐项相等（27/20/14/2）
- `E13` L41 [struct] 空洞测试抽查 >=8 个：断言是否连着被测路径
- `E14` L42 [grep] ac_refs/vc_refs 是否有空绑定/编号错配
- `E15` L43 [struct] achieved.md 一致性：两类清单
- `E16` L48 [struct] 14 行必须齐全

**W15** — `.agenticdoc/mw-worktree-junction-guard/workers/wjg-w15-delta-adversarial/task.md`

- `F1` L43 [manual] 返回 {result} 是否确实使命令体不被 spawn
- `F2` L44 [struct] 逐条给拦/放结论并标注哪些必须拦
- `F3` L45 [manual] 干净命令是否可能被误拦
- `F4` L46 [struct] 逐条给 issue+rc / 静默 实测结论
- `F5` L49 [manual] 标记是否可能在能力缺失的情况下仍然出现（假绿）
- `F6` L51 [cmd] 两份 bundle 的字节与计数；全局那份是否就是加载的那份
- `F7` L52 [manual] 逐条判定该断言是否可能假绿
- `F8` L37 [struct] 未覆盖面声明必须分列两层

**ACB-V1** — `.agenticdoc/mw-worker-output-contract/workers/acb-v1/task.md`

- `G1` L22 [grep] (a) 自检回合条件包含 hasDeliverableEvidence(...).delivered
- `G2` L22 [grep] (b) selfCheckSent 每进程一次
- `G3` L22 [grep] (c) 未交付走 finishSuccess（no-product 裁决）
- `G4` L22 [struct] 逐条给 PASS/FAIL
- `G5` L23 [struct] 产物落 evidence/acb-v1-audit.md（含逐条结论）
- `G6` L30 [cmd] [VERIFY] ACB-V1 探针交付：exit=0

**REFV** — `.agenticdoc/mw-rag-integration/workers/mw-rag-integration-ref-verify/task.md`

- `H1` L10 [struct] 每条给出：存在? / 语义一致? / 实际内容摘要
- `H2` L43 [struct] 一张表：# | 引用位置 | 存在 | 语义一致 | 证据
- `H3` L15 [struct] TOOL_ALLOWLISTS 工具集合与顺序逐一比对
- `H4` L30 [grep] 给出该断言的原文逐字引用
- `H5` L34 [grep] 是否存在其他位置也剥离/注入 env（grep env.pop）
- `H6` L45 [struct] 最后 ## 未能核对：列出来核不成的项及原因

**DESIGN** — `.agenticdoc/mw-rag-integration/workers/mw-rag-integration-design-critique/task.md`

- `I1` L19 [struct] 16 条 AC ... 三选一 + 理由
- `I2` L22 [struct] 22 条 VC ... 逐条给结论
- `I3` L24 [manual] VC-017 是否真能验证心跳防误杀
- `I4` L30 [manual] 是否有被忽略的明显替代方案；否决理由是否成立
- `I5` L35 [manual] 这是合理扩展还是改测试以绕门禁
- `I6` L38 [manual] GC-1/GC-2/GC-5/GC-6/GC-7 是否都被 design 显式尊重
- `I7` L44 [manual] K1/K2 划分是否有隐含依赖倒挂

**R-02** — `.agenticdoc/mw-model-fallback-cli/workers/review-fallback-cli-r2/task.md`

- `J1` L21 [struct] 报告写入唯一证据文件（勿覆盖 R-01 报告）
- `J2` L22 [grep] 每项判定给 文件:行 或测试用例名证据
- `J3` L23 [manual] F1/F2/F3 是否全部闭合，D1-D4 是否解除
- `J4` L46 [struct] 六项三态判定
- `J5` L47 [manual] 用例是否真的会在旧实现下失败
- `J6` L55 [manual] 不重跑 pytest/vitest/biome/tsgo

**CODEREV** — `.agenticdoc/mw-dispatch-flow-fixes/workers/code-review-1/task.md`

- `K1` L12 [manual] Correctness bugs and race conditions
- `K2` L13 [manual] Type-safety regressions
- `K3` L14 [manual] Protocol/format regressions
- `K4` L15 [manual] Contradictory or dead code
- `K5` L16 [grep] worker_liveness must be informational only
- `K6` L18 [struct] For each finding: severity, file:line, explanation, fix
- `K7` L18 [cmd] Do not modify any files

### 1.4 结构性事实（决定 schema 与门禁形态）

| 事实 | 数值 | 命令/来源 |
| --- | --- | --- |
| review worker 卡 header `type: review` | 46 / 608 | §1.1 |
| review 任务卡 `type: review` | 14 / 608 | §1.1 |
| review worker 卡缺 `审计目标` extras 模式 | 22 / 46 (47.8%) | 用 `dispatch-card.ts:257-263` 的同一正则逐文件匹配 |
| review worker 卡缺 `未覆盖面声明` 模式 | 23 / 46 (50.0%) | 同上 |
| review 任务卡缺上述两项 | 0 / 14 | 同上 |
| 有独立产物（`report*.md` 29 或 write_face 7，重叠 2） | 34 / 46 (73.9%) | 目录实测 |
| 只有 `output.md`（无 report、无 write_face） | 12 / 46 (26.1%) | 目录实测 |
| 上述 12 份 `output.md` 中含 `[VERIFY]` | 0 / 12 | 文本扫描 |
| 29 份 `report*.md` 中不含 `[VERIFY]` | 17 / 29 (58.6%) | 文本扫描 |
| 历史实测：12 次 review 派发 8 次未交出结论 | 8 / 12 | `.agenticdoc/_pitfalls.md:71` |

`dispatch-card.ts:203-208` 自记的历史口径是 `workers/<task>/task.md` 头 `review 28`；当前实测 46，说明**按 type 计数的语料在增长，任何"review 卡必然包含 X"的硬假设都会随语料漂移**。

## 2. 分类法

### 2.1 四类的判定边界（用"最便宜的充分判据"定义）

| 类 | 边界（必要且充分） | 反例（不算此类） |
| --- | --- | --- |
| `cmd` 命令可判 | 存在一条**可在本机原样执行**的命令，其 `rc` 或某个 `key=value` 计数直接决定命题真假 | "`grep` 一下就知道"不是 cmd（无可执行串）；"跑全量 suite"不是 cmd（无定向、预算不可控） |
| `grep` grep 可判 | 存在**锚点**（`path:line` / 符号 / 正则目标）+ **闭集谓词**（存在/不存在/计数/相等/包含/零命中），不需执行即决定真假 | "`X` 是否与 `Y` 一致"若 `X`、`Y` 都是集合则需要执行提取 → cmd；"是否自洽"无锚点 → manual |
| `struct` 结构可判 | 命题的真假等于某个**声明形状**的完整性：行数/列数/段名集合/id 集合相等/枚举清单条数 | "逐条判断每条是否成立"——形状可判但**格内容**不可判 → 必须再拆 |
| `manual` 仅人工 | 无锚点，或谓词不在闭集内（自洽/合理/成立/失效/冲突/风险/替代方案…） | "1 号发现是否关闭"不属此列（可由证据 + 判据判）；"是否引入**新的** fail-open"属此列（全称否定，无枚举源） |

**判定顺序（优先级从高到低，先命中先定类）**：`V 人工否决 → NEG 否定式排除 → P1 执行线索 → P2 形状线索 → P3 锚点+闭集谓词 → 默认 manual`。

```text
V    = (自洽|合理|是否成立|能否接受|失效|误拦|误判|冲突|尊重|倒挂|假绿|建议|质疑|优劣|影响面|风险|为什么|必要|充分|是否真能)
NEG  = (不|禁止|不得|禁)[^，。]{0,4}(跑|执行|运行|重跑)          # "不重跑 pytest" 是过程约束，不是执行判据
P1   = (=>|->|rc=|exit=|exit code|pytest|vitest|npm |node |python |mw [a-z]|git |命令原文|复算|实测)
P2   = (逐条|逐项|每条|每一条|全部|齐全|矩阵|清单|三态|五形态|两层|三选一|逐字|表|至少\s*\d+\s*条|\d+\s*(行|个|条))
P3a  = ([\w.-]+/[\w./*{}-]+|[\w-]+\.(ts|py|md|json|ps1|yml|log)|[A-Z]{2,}[A-Z0-9_]{2,}|[a-z]+_[a-z_]+|[a-z]+[A-Z][A-Za-z]+|[a-z]+-[a-z-]+|AC-\d+|VC-\d+|D-\d+|:\d+)
P3p  = (不存在|存在|没有|不再|仍|计数|=\s*\d|==|>=|<=|一致|相等|零|残留|来自|属于|包含|覆盖|归零|每进程一次|只)
```

**关键设计点：`是否` 不是谓词，只是疑问标记**。把它当谓词会让"是否引入新的 fail-open"被误判成 grep 类（本卡实测的 v1 规则正是如此，见 §2.4 的 dangerous 计数）。validator 侧同理：`判据` 里出现"是否"不得视为可机检。

### 2.2 每类的最小 `判据` 写法模板

```text
cmd   : cmd: <verbatim command> => rc=<n> [k=v ...]        # 一条命令、单行、无 &&/;/>；管道仅允许 bash -lc '...'
grep  : grep: <path>[:a-b] :: <regex> => count=<n> [cmp]   # cmp ∈ {=,>=,<=,0}；regex 必须是 POSIX 可移植子集
struct: shape: <artifact> :: <列/段/id 列表> x <行数>       # 例：shape: report.md :: [claim,裁决,证据] x 6
manual: manual: <artifact> :: <二选一判定式> => 由 <谁> 在 <裁决文件:line> 裁决
```

三条**真实语料**例句（含原文行号）：

1. `cmd` — `wjg-w15-delta-adversarial/task.md:66-71` 的验收命令块：`node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts ...` → 最小判据 `cmd: node ../../node_modules/vitest/dist/cli.js --run test/suite/worktree-junction-guard-decide.test.ts => rc=0`。
2. `grep` — `ds-qg-review-2/task.md:30`「工具是否完全不再读 .mw/decide-points.json（`grep` 级证据）」→ `grep: packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts :: \.mw/decide-points\.json => count=0`。
3. `struct` — `mwg-qg2b-code-adversarial/task.md:48`「表：`# | 结论(成立/不成立/无法判定) | 代码锚点 | 最强反例`，14 行必须齐全」→ `shape: report.md :: [#,结论,锚点,反例] x 14`。

第 4 类（manual）的真实例句见 §3 M-4、M-5：`ds-qg-review-2/task.md:36`「修复是否引入新的 D-036 违约、新的 fail-open、新的跨层漂移」无锚点闭集，只能 `manual`。

### 2.3 一条要求 → 一类的可执行流程（含复合单元拆分）

```text
S0 拆分：一个单元若同时含 [形状/执行并列] 与 [判断谓词]，先按 (；|。|，)?? + (是否|判断|评价|理由|影响) 切分；
        并列形态 "A；B；C" 按分号切（9 条误拒样本里 6 条拆分后可落入 cmd/grep/struct）。
S1 对每个原子单元套 §2.1 的 V/NEG/P1/P2/P3 判定。
S2 若命中 V → manual（即使带锚点）：锚点只用于写"未验证原因"，不改变类。
S3 若 P1 与 P2 同时命中 → 取 P1（cmd 可同时覆盖结构完整性：断言 rc 之外再断言行数）。
S4 若只剩 P3a 无 P3p → manual（有位置、无谓词 = 只是在指着某个文件）。
```

### 2.4 规则实测（对 §1.3 的 104 个单元）

| 指标 | 值 |
| --- | --- |
| 规则输出与人工裁决一致 | **66 / 104（63.5%）** |
| 规则输出分布 | cmd 14 / grep 11 / struct 25 / manual 54 |
| 危险方向（人工 manual 被判成可机检） | **1**（`R-02` J3「F1/F2/F3 是否全部闭合」误判 struct） |
| 保守方向（可机检被降级为 manual） | 29（代价是多记一条 claim，不会假通过） |

结论：该规则可用作**筛查器 + 宽松上限**，不可用作拒绝依据。规则把 29 个可机检单元降级为 manual（保守），只把 1 个人工单元误升为可机检（收敛在 V 否决表的漏词 `全部闭合`）。设计上应要求卡片**自报类**（`类型: cmd|grep|struct|manual`），validator 只校验"自报类与判据前缀一致"，不重新推断类。

### 2.5 语料里的"缺通道"事实：21 个 cmd 类单元里 11 个无执行串

104 个单元中含执行线索（P1）的共 15 个，其中只有 10 个与 cmd 类重合——**11 个行为类命题（A5/A8/A9/A10/B4/B5/C10/D5/D6/F6/K7）在卡里没有任何可执行串**。这 11 条只能靠"存在某个测试文件"间接落地，而测试文件名在卡里并不出现（`ds-qg-review-2/task.md:33` 只写"write、edit、bash 三个通道是否仍拒"，测试名 `decision-signoff.test.ts` 只在 `:21` 的修复表里出现）。

对 design 的直接含义：**AC-001 要求每条 claim 带 `判据`，但卡片目前连"判定通道在哪"都不写**；validator 必须允许 `判据: cmd: TBD(<测试文件名>)` 这种**待定通道**并计入 `unverified(budget=0)` 预算，而不是拒绝派发。

## 3. 误拒反例集（四要素校验会拒绝的真实要求）

本节 9 条全部来自 §1.3 的真实卡文。每条的判定标准是：**能不能按 AC-001 的 `id/陈述/反证条件/定位/判据/预算` 六项填满且不被 validator 拒**。注意 AC-001 只校验"四要素均非空 + 定位语法"，因此真正的误拒风险来自**后续 design 可能追加的"判据必须可执行"**；本节的"为什么会被误拒"即指这一类。

### M-1 全称否定的回归审计（→ manual，不可硬改）

- 语料：`.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/task.md:36`
- 原文：「回归审计：修复是否引入新的 D-036 违约、新的 fail-open、新的跨层漂移（尤其 FIX-B 删掉了 `Dp2Authorization.mode` 这类收窄式 API 变更的所有调用点是否真的干净）。」
- 为什么四要素填不上：`陈述` 只能是"没有引入**新的** fail-open"——全称否定；`反证条件` 要求枚举"所有 fail-open 形态"，语料里没有这个枚举源；`定位` 是"本次 diff 的全部变化点"，不是 `path:line`；`判据` 无命令；`预算` 无界（review 的 `read_scope` 上限 8 file / 65536 B，`packages/multi-workers/autopilot/dispatch.py:224-250`，`:233-238` 记录了两名 L3 reviewer 花光 8 次配额后 0/23、0/31 无法断言的先例）。
- 归处：**manual**。这是"应当保留为人工"的典型，不是改写对象。
- 若必须机检，只能降级成两条弱断言（不覆盖原意，需在 `未覆盖面声明` 里写明）：
  - (a) `grep`：「diff 新增的兜底形态清单与基线相同」→ `grep: <diff-file> :: ^\+.*(catch|except|or None|getattr\(|\?\?) => count=0`（只看新增行，不看语义）。
  - (b) `manual`：「新增兜底点中是否有把失败折叠为成功的」→ manual 二选一，由 PM 在指定 `evidence/…:line` 裁决。
- 对 design 的要求：`反证条件` 允许**抽样式**写法（`抽 N 个点，若 ≥1 例反证则命题不成立`），validator 不得因为"非全称"而拒绝；`预算` 必须允许 `manual` 档（见 §6）。

### M-2 "所有会写盘语句"（→ 缺枚举源的 struct，需改为 cmd+grep 组合）

- 语料：`.agenticdoc/mw-gate-verdict-hardening/workers/mwg-qg2b-code-adversarial/task.md:30`
- 原文：「逐条列出该路径上所有会写盘/改状态的语句（行号），确认 `contract_guard.evaluate` 严格在它们之前……找出任何"先写后查"的分支（含提前 return 的旁路）。」
- 为什么四要素填不上：`反证条件` = "漏列了一条写盘语句"，但**"所有"没有 ground truth**，无法判定漏没漏；`判据` 写成"逐条列出"不是命令、也不是 grep；`定位` 是函数路径而非单行。若 validator 只查"四要素非空 + 定位语法"，这条会**通过校验但不可结算**（反向风险见 §4 B-2/B-9）。
- 归处：**改写为可机检**（不是 manual）。
- 改写后：
  1. `陈述`：`conductor.py::_done_transaction` 的写盘语句集合 = S；`反证条件`：存在写盘语句不在 S 中，或 S 中存在语句的行号落在 `contract_guard.evaluate` 调用行之前。
  2. `定位`：`packages/multi-workers/autopilot/conductor.py:1000-1080`（必须带行段，AC-001 ③）。
  3. `判据`：`grep: packages/multi-workers/autopilot/conductor.py:1000-1080 :: (write_text|open\(.*["\x27]w|\.write\() => count=N` 加 `shape: report.md :: [行号,语句,是否在 evaluate 之前] x N`。
  4. `预算`：`2`（一次 grep + 一次行号比对）；N 由 grep 决定，作者不得手抄。
- 对 design 的要求：`struct` 类 claim 的 `反证条件` 必须指名**枚举源**（哪条命令产出全集），否则 validator 应把它降级为 `unverified(ambiguous)`，而不是允许"逐条列出"式判据。

### M-3 "逐条给 PASS/FAIL"（→ 1 条 struct + N 条原子 claim）

- 语料：`.agenticdoc/mw-worker-output-contract/workers/acb-v1/task.md:22`（「逐条给 `PASS/FAIL`」）、`.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/task.md:29`（「逐条给出 AC-NNN → 判定 → 证据 → 反例或缺口」）。
- 为什么四要素填不上：一条 claim 同时要求"3 行齐全"（结构）与"每行判定正确"（人工），`判据` 只能写成"逐条 PASS/FAIL"——既非命令也非 grep，若 validator 要求"判据必须含命令或 `path:line`"即直接误拒。
- 归处：**拆分为 1 条 struct + N 条原子 claim**；acb-v1 的 3 个子项其实都是 grep 可判（见 G1-G3），因此这张卡的合法拆法是 3 条 grep + 1 条 struct，而不是 1 条混合 claim。
- 改写后（acb-v1 例）：
  - `C-01` grep：`grep: packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts :: hasDeliverableEvidence\(taskDir, lastAssistantText\)\.delivered => count>=1`（源行实测 `:3831-3833`、`:3991-3993`）。
  - `C-02` grep：`selfCheckSent` 只在一处被置 `true` 且以 `!selfCheckSent` 为前置（源行 `:3332`、`:3994-3995`）。
  - `C-03` grep：未交付分支落 `finishSuccess`（`:3813`、`:3827-3833`）。
  - `C-04` struct：`shape: evidence/acb-v1-audit.md :: [claim,判定,证据] x 3`。
- 对 design 的要求：validator 应允许"结构 claim 覆盖 N 个原子 claim 的呈现"，但**不得**允许结构 claim 替代原子 claim（`spec.md:78` 的 id 集合包含关系已是这个语义，需在 design 里写明是单向包含而非等价）。

### M-4 设计质量主观题（→ manual + 二选一裁决）

- 语料：`.agenticdoc/mw-rag-integration/workers/mw-rag-integration-design-critique/task.md:24`（VC-017 是否真能验证心跳防误杀）、`:30`（是否有被忽略的明显替代方案）、`:35`（「这是"合理扩展"还是"改测试以绕门禁"」）。
- 为什么四要素填不上：`反证条件` 需要命名一个"被忽略的替代方案"，输入空间开放；`定位` 只能到 `design.md §x`（章节号，不是行号）；`判据` 天然是"给出判断与理由"；`预算` 不可估。
- 归处：**manual**（不改写）。
- 改写后（保留可审计性，不假装机检）：`manual: .agenticdoc/mw-rag-integration/design.md::D-011 :: {合理扩展 | 绕门禁} => 由 PM 在 evidence/rq2-review.md:LL 裁决`。关键是**必须带二选一**（否则人工裁决退化为"看过"）。
- 对 design 的要求：`判据` 以 `manual:` 开头时，validator 只校验"是否含二选一枚举 + 裁决人 + 裁决落盘位置"，不校验可执行性。

### M-5 开放审查请求（没有命题，不该被 claim 化）

- 语料：`.agenticdoc/mw-dispatch-flow-fixes/workers/code-review-1/task.md:11-18`（「Review for, in priority order: Correctness bugs and race conditions…」「For each finding: severity (blocker/major/minor/nit), file:line, a one-paragraph explanation, and a suggested fix」「Do not modify any files」）。
- 为什么四要素填不上：整张卡是**任务描述**而非断言集；K1-K4（correctness / type-safety / protocol regressions / dead code）没有可证伪的命题形式；强行 claim 化会产出"不存在 race condition"这类全称否定（同 M-1）。
- 归处：**卡级改写**（triage 阶段先产出 claims，再扇出取证；`spec.md:36-38` 场景 3 即此形态）。
- 改写后（示例 2 条，替代 K1 与 K5）：
  - `C-01` grep：「`_workers.parallel` 的写入点全部走 `workers.lock`」→ `grep: packages/multi-workers :: _workers.parallel => count=N` + `grep: … :: workers\.lock => count>=N`（计数配对下界，非全称）。
  - `C-02` grep：「`worker_liveness` 只出现在信息面，不参与 verdict/exit code」→ `grep: packages/coding-agent/src/extensions/agent-team-loop :: worker_liveness => count=N` 且同集合内 `verdict|exitCode` 命中为 0（按文件分桶）。
- 对 design 的要求：这一形态需要 **triage → 扇出 → merge** 三步（AC-004）；若首轮派发就要求 claims 齐全，开放审查卡必然误拒——故 AC-001 需要一个 `claims_pending: triage` 的显式豁免（否则本卡这类语料 0/1 可派发）。

### M-6 "存在? / 语义一致?" 双列（→ 1 struct + 少量 manual，受预算约束）

- 语料：`.agenticdoc/mw-rag-integration/workers/mw-rag-integration-ref-verify/task.md:7-10`（「每条给出：存在? / 语义一致? / 实际内容摘要」）、`:43`（表列 `# | 引用位置 | 存在 | 语义一致 | 证据`）。
- 为什么四要素填不上：`存在` 是可 grep 的（锚点 `path:line`），`语义一致` 需要把"文档声称"与"代码实际"逐条比对，**每行命题不同**；21 条引用 → 若一对一 claim 化需要 42 条，超 `Σ预算 ≤ 40`（`spec.md:77` ④）且必然饥饿。
- 归处：**混合**：1 条 struct（21 行 × 4 列）+ 每行 `存在` 由摘录命中判据兜底 + 只在高风险行（3 条）开 manual claim。
- 改写后：`shape: report.md :: [#,引用位置,存在,语义一致,摘要] x 21` §`存在` 列的机检由 (c) 摘录判据承担：`path:line「excerpt」`（§5.3），excerpt 必须逐字出现在该行；`语义一致` 只对 3 条高风险行建 manual claim。
- 对 design 的要求：**结构 claim 必须能"携带"格级判据**（否则 21 行要么 21 条 claim 要么全人工）；这直接影响 `## 断言裁决` 是否需要"子行"概念（§5.1 的 `claim` 允许 `C-01.3` 形式）。

### M-7 过程否定约束（定位不在仓库文件里）

- 语料：`.agenticdoc/mw-model-fallback-cli/workers/review-fallback-cli-r2/task.md:55`（「不重跑 pytest/vitest/biome/tsgo（review 角色无 bash）」）、同类 `wjg-w15-delta-adversarial/task.md:30`（「不新建夹具、不写文件（writeless）」）。
- 为什么四要素填不上：`反证条件` = "本次 run 里发生了一次测试执行"，证据形态是 trace 事件而非仓库文件；`定位` 若限定为 `path:line`（AC-001 ②），就没有合法取值——这是**schema 缺一个定位域**，不是要求本身不可判。
- 归处：**改写为可机检**，并同时暴露 schema 缺口。
- 改写后：`定位: run:trace.log`（本次 run 的自产物）；`判据: grep: .agenticdoc/<key>/workers/<task>/trace.log :: [FLOW] .*tool_call .*(bash|pytest|vitest) => count=0`；`反证条件`：任意一行命中即命题不成立。
- 对 design 的要求：AC-001 ② 的定位域必须加 `run:trace.log`（以及 `run:run.json`），否则所有"过程约束类"审查（零写入、零执行、零夹具）都无法 claim 化——而这类约束在本语料里占 7 张卡的硬性要求。

### M-8 假绿/不可达证明（→ manual，且"找不到反例"不算证据）

- 语料：`.agenticdoc/mw-worktree-junction-guard/workers/wjg-w15-delta-adversarial/task.md:49`（「标记 `reparse-point` 是否可能在能力缺失的情况下仍然出现」）、`:52`（逐条判定"该断言是否可能假绿"）、`.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/task.md:37`（「请构造反例……若不可达，给出**证明**」）。
- 为什么四要素填不上：`反证条件` = "构造一个能力缺失但标记仍在的输入"——输入空间开放，无法给出"全部输入"的判据；`判据` 实际是"尝试 N 条路径均被拦"，这是**负结果**，天然不可作为 `closed` 证据。
- 归处：**manual**，且裁决必须允许 `unverified`（不是 FAIL）。卡文自己给了正确口径：`wjg-w15-delta-adversarial/task.md:32`「**禁止**把"我没找到反例"写成"不存在反例"」。
- 改写后：`manual: <artifact> :: {证伪成功 | 未找到反例(≠证明)} => 由 PM 裁决`，并强制 `攻击尝试=N`（卡已要求末行机器可读：`wjg-w15-delta-adversarial/task.md:38` 的 `ADVERSARIAL:` 行）。
- 对 design 的要求：`unverified` 必须能表达"负结果"（原因词表里的 `ambiguous` 或 `no-access`），且 PASS 判定不得把 `unverified` 当 0 分或当 1 分——必须在覆盖表里独立成列（§6）。

### M-9 计数 + 质量混合（这是"能过校验但没审"的桥接样本）

- 语料：`.agenticdoc/mw-decision-substitution/workers/ds-qg-review-2/task.md:38`「**测试有效性抽样 ≥3**：从本轮新增用例里挑 3 条，证明它们是**行为级**而非镜子级（能抓住回退）。」
- 为什么四要素填不上：`判据` 写成 `>=3` 即可通过所有语法校验，但"行为级"完全没有被判；`反证条件` 若写"用例在回退后仍绿"则又回到 M-1 式全称否定。
- 归处：**改写成 3 条 cmd（变异测试）**，这才是"能抓住回退"的可证伪形式。
- 改写后（对每条抽样用例）：`陈述`「用例 X 在把 `<被测行为>` 反向变异后必须变红」；`反证条件`「变异后仍 rc=0」；`判据` `cmd: <mutate> && node ../../node_modules/vitest/dist/cli.js --run <file> => rc!=0`；`预算` 2（一次变异 + 一次运行）。
- 对 design 的要求：这是"通过四要素校验但实际空转"的最短路径，§4 B-1/B-2/B-9 的判据必须与本节配套；否则 validator 会让 M-9 的 `>=3` 形态直接 PASS。

## 4. 被绕过反例集（表面合规、实际没审）

每条给出：绕过写法 → 为什么能过现有/朴素门 → **廉价机器判据（不调 LLM）** → 落在哪个校验点 → 误伤风险。校验点命名：**G1 卡 gate**（派发期，`dispatch-card.ts::typeExtrasMissing` 同级）、**G2 结算 gate**（`output-sections.ts::checkRecovery` / `worker-mode.ts::settleOrSelfCheck` 同级）、**G3 PM 收敛**（合并单元 / 覆盖表）。

| 编号 | 绕过写法 | 为什么能过朴素门 | 廉价机器判据 | 校验点 | 误伤风险 |
| --- | --- | --- | --- | --- | --- |
| B-1 | 复制卡内 claim id，全填 `closed`，证据指向本报告自身（`report.md:12`、`output.md:3`、`task.md:29`） | id 集合齐全、token 合法、"有 `path:line`" | 证据路径 ∉ 自证集合 `{report*.md, output.md, progress.md, task.md, card_path, 本卡 claims 块}`；且路径必须存在。自证集合可静态枚举，零成本 | G2 | review 产物通常就在 taskDir；若 worker 合法引用 `progress.md` 里的中间记录会误伤 → 允许 `progress.md` 作**二级证据**但不得作唯一证据 |
| B-2 | 全部标 `unverified` + 任意理由 | `unverified` 只需"有原因"（AC-002） | (a) `unverified` 占比 > 40% ⇒ 不得 PASS（升级 PM）；(b) 原因 ∈ 7 词闭集；(c) 每个原因须有事实对账：`budget` ⇒ 该 claim 取数 == read cap（8，`read-scope.ts:31`）或 trace 出现 `read_scope: blocked`；`no-access` ⇒ 角色工具表确实无该工具（`TOOL_ALLOWLISTS`，H1 已核 `read,find,grep,ls`） | G2 | 真·无 bash 的 review 卡（本语料 46/46 都是 `read/find/grep/ls`）合法产出大量 `no-access` → 上限必须按角色（review 允许 ≤60%，coding ≤10%） |
| B-3 | 引用不存在的行号 / 行号漂移 | 正则 `path:\d+` 通过 | `line ≤ len(file)`；可选 `「excerpt」` 必须归一化后出现在该行/行段内；`path:a-b` 要求 `a≤b≤len`、`b-a≤200` | G2 | 文件在评审期间被其他 worker 改写 → 行号合法但摘录不命中；故摘录校验只在 claim 声明 `excerpt` 时启用（strict profile），advisory 期只告警 |
| B-4 | 证据只写 `report.md`/`output.md`（自证"我已核对"） | 落盘契约只要求四段齐全（`output-sections.ts:48`） | 同 B-1 的自证集合；另要求 `closed` 行至少 1 条**非本 run 产物**的证据（仓库代码/测试/其它 run 的 evidence） | G2 | 纯文档类审查（如 design-critique）的合法证据就是 `design.md`（非本 run 产物，OK）；但"自我复核型"任务确实只能自引 → 这类必须走 `manual`，不得 `closed` |
| B-5 | 把断言改写成同义反复：`陈述`「X 已修复」/`判据`「grep X」/`反证条件`「X 未修复」 | 六要素非空、定位合法、判据可执行 | 归一化相似度：`陈述` vs `反证条件` 去掉否定词后 token 集合相同且相似度 ≥0.90 ⇒ 拒；`判据` 必须含一个**不在** `陈述` 中出现的 artifact token（路径/符号/命令） | G1 | 合理的最小改写（"已修复" vs "未修复"）本就只差否定词 → 必须比较"去否定后剩余 token"，且仅当**没有任何新 artifact**时才拒 |
| B-6 | 表格齐全但零取证：`取数` 填 1，实际未读任何文件 | 无字段校验取数真伪 | `Σ取数 ≤ min(卡 Σ预算, read file cap)`；且 `Σ取数 ≤ count(trace.log 中 [FLOW] .*tool_call (read|grep|find|ls))`。trace 行由 `worker-mode.ts:3225` 写入（格式只带 toolName，**不带路径**） | G2 | 一次 `bash` 里的多条读取不产生独立 tool_call；`ls`/`find` 可能一次覆盖多文件。故该判据只能作**上界**（拦"0 次调用却填 5 次取数"），不能反推读过哪些文件 |
| B-7 | 复用上一轮同卡裁决（copy 上次 QG 报告的行） | 内容看起来专业、行号也真 | 证据 mtime > 本次 `task.md` mtime，或该行显式写 `carried-from: <path:line>`（允许"未变即沿用"，但必须可审计） | G2 / G3 | 代码确实未变（mtime 更旧）是合法情形 → `carried-from` 是唯一放行通道，不做则误伤"复评类"卡（本语料 R-02 整张就是复评） |
| B-8 | 用兜底文本满足 extras：`[ENVELOPE_FALLBACK] 审计目标: 服务层兜底骨架`（`launcher.py:1867-1875`）或 producer 自动填 `审计目标: <prompt 首行>`（`dispatch.py:467-469`） | extras 只看"名字是否出现"（`launcher.py:1565-1592`；`dispatch-card.ts:457`） | (a) 文本含 `[ENVELOPE_FALLBACK]` ⇒ 该 extras 视为缺失；(b) `审计目标:` 后的 payload 必须含 ≥1 个锚点（`path:line` 或 `AC-\d+` 或 `D-\d+`），否则视为缺失 | G1 | 合法的短目标（"审计目标: 关闭判定"）会被 (b) 拒 → advisory 期只告警；enforce 需卡模板强制 `审计目标: <path:line> 的 <AC>` 形态 |
| B-9 | 把 claim 退化成"文件存在即成立"（`陈述`「X 存在」/`判据` `file X exists`） | 四要素齐全、判据确实可执行 | `陈述` 谓词白名单：至少 1 个非存在性谓词（行为结果/相等/计数比较/增量）；纯 `存在|exists|非空` ⇒ 拒（或强制归 `struct` 且不得单独支撑 PASS） | G1 | 有些 claim 的正当内容就是"该文件必须存在"（唯一证据文件类）→ 只对 `type=review` 的 `closed` 计数生效，不拦 `deliverable` 类 claim |
| B-10 | 结构 claim 吞掉全部原子 claim（1 行 `shape: report.md x 6` 代替 6 条裁决） | AC-002 只要求"表内 id ⊇ 卡内 id" | id 双向包含：`表 ⊆ 卡` 且 `卡 ⊆ 表`；子行只允许 `C-01.3` 形式且父 claim 类型必须是 `struct`；`struct` 行不得计入 `closed` 分子 | G2 | 合法的"一个 struct 覆盖 N 行呈现"（M-6 的 21 行表）会被误伤 → 只在 `struct` 行声明了 `覆盖: C-01..C-21` 时放行 |

### 4.1 判据的落地成本（为什么说"廉价"）

- 全部判据都是**字符串/正则/文件 stat/行计数**：无 LLM、无 AST、无网络。最贵的一条是 B-6 的 trace 计数（读一个本地 `trace.log`）。
- 判据所需的三个事实源都已存在：`trace.log`（`output-writer.ts:572-577` 的 `[FLOW] <ts> <line>` 追加器 + `worker-mode.ts:3225` 的 `tool_call <name>`）、`read-scope.ts:31-32` 的 cap、`output-sections.ts:210` 的 H2 判定器（已处理 fenced block / blockquote / 别名，见 `:128-183`）。
- 唯一缺的字段是 trace 的 **path 级归属**（`tool_call` 只记工具名，`worker-mode.ts:3225`）。若 design 想让"引用路径必须是被读过的路径"成为硬判据，需要给该行加一个 `arg=<path>` 字段；否则只能用 §4 的上界判据（B-6）。**这是本卡对 AC-002 的实现级建议。**

## 5. `## 断言裁决` schema 建议

### 5.1 列定义（7 列，全部单行、无换行、无 HTML）

| 列 | 必填 | 语法 / 闭集 | 校验器（零成本） |
| --- | --- | --- | --- |
| `claim` | 是 | `^C-\d{2,3}(\.\d+)?$`；子行仅允许 `父.序号` 且父必须是 `struct` | 双向集合相等（`表 = 卡`，见 B-10） |
| `类型` | 是 | `cmd` / `grep` / `struct` / `manual` | 与卡内声明一致（§2.4 规则只做告警，不做拒绝） |
| `裁决` | 是 | `closed` / `partial` / `unverified`（AC-002 闭集） | token 相等 |
| `判定` | 是 | `成立` / `不成立` / `无法判定` | 与 `裁决` 的映射：`closed`→成立或不成立；`partial`→部分成立（渲染时按 `partial` 处理）；`unverified`→无法判定 |
| `证据` | closed/partial 必填 | 1–3 条 `ref`，`;` 分隔（§5.3） | 路径存在 / 行号上界 / 摘录命中 / 命令 verb 白名单 |
| `取数` | 是 | 非负整数 | `Σ取数 ≤ min(卡 Σ预算, read file cap)`；≤ trace 的读类 `tool_call` 计数（B-6） |
| `原因` | unverified 必填 | 7 词闭集（§5.4） | token 相等 + 事实对账（B-2） |

**为什么把 `裁决` 与 `判定` 分成两列**：语料里"关闭/未关闭/部分关闭"（`ds-qg-review-2/task.md:29`）、"成立 / 部分成立 / 不成立"（`t18-adversarial-qg/task.md:29`）、"PASS/FAIL"（`acb-v1/task.md:22`）是**两个正交轴**：`closed` 只表示"这条断言已被证据结算"，不代表"断言成立"。若混成一列，`closed` 会被读成 PASS——这正是 §6 要堵的后门。

### 5.2 裁决 token 闭集与语义

```text
closed    = 证据已取到，且判定已定（成立 或 不成立）——两者都算"已结算"
partial   = 取了部分证据，覆盖了命题的一部分（必须写覆盖比例，如 3/6）
unverified= 命题未被结算（原因闭集见 §5.4）；不得计入 closed 分子，也不得静默当 0 分
```

禁止同义 token（`done` / `PASS` / `ok` / `verified` / `N/A`）：`N/A` 必须落成 `unverified: out-of-scope`，`done` 必须落成 `closed`。理由：语料里已经出现三种词表并存（`关闭/未关闭`、`PASS/FAIL`、`✅/⚠️/❌`），不收敛就无法聚合度量（`spec.md:81` 的 `tokens_per_closed_claim`）。

### 5.3 证据引用语法（精确形式）

```text
ref       := pathref | cmdref
pathref   := path ":" line ["-" line] ["「" excerpt "」"]
cmdref    := verb " " rest " => " result

path      : 仓库相对路径；禁止 "./" 前缀、禁止 ".."、禁止绝对路径；必须 exist
line      : 1 基；a<=b；b-a<=200；b <= 文件行数
excerpt   : <=60 字符，标记内逐字（归一化空白后）必须出现在所引行/行段
verb      : node|npm|npx|python|python3|pytest|vitest|git|mw|rg|grep|bash
result    : "rc=" [-]digits [" " key "=" value ...]      # 例: rc=0 passed=12
```

- **禁止** `&&` / `;` / `>` / 反引号出现在 `cmdref` 内（防"半条命令"式证据）；需要管道/重定向时写 `bash -lc '<整串>'`，其结果行同样必须带 `rc=`。
- `path:line` 与 `cmd => rc` 是**两类**证据，不能互相顶替：`cmd` 类 claim 必须给 `cmdref`；`grep` 类 claim 必须给 `pathref`（或 `cmdref` 里 verb=`rg|grep`）。`struct` 类 claim 必须有 1 条 `pathref` 指向被裁决的表/报告本身。
- 可选钉定：`path:line#sha8`（所引行文本的 sha256 前 8 位）。用途：跨 run 复评时检测行号漂移（本语料 12 张复评卡在高频改写文件上工作，`ds-qg-review-2c/task.md:72-75` 的锚点已出现行号漂移：卡写 `decision-tool.ts:640`（四键透传注释），而 `missingDecisionStateFields` 实际在 `:296`）。

### 5.4 `unverified` 原因词表（7 词，kebab-case，单源）

| 词 | 含义 | 必须附带的事实对账 |
| --- | --- | --- |
| `budget` | 取数预算耗尽 | 该 claim `取数` == cap（`read-scope.ts:31` = 8）或 trace 有 `read_scope: blocked` |
| `no-access` | 角色无该工具 | `TOOL_ALLOWLISTS[type]` 不含该工具（review = `read,find,grep,ls`） |
| `not-found` | 定位目标不存在 | 另一条 `grep => count=0`（或 `path` 不存在） |
| `ambiguous` | 二选一无法消歧，需人工 | 必须给出两个候选与各自证据 |
| `environment` | 平台/环境基线（如 Windows 89 失败基线） | 失败用例名 + 基线来源 |
| `out-of-scope` | 卡 `未覆盖面声明` 已列入 | 引用该声明行 |
| `awaiting-input` | 依赖 PM/人类提供证据（签名、裁决、外部事实） | 指向待签署/待裁决文件（如 `evidence/review/` 之外的 signoff 通道） |

设计要点：这套词的命名风格与 `ESCALATED_REASONS`（`packages/multi-workers/decision_points.py:111-120`，7 值：`disabled/unavailable/input-incomplete/input-oversize/low-confidence/over-authority/p0`）一致——**同一仓库里已有"7 值闭集 + 单源"的成功先例**，且该先例的教训是"两个模块各写一份就漂移"（同处注释：`decide_archive._ESCALATED_REASONS` 校验同一集合，避免归档侧同义词）。claims 侧必须同样单源（TS/Python 各一份会被 `test_autopilot_l0.py` 式平价锁抓住，见 `mw-rag-integration-ref-verify/task.md:30` 的 T-17 平价锁先例）。

### 5.5 10 行示例表（3 行本卡实测，7 行为形态示例）

> claim id 为占位；标记 `[实测]` 的行由本卡实际读取核过，`[形态]` 行只演示字段形状，**不是**对被测命题的裁决。

| claim | 类型 | 裁决 | 判定 | 证据 | 取数 | 原因 |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 `[实测]` | grep | closed | 成立 | `packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-card.ts:191「REVIEW_EXTRA_SECTIONS」` | 1 | - |
| C-02 `[实测]` | grep | closed | 成立 | `packages/multi-workers/decision_points.py:111-120「ESCALATED_REASONS」` | 1 | - |
| C-03 `[实测]` | struct | closed | 成立 | `packages/coding-agent/src/extensions/agent-team-loop/worker/output-sections.ts:48`;`:54` | 1 | - |
| C-04 `[形态]` | cmd | closed | 成立 | `node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-signoff.test.ts => rc=0` | 2 | - |
| C-05 `[形态]` | grep | closed | 成立 | `packages/coding-agent/src/extensions/agent-team-loop/pm/decision-tool.ts:296「missingDecisionStateFields」` | 1 | - |
| C-06 `[形态]` | struct | partial | 部分成立 | `evidence/quality-gate-report-20261020c.md:12-40` | 2 | 覆盖 3/6 |
| C-07 `[形态]` | manual | unverified | 无法判定 | `-` | 0 | `ambiguous` |
| C-08 `[形态]` | grep | unverified | 无法判定 | `-` | 0 | `not-found` |
| C-09 `[形态]` | cmd | closed | 不成立 | `node ../../node_modules/vitest/dist/cli.js --run test/suite/dp2-narrow.test.ts => rc=1 failed=2` | 2 | - |
| C-10 `[应拒]` | grep | closed | 成立 | `report.md:12「已核对」` | 1 | - |

C-10 是 §4 B-1 的形态：语法全合法、语义为零（证据指向本报告）。这类行必须由 G2 的"自证集合"判据拒掉，而不是靠人读出来。

### 5.6 解析容差（P-048 教训）

- 表头别名：`claim` / `断言` / `Claim`；`裁决` / `verdict`；`证据` / `Evidence`。列顺序任意，多余列忽略（`spec.md:88`：P-048 的 schema 过严导致连续误拒 30 分钟零产出）。
- 全角/半角：`：`→`:`、`｜`→`|`、全角数字归一。
- fenced code block 内的表不计（复用 `output-sections.ts:128-183` 的 fence 状态机，`h2Headings` 已实现同一语义）。
- 缺表或 id 不全 ⇒ **一次** self-check steer 后仍缺才 `exit 2`（`worker-mode.ts:3962-4008` 的既有一次性机制，`selfCheckSent` 每进程一次）；不得新增终态、不得静默 `done`（AC-002）。
- 兼容结论：`## 断言裁决` 若写成 `## 断言裁决（claims）` 仍命中（H2 别名匹配是 `includes`，`output-sections.ts:186-188`）。

## 6. `manual` 档位定义（防止变成"写完就 PASS"的后门）

### 6.1 计入预算的方式

| 规则 | 值 | 理由 |
| --- | --- | --- |
| 单条 manual claim 记账 | **2**（grep/cmd/struct 记 1） | manual 不吃 worker 取数，但吃 PM 注意力；双倍记账让"批量转 manual"立刻撞 cap |
| 卡级 manual 上限 | `min(4, ceil(claims/3))` | 26/104（25.0%）的语料占比说明 1/3 是自然上界；超过即不是"审查"而是"评审" |
| `Σ预算 ≤ 角色上限` | 沿用 AC-001 的 40（`spec.md:77`） | manual 已双倍计，无需再单独设上限 |
| 超限处置 | 派发拒绝（G1），拒绝原因含 `manual-overflow: k/n` | 与 AC-001 的"零副作用"一致 |

### 6.2 允许的裁决值

| 裁决 | 允许？ | 条件 |
| --- | --- | --- |
| `unverified` | **默认且唯一允许由 worker 自行给出** | 原因 ∈ {`ambiguous`, `awaiting-input`, `out-of-scope`, `environment`}；`budget`/`no-access`/`not-found` 对 manual 不成立（manual 的定义就是"工具面不缺，缺判断"） |
| `closed` | 允许，但**必须机器可验地引用人工裁决** | `证据` 必须是 `path:line` 指向一份**人类签字产物**（signoff/review 文件的裁决行）+ `判定` 必须与该行一致；worker 自己写下的"我认为成立"不得作为证据 |
| `partial` | **禁止** | manual 没有"部分取证"的概念；要部分就去拆成可机检子 claim |

### 6.3 覆盖表里的呈现

覆盖表（PM 侧聚合，非 worker 自评）必须按档位分列，且 PASS 判定不得把 manual 折叠掉：

```text
| 档位    | claims | closed | partial | unverified | 计入 closed 分子 |
| machine |    n1  |   c1   |   p1    |     u1     |       是         |
| manual  |    n2  |   c2*  |    0    |     u2     |       否         |   * c2 仅在引到人工裁决时成立
PASS 条件：n1>0 且 (c1/(n1)) >= 阈值 且 (c2 == n2 或整体结论显式降级为 PASS-WITH-FINDINGS)
```

- `manual` 的 `closed` **不进** `closed` 分子（否则 `tokens_per_closed_claim` 被人工裁决稀释，`spec.md:81` 的跨 key 可比性失效）；单独输出 `manual_ruled = c2/n2`。
- 顶层结论行必须打印 `manual=K/N`。若 `n2/n > 1/3`（理论上被 G1 拦住，但复评/补卡可绕过 G1），PM 侧仍须强制把结论降为 `PASS-WITH-FINDINGS`。
- `manual` 的 `unverified` **不得**当 0 分或 1 分参与任何比率；它只参与"是否有人裁决"的计数。

### 6.4 反后门四条（都可零成本校验）

1. **全 manual 卡不可派发**：`n1 == 0` ⇒ G1 拒绝（`no-machine-settleable-claim`）。否则"把 6 条要求全标 manual"就能让任何卡通过。
2. **worker 不得自封 manual 的 `closed`**：`closed` 的 manual 行必须引用**非本 run 产物**的人工裁决行（同 §4 B-1 的自证集合），否则降级 `unverified(awaiting-input)`。
3. **manual 不得携带取数**：`取数 > 0` 且 `类型 == manual` ⇒ 拒（说明它在假装取证；要么取证后转 machine，要么保持 0）。
4. **manual 的 `判定` 不得由 worker 自封为 `成立`**：worker 侧只能 `无法判定`；只有引用到人工裁决行（§6.2 的 closed 条件）时才可写 `成立/不成立`。这条是"写完就 PASS"的直接封堵。

## 反例集

19 条：9 条误拒（M-1…M-9，真实卡文）+ 10 条绕过（B-1…B-10）。

| # | 反例（语料出处） | 为什么会误拒 / 被绕过 | 拦住它的判据（或应放宽的规则） | 误伤风险 |
| --- | --- | --- | --- | --- |
| M-1 | 回归审计：是否引入**新的** fail-open（`ds-qg-review-2/task.md:36`） | 全称否定 + 无枚举源 + 预算无界（read cap 8，`dispatch.py:224-250`） | 归 `manual`；`反证条件` 允许抽样式；`预算` 允许 manual 档 | 若强行机检，只会留下"新增行 grep count=0"这种弱断言，得出假 PASS |
| M-2 | 「逐条列出**所有**会写盘语句」（`mwg-qg2b-code-adversarial/task.md:30`） | "所有"无 ground truth；判据"逐条列出"非命令 | struct 的 `反证条件` 必须指名枚举源（哪条 grep 产出全集） | 枚举源本身漏模式（如 `Path.write_text` 之外的 `os.replace`）→ 判据自身有洞 |
| M-3 | 「逐条给 PASS/FAIL」（`acb-v1/task.md:22`、`t18/task.md:29`） | 一条 claim 同时承担形状与内容 | 拆成 1 struct + N 原子 claim；id 允许 `C-01.3` | 拆得过细 → claim 数膨胀撞 40 预算；需允许"结构覆盖"写法（B-10 的放行分支） |
| M-4 | 设计质量三选一（`design-critique/task.md:24,30,35`） | 反证条件是"命名被忽略的替代方案"，开放输入 | `manual:` 前缀 + 二选一 + 裁决落盘坐标 | 二选一写不好会退化成"看过即通过"→ 必须要求裁决行 |
| M-5 | 开放审查请求，无命题（`code-review-1/task.md:11-18`） | 整卡是任务描述；K1-K4 无可证伪形 | 卡级 triage 先产 claims（AC-001 需 `claims_pending: triage` 豁免） | 豁免会被滥用成"永远不产 claims"→ 需 TTL（1 轮） |
| M-6 | 21 行引用核对表，存在?/语义一致?（`ref-verify/task.md:7-10,43`） | 每行命题不同，1:1 化超 40 预算 | 1 struct 携带格级摘录判据 + 只对高风险行开 manual | 摘录判据只验"行里出现了这段字"，不验语义 |
| M-7 | 「不重跑 pytest/vitest」（`review-fallback-cli-r2/task.md:55`） | 反证是 trace 事件，`path:line` 无合法取值 | 定位域加 `run:trace.log`；判据 `grep trace :: tool_call (bash|pytest|vitest) => count=0` | trace 只在有 bash 时记录 → review 角色天然 0，判据退化为恒真（诚实标注：该约束本就不适用于 review） |
| M-8 | 假绿/不可达证明（`wjg-w15/task.md:49,52`、`t18/task.md:37`） | 负结果不可作为 closed 证据 | 归 manual + 强制 `攻击尝试=N` + `unverified(ambiguous)` | "找不到反例"被当成证明（卡文 `:32` 已明令禁止） |
| M-9 | 「抽样 ≥3，证明行为级而非镜子级」（`ds-qg-review-2/task.md:38`） | `>=3` 通过校验但质量未判 | 改写成 3 条变异测试 cmd（`mutate => rc!=0`） | 变异点选错 → 用例仍红，得到假"行为级"；需固定变异算子 |
| B-1 | 复制 id + 自证证据（`report.md:12`） | id 齐全、`path:line` 合法 | 自证集合静态排除 + 路径存在 | 引用 `progress.md` 的合法中间记录会被误伤 → 允许作二级证据 |
| B-2 | 全标 `unverified` | AC-002 只要求"有原因" | 角色化比例上限（review ≤60%，coding ≤10%）+ 7 词闭集 + 事实对账 | 真·无 bash 的 review 卡合法大量 `no-access` |
| B-3 | 不存在的行号 / 行号漂移 | `path:\d+` 正则通过 | 行号上界 + 可选摘录命中（strict） | 评审期间文件被其他 worker 改写 |
| B-4 | 证据只写 `output.md`/`report.md` | 四段契约只管段落 | 同 B-1；`closed` 需 ≥1 条非本 run 产物 | 纯文档审查的合法证据就是被审文档（非本 run 产物，OK） |
| B-5 | 同义反复（陈述≈反证条件） | 六要素非空 | 去否定后 token 相似度 ≥0.90 且无新 artifact ⇒ 拒 | 最小改写本就只差否定词 |
| B-6 | 表格齐全、零取证 | 取数无校验 | `Σ取数 ≤ min(Σ预算, read cap)` 且 ≤ trace 读类 tool_call 计数 | 一次 bash 多读 / `ls` 一次多文件 → 只能作上界 |
| B-7 | 复用上一轮裁决 | 内容与行号都真 | 证据 mtime > task.md mtime，或显式 `carried-from:` | 代码未变（mtime 更旧）是合法情形 |
| B-8 | extras 兜底文本（`launcher.py:1867-1875`、`dispatch.py:467-469`） | extras 只查名字出现 | 含 `[ENVELOPE_FALLBACK]` ⇒ 视为缺失；`审计目标:` payload 需含锚点 | 合法短目标会被锚点要求拒 |
| B-9 | claim 退化成"文件存在" | 四要素齐全且判据可执行 | `陈述` 需非存在性谓词 | 唯一证据文件类 claim 正当就是"存在" |
| B-10 | 一条 struct 吞掉 N 条原子 claim | AC-002 只约束一个方向（卡 ⊆ 表） | id 双向包含 + 子行 `父.序号` + struct 不计 closed 分子 | 合法的 21 行表需 `覆盖: C-01..C-21` 放行 |

## 未找到清单

| # | 未找到的东西 | 命令 | 输出 |
| --- | --- | --- | --- |
| 1 | 真实的 `<!-- mw-claims: v1 -->` 声明（任何卡/任何 worker task.md） | `rg -n --  mw-claims .agenticdoc packages` | rc=0，**仅 1 行**：`.agenticdoc/claim-driven-review/spec.md:77`（定义本身），实现与语料 0 处 |
| 2 | 结算期 `## 断言裁决` 的实现 | `rg -n -- 断言裁决 packages` | rc=1，**0 行**（纯 spec，无代码） |
| 3 | `claim_gate` 的实现 | `rg -n -- claim_gate packages .agenticdoc` | rc=0，**仅 1 行**：`spec.md:82` |
| 4 | review 卡里的 per-claim 取数预算 | 46 张 `type: review` worker 卡全文扫描 `取数` / `预算` | `取数` 1/46（`mw-rag-qg-review`，非预算语义）；`预算` 9/46 全部是**上下文 token 预算**（如 `ds-qg-review-2c/task.md:57`「全程上下文 ≤120k tokens」），不是取数预算 |
| 5 | review 卡把某要求显式标为 `manual`/`仅人工` 的先例 | `rg -n -- 仅人工\|\bmanual\b` 扫 3 个 key 的 `tasks/` | 1 行命中且不是档位声明（fixture 描述）⇒ **0 先例** |
| 6 | 只有 `output.md` 的 review run 里的 `[VERIFY]` 行 | 逐个扫描 12 个 output-only worker 的 `output.md` | **0/12**（另外 29 份 `report*.md` 中 17 份也没有） |
| 7 | trace 中的"读过的路径" | 读 `worker-mode.ts:3225` | 不存在：trace 只记 `tool_call <toolName>`，无 `arg=<path>`（故 §4 B-6 只能做上界判据） |

## 未覆盖面声明

- **只覆盖 `type: review` 的 worker 卡**（46 张）与 14 张 review 任务卡；`reviewer`/`verifier`/`rag-research`/`vision` 角色、以及 77 张"标题含 review 但 type 非 review"的卡未逐条拆单元（只在 §1.1 计数）。
- **未做端到端验证**：`mw-claims` 与 `## 断言裁决` 均无实现（`## 未找到清单` 1-3），本卡的 schema 与判据全部是**纸面推演 + 历史语料实测**，未在真实派发/结算链路上跑过。
- **未验证 `output.md` 的合并语义**：`output-writer.ts:556-569`（D-117）会把 agent 既有内容与 harness 段拼接；`## 断言裁决` 若被 agent 写在 `output.md` 且被 harness 再追加一次，是否会重复计行未测。
- **未覆盖合并单元（merge）**：AC-004 的"merge 只读各单元裁决文件"没有实现可测；`C-01.3` 子行在跨文件合并时是否会撞 id 未验证。
- **未覆盖英文语料之外的规则适配**：§2.4 规则对英文单元（K1-K7）几乎全部降级为 manual（`code-review-1/task.md` 7 条里 4 条），说明规则隐含中文词表。
- **未覆盖平台差异**：只在 Windows 开发机语料上统计；`path:line` 的大小写与短路径（8.3）行为未验证。

## 结论

1. 分类法必须以"最便宜的充分判据"定义，四类在 104 个真实单元上的分布是 21/28/29/26；仅人工占 25.0%，是不可消除的一档，不是缺陷。
2. 误拒的根因是**复合单元**与**缺通道**（21 个行为类命题里 11 个在卡里没有任何可执行串），不是要求本身太软；validator 必须允许 `manual:` 与"待定通道"，不得校验"判据可执行"。
3. 四要素的定位域必须扩展两处：`run:trace.log`（过程约束类）与"结构 claim 携带格级摘录"（大表类），否则 7 张卡的硬约束与 21 行引用表都无法 claim 化。
4. 绕过面用 4 条零成本判据可拦住 10 条绕过中的 7 条：自证集合排除、行号+摘录、取数上界（≤ cap 且 ≤ trace 读计数）、`unverified` 比例与原因对账。剩余 3 条（B-5 同义反复、B-7 复用裁决、B-8 extras 兜底）靠"去否定相似度 + mtime/carried-from + 兜底标记"三条字符串规则即可。
5. `manual` 通过"双倍记账 + 上限 min(4,⌈n/3⌉) + 只能 unverified/带人工裁决的 closed + 不进 closed 分子"四点封堵"写完就 PASS"；其中"worker 不得自封 manual 成立"是最关键的一条。
6. `裁决` 与 `判定` 必须是两列：语料里"关闭/成立/PASS"三套词表混用（`ds-qg-review-2/task.md:29`、`t18/task.md:29`、`acb-v1/task.md:22`），单列会把"已结算"读成"已通过"。

## 证据

| 论断 | 证据坐标 / 命令 |
| --- | --- |
| review 语料规模 46 / 14 | §1.1 的 glob + 前 20 行 `type:` 解析；对照 `dispatch-card.ts:203-208` 的历史口径 review 28 |
| extras 落地率 24/46 与 23/46 | 用 `dispatch-card.ts:257-263` 的同一正则扫描 46 张 worker 卡；任务卡 14/14 |
| 34/46 有独立产物、12/46 仅 output.md | 逐个 worker 目录 `report*.md` + `write_face` stat（`write_face` 为仓库相对路径） |
| 12/12 output-only 无 `[VERIFY]`、17/29 report 无 `[VERIFY]` | 文本扫描；与 `_pitfalls.md:71` 的"12 次 review 8 次未交出结论"同源 |
| 104 个单元的类分布 | §1.3 明细逐条 + `TEMP/mw_rq3_units.json`（本卡脚本） |
| 规则一致率 66/104、危险方向 1 | §2.4；规则源见 §2.1 代码块 |
| review 角色工具表无 bash | `mw-rag-integration-ref-verify/task.md:15`（`read,find,grep,ls`）；`mw-gate-verdict-hardening/.../mwg-qg2b:11`「没有 bash」 |
| read cap = 8 file / 65536 B | `read-scope.ts:31-32`；预算饥饿先例 `dispatch.py:233-238`（0/23、0/31） |
| 一次性 self-check + `recovery-gap` trace | `worker-mode.ts:3962-4008`、`:3972-3978`、`:3994` |
| 四段 + review 第五段 | `output-sections.ts:48`、`:54`；别名与 fence 语义 `:75-82`、`:128-183`、`:186-188` |
| extras 兜底可被绕 | `launcher.py:1867-1875`（`[ENVELOPE_FALLBACK]` 骨架）、`dispatch.py:467-469`（`审计目标: <prompt 首行>`） |
| 7 值闭集先例 | `decision_points.py:111-120`（`ESCALATED_REASONS`） |
| `output.md` 是 agent 回复 + harness 追加 | `output-writer.ts:556-569` |
| trace 只记工具名 | `worker-mode.ts:3225`（`tool_call ${event.toolName}`） |

## 残留与未验证

1. **§2.4 的规则不是 validator**：63.5% 一致率 + 1 个危险方向说明它只能做筛查；卡自报类 + 前缀校验才是可落地的实现（本卡建议，未实现）。
2. **B-6 的取数上界未在真实 run 上回放**：语料里没有 claim 数据，无法验证"trace 读计数 ≥ Σ取数"的实际通过率；只在 `output.md`-only 的 12 个 run 上确认了 0 次读 → 若这些卡有 claims 会全部触发该判据（即判据本身未被真实数据压力测试）。
3. **B-7 的 mtime 判据在复评卡上必然误伤**（`R-02` 整卡复评）；`carried-from:` 是补丁，未验证其在 12 张复评卡上的覆盖率。
4. **M-6 的"格级摘录"只验字面**：`ref-verify` 的"语义一致"仍需人工；本卡未给出任何语义级廉价判据（也不认为存在）。
5. **行号漂移未量化**：本卡只观测到 1 例（`ds-qg-review-2c/task.md:72` 的 `decision-tool.ts:640` 与实读 `:640`/`:296` 并存）；未统计 46 张卡里过时锚点的比例。
6. **`manual` 上限 min(4,⌈n/3⌉) 是经验值**：依据是 26/104 的语料占比，不是实测通过率。

## 上下文来源

- 抽样（全文读）：`workers/ds-qg-review-2/task.md`、`ds-qg-review-2c/task.md`、`ds-qg-review-2d/task.md`、`mwgal-t18-adversarial-qg/task.md`、`mwg-qg2b-code-adversarial/task.md`、`wjg-w15-delta-adversarial/task.md`、`acb-v1/task.md`、`mw-rag-integration-ref-verify/task.md`、`mw-rag-integration-design-critique/task.md`、`review-fallback-cli-r2/task.md`、`code-review-1/task.md`
- 契约与实现：`shared/dispatch-card.ts`（`:191`、`:203-208`、`:248-264`、`:457`）、`worker/output-sections.ts`（`:48-63`、`:75-82`、`:128-188`、`:210`）、`worker/worker-mode.ts`（`:2700`、`:3225`、`:3332`、`:3813-3833`、`:3962-4008`）、`worker/output-writer.ts`（`:526-570`）、`worker/read-scope.ts`（`:31-32`、`:180-212`）
- Python：`autopilot/dispatch.py`（`:224-270`、`:455-479`、`:600-640`、`:700-745`）、`autopilot/launcher.py`（`:1565-1592`、`:1867-1875`）、`decision_points.py`（`:83-120`）
- key 契约：`claim-driven-review/spec.md`（`:77-83`、`:88`、`:89`）、`tasks/RQ-3-claim-taxonomy.md`、`evidence/research/spec-rq0-research-plan-20261020.md`
- 坑库：`.agenticdoc/_pitfalls.md:63-73`（P-007）、`:499-507`（P-048）
- 统计脚本：`%TEMP%/mw_rq3_units.json`（104 单元 + 分类结果，本卡运行产物，非仓库文件）

[VERIFY] RQ3 cards=11 units=104 cmd=21 grep=28 struct=29 manual=26 misreject=9 bypass=10 review_workers=46 review_cards=14 extras_missing_audit=22 extras_missing_coverage=23 landed_product=34 output_only=12 verify_zero=12 rule_agree=66 dangerous=1
