# v0.5四段范本逐项对比合同

状态：规划复核修订，未实现。本文是spec AC-015—018、design VC-015—018及T01—T10共同引用的验收合同；不新增API调用、派发或实施授权。

## 唯一范本入口

[范本索引](docs/reference-records/index.json)列出8类DP、9个唯一案例及两个八DP组合；[阅读入口](docs/reference-records/index.md)。[acceptance-samples.json](acceptance-samples.json)只引用这套资产，不另造一套样例。相对路径以包含该路径的索引文件所在目录为根；case.source_capture以docs/为根，case.reference以本key为根。

每例目录中的decision-book.json、model-input.json、model-return.raw.json、pm-reference-decision.json分别为四段原件；reference-chain.json包含同版pair_map、official_decode、local_decode、original_host_checks；expected-checks.json规定wire、业务choice、basis、全部原因/剩余项、PM必要事实/禁止声明与已知材料缺口。所有这些范本均只读。

## 每例必须逐段核对什么

| stage_id | 段 | 基准文件/字段 | 逐项对比内容 | 责任 |
| --- | --- | --- | --- | --- |
| decision_book | 决策本 | decision-book.json；chain.local_book/pair_map | 来源、目标/偏差、准备与本地约束、字段追溯、完整候选/合法配对；哪些字段发送、哪些仅本地、实际落点；合成来源不得冒充生产身份 | T01/T02/T03/T04 |
| model_input | 模型输入 | model-input.json；chain.model_input | 历史请求原字节/hash；当前producer实际投影的model/state/questions、desc、material、引用/术语、全部单选判据；本地过程/actionplan/expected不整体入模 | T02/T03/T04/T05/T06 |
| model_return | 原始返回及反解 | model-return.raw.json；chain.model_return/official_decode/local_decode | 原字节/hash、model/answers/id/usage、confidence和probabilities分别保留；同版wire→choice/basis/全部finding_ids/remaining_ids；无遗漏、无跨版本套用 | T01/T06 |
| pm_decision | PM/原主体接回 | pm-reference-decision.json；expected-checks.json | disposition、采纳/退回理由、required_pm_facts、全部原因/剩余项、后续动作、待核条件、forbidden_pm_claims及真实执行状态；w-check自评仍由实际Worker负责 | T05/T06 |

T07核四段在回放中的可见性、内容一致和发送标记；T10交付对比器/报告合同；T08合并生产链实际观测与差异报告；T09逐项复核四段和差异依据，不能只看总分。

## 两种对比必须分开

1. **原件回放**：9例均读取四段原件，JSON值与chain同字段相等；请求/原始响应必须与来源字节/hash一致。同版pair_map重建wire与全部原因，保留实际ID、usage和两个独立概率指标。第四段按当前参考裁定的真实类别读取，不能写成历史生产PM结果。
2. **当前实现对照**：用当前真实producer/handler和隔离来源、faux传输驱动，保存实际材料/请求或发送前拒绝、原始返回/反解及接回观测。逐字段列基准值、当前值和差异；协议字段、动态身份/时间/模型响应ID等变化须有路径级规则，不能要求当前结果复制历史字节，也不能用“版本不同”忽略整段。合成来源及测试替身必须标明，不声称真实生产独审或执行。

T10先交付只读原件检查、报告schema及校验测试，不等待T03—T07完成；T08在相关实现完成后生成当前实现的完整对照。T01—T07提交本卡负责字段的实际证据，不能用重复读取范本代替生产链验证。

修正材料产生新payload时，历史回包仅能绑定历史请求并单独回放反解；当前payload的响应只能来自该次隔离faux传输，标明来源，不能宣称新jev实测。没有响应时记录明确状态，不补造回包。

## 已知负例如何验收

- dp-QG历史payload缺reopen：原件回放仍应精确得到fixB、F1/F2；当前发送校验应拒绝该不完整材料。补齐候选的新请求单独标版本并用faux验证，不能沿用旧回包作为新请求结果。
- dp-auto-original缺目标取舍/完整路径：原件回放保留retryA、confidence=0.16及实际概率；当前准备应报告缺口并由原主体接回，不把低confidence本身当唯一拒绝原因。
  - 旧案第四段的历史回执保持 `null`。当前验收用同一负例在 PM 正常入口产生的发送前拒绝和会话接回记录，关联本次阻塞事件及 PM 的身份与事项。记录退回理由、负责接回的 PM、补齐优先级和有界路径的下一步，并核对零发送、未执行及原只读授权、时间和重试上限。以上观测成立时第四段为 `expected-rejection`。
- dp-auto-optimized含新增目标/事实：独立案例比较，不能倒填旧auto或声称同事实confidence提升。它自身仍须通过当前前提、路径及预算检查，不能凭历史confidence=1判业务通过。
- 其余案例不是无条件合规豁免；若当前合同另检出真实缺口，应列具体字段、AC和观测，不复制历史缺陷、不强凑全部正例。

发送前拒绝案例的当前model_input段记录实际候选材料及诊断、network_attempts=0；model_return段记录当前response=null和未发送原因，并另引用历史原始返回/同版反解检查；pm_decision段记录真实拒绝/接回结果。三段都不得省略。该类只有实际观测符合对应预期且理由明确，才能记expected-rejection。

## 未来验收报告必须交付

[八个 DP 同次对账](decision-chain-reconciliation.md)补充 AC-012/014/015—018 的执行核对。四段仍为 36 行，第四段分列原主体接回、适用 writer 及实际回执。已发、未发送和本地结果按实际来源关联。

T08输出evidence/acceptance/v05-four-stage-comparison.json和同名.md，T09的check_review.py通过evidence-index引用并核验二者。以下是报告合同，不是已生成的实施结果。

- 每个唯一案例固定4行，总计9×4=36行；两cohort只引用case_id，不把共用七例重复计数。所有四段均须有原件回放结果和当前实现对照结果；阶段全为空、缺行、重复行都失败。
- 每行至少有case_id、stage_id、source_schema、reference_path/hash、reference_result、implementation_result、field_checks、status、ac_ids、vc_ids、evidence_refs。
- field_checks逐项包含字段路径、基准值/原件指针、当前观测值/证据指针、比较规则、结果、差异理由及对应AC/VC。覆盖已比较字段和仅本地/发送/改名/新增/删除字段；source_trace给出模型字段来源及发送落点，不能只写“全部相同”。大文本可用带hash的本地产物指针，实际内容必须可读取。
- status仅用matched、justified-change、expected-rejection、fail、unverified。justified-change必须有具体AC/VC、字段级理由、当前观测和审查结论；fail/unverified/缺证不能计通过。自然语言PM裁定按必要语义审查，不要求逐字相等，不以字符串包含或confidence替代人工核对。
- PM部分同时保存参考裁定和当前接回观测，逐条检查处置方向、理由、必要事实、禁止声明及后续边界；脚本只证明结构/机械条件，语义审查由真实PM及独立复核者记录。实际dispatch/writer/production_executed没有发生仍为空/false，离线测试成功不改成已执行。
- 报告绑定当前spec摘要、源码快照、目标工作区、执行者、命令/时间/退出码、原日志和输入/配对版本；每项差异能追到原件与当前观测。T09复核9例×4段全部36行及两cohort，不以抽一例、只检查文件存在或只核最终choice替代。

验收要求是36行完整且结论逐项成立，不要求为了“36通过”删未知或放宽合同。尚有fail/unverified时保留缺口，不宣称本key完成。当前仅核本文及引用一致，产品报告和测试仍not-run。
