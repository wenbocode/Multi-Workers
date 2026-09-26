# Spec: mw-l3-fail-marker-forms

## §0 Goal Alignment

- **对齐**: goal.md 的核心是「PM Agent 管理多 Worker 并行开发的协作框架」。L3 质检裁决是 PM 闭环的信任基座——false-meets 让 PM 把未达标当达标结案，直接破坏该基座。本 key 修复 FAIL 标记识别过窄（三形态只覆盖一形态），属于 conductor 裁决可靠性主线。
- **GC 继承**: 无活跃 GC 冲突；与 mw-done-closure-repair（d20a270d5，done 收口回流）同域不同面——那把「该 below 的救活」，这把「该 below 的误判成 meets」，方向互补。
- **冲突**: 无。不触碰 verdict 转写（D-108）、freshness（1b2a1efde）、closure repair（d20a270d5）的语义；只放宽 FAIL 检测的召回面并加否定语境豁免。
- **预期收益**: false-meets 归零（reviewer 写 FAIL 的任何自然形态都判 below）；解锁 E2Feature 侧 `feature-false-meets-remediation`（全量复算 + append-only 更正）；消除依赖图污染源头（E2 已有 2 个 false-meets DONE key，17 项未达成被当达成）。

## 1. 背景与问题

L3 verdict 解析的 FAIL 检测 `_L3_FAIL_RE = re.compile(r"\|\s*\**\s*FAIL\b")`（a0c36fccc 引入）只匹配管道表格单元格（含加粗）。真实事故（E2Feature，2026-09-25 确证，reflect 台账 `l3-fail-marker-detection-too-narrow.md`）：

- `feature-inline-marker-patchkit` l3-a3：8 处 `| **FAIL** |` → **已覆盖**（a0c36fccc 后）；
- `feature-sampling-human-channel` l3-a1：TL;DR `FAIL — 21/30 VC 通过，9 项失败`、汇总 `- **FAIL：9**` → **仍漏检**，false-meets 结案 DONE。

危害：stalled 损失时间，false-meets 污染事实面（verdict/roadmap/dossier 全链自洽地错）。同型误判轮次 E2 侧已登记 7 个（F-3/F-4）。证据：`evidence/research/spec-incident-fail-forms-20260925.md`、`spec-decision-space-20260925.md`。

## 2. 验收标准

- **AC-001（事故形态全覆盖）**: 四种 FAIL 形态——朴素管道 `| FAIL`、加粗管道 `| **FAIL** |`、中文冒号项目符 `- **FAIL：n**`、结论行散文 `FAIL — …`——以 E2 真实事故样本逐字回放，全部判 `below`。
- **AC-002（否定语境零误伤）**: PASS 报告中的 FAIL-相邻否定文本（`FAIL 行 0`、`0 FAIL`、`failed=0`、`needs-rerun=0`、`无 FAIL` 等，以真实语料编目）不触发 below——用例表须逐条源自编目语料（file:line 引用），不得凭空构造后自证。
- **AC-003（存量零回归）**: 默认套件对照基线全绿（基线 = 927 passed + 2 外域先在，见 mw-done-closure-repair T-09 证据）；`e2e_l2` 7/7 保持。
- **AC-004（判定组合语义）** [REVISED 2026-09-25，评审 MINOR-6：原文「FAIL 与缺节并存时的优先序与现状一致」与 D-003 洗白洞修复冲突，按 key-decision D-003 裁定修订]: source fallback 两源（output.md → report.md）上 FAIL 检测语义一致；**FAIL 否决优先于合规性判定**（任一可读源命中即 below，含非合规源）；两处均缺必需节仍判 below；verdict 值域与事件类型集不变。
- **AC-005（below 留痕可区分）**: 因 FAIL 命中判 below 时，verdict 记录/timeline reason 能与「缺节 below」区分，并携带首个命中行样本（供 remediation 复算与人工复核）。
- **AC-006（e2e 集成）**: e2e 全链含一个 bold-FAIL reviewer stub 轮，判 below 且走既有 stalled/repair 路径，不产生 false-meets DONE。
- **AC-007（判据文档化）**: 形态表 + 否定豁免表落 CHANGELOG [Unreleased]；教训（判据 vs 表达措辞差）落 `_pitfalls.md`。

## 3. 非目标

- 不修 E2Feature 侧 false-meets 后果（其 `feature-false-meets-remediation` 自担，依赖本 key）。
- 不改 reviewer 提示词协议（方案 3「机器裁决行」记为后续可选增强，另行评估）。
- 不处理历史 `l3-verdict.txt` 污染的回填（freshness 语义已有 1b2a1efde 管；历史更正属 remediation 域）。
- 不动 verdict 转写（D-108）、closure repair（d20a270d5）路径。

## 4. 可复用资产

- a0c36fccc 的 `_L3_FAIL_RE`/`_L3_SOURCE_ORDER` 测试基建（verdict 解析用例直接扩展）。
- d20a270d5 的 e2e stub reviewer 模式（test_autopilot_e2e.py 内嵌响应分支）。
- E2 reflect 台账的真实语料指针（marker l3-a3 / sampling l3-a1 / mvp-closeout 38 处朴素管道）。
- `_md_section` 节提取机制（结构化扫描面可复用）。

## 5. 需规避坑点

- **P-013 同型**（判据与提取边界措辞差）：扫描面若依赖节提取，必须先核 `_md_section` 的 H2 截断边界；TL;DR 不在两节内，需显式纳入。
- **误伤方向也是损失**：把真 PASS 判 below 会制造 stalled + 人工闸门（回到时间税）；豁免表必须语料驱动，禁凭空构造。
- **A-03 教训**（产出形态随机）：不能指望「reviewer 会写对格式」——检测面按「所有自然形态」设计。
- **幂等/消费语义**：不重复消费既有 verdict 事件；本 key 只改解析判定，不新增事件类型（AC-005 的 reason 增强除外）。

## 6. 风险与开放问题（design 阶段 RQ 输入）

- 扫描范围现状（全文 vs 提取节）——RQ-1；
- 否定语境真实语料面——RQ-3；
- mvp-closeout 朴素 `| FAIL` 轮内否定行互作——RQ-3；
- below 留痕现状粒度——RQ-1；
- 三形态 + 豁免的正则/结构组合设计——RQ-1/2/3 汇合后 design 定。
