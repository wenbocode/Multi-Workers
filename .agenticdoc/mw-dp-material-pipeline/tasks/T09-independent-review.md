type: coding
deps: [T08]

# T09 独立复核与最终验收材料

## 状态与上下文

planned，未派发。Key mw-dp-material-pipeline；控制/目标E:/gitlite/Multi-Workers。此卡使用coding仅为稳定落盘审查报告，实际只允许报告/evidence写入，不改被审代码。执行者必须不同于T01—T08及T10的实现/参考编制/自验者；PM在派卡时通过真实run/身份绑定核验，不接受自填“独立”。

目标锚点 `.agenticdoc/goal.md:3`。验收锚点 `.agenticdoc/mw-dp-material-pipeline/spec.md:70`。代码锚点 `packages/multi-workers/decision_model_context.py:115`。本次复核材料为更新后的 v0.5 对账、本轮 PM/Worker 普通工具与 Gate CLI 的隔离运行证据，保留旧 dp-auto 的历史待证。

## 目标及对应AC

AC-001—018；VC-014及015—018的现有v05范本、来源与PM参考充分性。历史实验与当前参考意见分开，不伪造历史生产采纳。

## 工作项与交付

1. 先落 evidence/review/t09-mw-worker-review.md 骨架，再逐AC/VC给met/not-met/unverified及具体原始证据；报告先结论/findings后矩阵，主报告<=120行，详证可分文件。
2. 核实际字段写者→读者、固定候选reopen、desc精确计量与限制、真实助手隔离/吸收、全部fix原因、原预算/continuity和原始返回可见。
3. 复验必要关键命令/负例，确认当前源码与T08索引一致；存在缺口如实不通过，不改源代码/标准/旧响应来“补绿”。
4. 交给PM检查真实独立身份、报告、实际diff和证据，只有全部必要证据成立才考虑完成。不可直接写正式QG/sign/索引或推进阶段。
5. 核8DP/9案例的完整决策本、实际payload、原始回包/反解与当前PM参考，源hash/ID/版本一致；缺历史执行回执仍为空。
6. 核两cohort、PM必须保留事实/禁止声明和已知QG/旧auto负例；不以confidence或自然语言逐字相等验收，不强制新真实采集。

## 依赖与已有证据

T08当前源码证据/check_review.py，T10参考校验与docs/reference-records原件，本key spec/design。缺当前实现证据应列缺口；参考数据已经存在，不再依赖T11。

## 写入允许面

- `.agenticdoc/mw-dp-material-pipeline/evidence/review/**`

## 写入禁止面

所有产品源码/测试、依赖/全局凭证、spec/design/原AC、docs原件、其它key、正式质量/签收writer与机器阶段。

## 验收命令

```json
["python", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/check_review.py", "--report", ".agenticdoc/mw-dp-material-pipeline/evidence/review/t09-mw-worker-review.md", "--spec", ".agenticdoc/mw-dp-material-pipeline/spec.md", "--evidence-index", ".agenticdoc/mw-dp-material-pipeline/evidence/acceptance/evidence-index.json", "--reference-index", ".agenticdoc/mw-dp-material-pipeline/docs/reference-records/index.json"]
```

## 完成判据与输出

上述验收器检查覆盖与证据链接。PM 另核真实审查 run 的独立身份和实质报告。VC-014 仅在全部当前 AC 证据和独立复核齐备时通过，缺项应明确记为 unverified。交报告与 output.md，后续修复由 PM 回派并重新复核。

## v0.5范本引用与逐项对比（必验）

按[八个 DP 同次对账](../decision-chain-reconciliation.md)在原证据中逐项正查及从回执反查。核所属事项、尝试、版本、角色和 writer 证据，覆盖串次、借回包或回执以及没有执行却写成功的负例。

跨项目回归见[典型四段对照](../evidence/dp-blocked/20261122/v05-blocked-comparison.md)。逐项核案例的已覆盖能力、仍待验证的运行结果和剩余缺口。检查四段无串版或伪造，确认来源分类和代表性附加回归记录。

共同输入：[范本索引](../docs/reference-records/index.json)、[四段全记录](../docs/reference-records/index.md)、[逐项对比合同](../reference-comparison-contract.md)。四段均须读取：决策本、模型输入、原始返回/同版反解、PM参考决策；主AC不变，本节按职责支撑AC/VC-015—018。

范围：全部9例、两个cohort。逐行复核36行及字段证据、PM处置/理由/必要事实/禁止声明；核差异依据和负例实际拒绝，不只核文件或choice。check_review经evidence-index读取完整报告。

未来验收按合同提交本卡负责字段的基准/当前观测、规则/结果、差异理由及原证据，进入T08的9例×4段共36行报告。原件字节只在回放模式严格相等；当前规范修正须解释差异，缺段/无依据差异/假执行不可通过。PM参考不是历史执行回执，实际接回仍由原主体负责。本文不运行验收命令、不新增调用/派发。

## 改动历史

- 2026-11-22 补全正式派发所需锚点和机器写面。独审应先核四项修复的真实负例，再核 Gate 同次接回和 36 行差异。若旧 dp-auto 的历史回执仍为空，记为 unverified。另存独审报告 `.agenticdoc/mw-dp-material-pipeline/evidence/review/t09-mw-worker-review.md`，在本次 run 的 output.md 引用。不得覆盖先前独审、改变验收条件、用合成回包声称实时模型验收或执行实际 Gate 动作。
