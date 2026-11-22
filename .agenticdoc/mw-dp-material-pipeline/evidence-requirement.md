# Evidence Requirement: mw-dp-material-pipeline

状态：规划v3；产品实现/独审仍not-run，现有v0.5四段参考资产已整理并明确来源。spec为draft，无用户锁定时间；AC-015—018按用户澄清修订为已有记录范本/对比/校验，不要求先新采真实运行。

## 指纹与证据绑定

实现前冻结实际spec摘要及AC内容、目标工作区、源码摘要、注册表/材料合同版本；每条证据保存原始命令/参数/目录/起止/退出码、assert与实际[VERIFY]输出、run/执行者和限制。本文不提前写虚构源码hash或passed。最终批次修改后重验。

| AC | VC | 必须取得的证据 | 主卡/复核 | 当前 |
| --- | --- | --- | --- | --- |
| AC-001 | VC-001 | 八DP真实注册源/生成消费，固定闭集完整；QG缺reopen和单候选拒绝，auto边界 | T01/T09 | not-run |
| AC-002 | VC-002 | 限定来源真实正文→投影；仅路径/超限/删失败/未读反例与压缩保留项 | T02/T09 | not-run |
| AC-003 | VC-003 | 10/11句与精确1000/1001边界，计量未知零假通过，计量器来源合同 | T03/T09 | not-run |
| AC-004 | VC-004 | 真实producer产生全部模型字段的trace；本地metadata/actionplan零泄漏 | T03/T09 | not-run |
| AC-005 | VC-005 | AC正文/缩写/代码闭包；同ID错对象/冲突/悬空负例 | T03/T09 | not-run |
| AC-006 | VC-006 | 当前独审逐AC/VC，fail/not-run保留；错/旧QG不能finalize | T05/T09 | not-run |
| AC-007 | VC-007 | 注册工具/profile实际越序/越范围/换模型/旧版/半发布拒绝及合法吸收 | T04/T09 | not-run |
| AC-008 | VC-008 | 全1..10对比较；缺偏好/等价具体状态，固定候选不私删 | T05/T09 | not-run |
| AC-009 | VC-009 | 路径停止/上限/次数、循环/重复/超预算、执行前余量复验 | T05/T09 | not-run |
| AC-010 | VC-010 | 真实接回合法fix多原因完全一致，未知wire/错revision零业务采纳 | T06/T09 | not-run |
| AC-011 | VC-011 | 原matter并发/时间戳去重、账本连续、transport-unknown零盲目补发 | T06/T09 | not-run |
| AC-012 | VC-012 | 完整Request.data与response原字节/id/usage，UI默认入口可见截图及未执行状态 | T07/T09 | not-run |
| AC-013 | VC-013 | 关闭/失败/取消/不可用原continuity合法接回，零新审批/全局等待/冒充 | T06/T09 | not-run |
| AC-014 | VC-014 | 当前源码AC证据齐全，必要检查如实，另一执行者真实run独立报告与PM复核 | T08+T09 | not-run |
| AC-015 | VC-015 | 八DP四段参考/9个唯一案例，历史输入/返回原件一致，当前PM参考另标来源 | T10+T08/T09 | 参考资产已整理；实现消费/独审not-run |
| AC-016 | VC-016 | 原版/整合版cohort不串版，9份PM参考理由/原因/后续/禁止声明及事实变化对照 | T10+T08/T09 | 参考资产已整理；实现消费/独审not-run |
| AC-017 | VC-017 | 9份expected-checks与实际wire/basis/全部原因匹配，QG和旧auto已知负例不放宽 | T10+T08/T09 | 参考资产已整理；实现消费/独审not-run |
| AC-018 | VC-018 | 历史与当前参考类别明确，缺失生产PM/执行回执仍为空，无新调用/派发/伪造 | T10+T08/T09 | 参考资产已整理；实现消费/独审not-run |

## 充分性

单次exit0或打印[VERIFY]不充分，必须有断言和原始可见输出。旧QG示例缺reopen是负例；旧auto单次高confidence不是业务正确率。各层验证区分local/decode/business/executed，未执行不得标已执行。

样例完整性按[acceptance-sample-design.md](acceptance-sample-design.md)核既有四段参考；v3不以未来live8采集为前置。当前参考8/8覆盖并保留9个唯一实例；历史生产PM/执行并不存在，第四段明确是现在编写的参考裁定。

Python/TS/faux/隔离生产链均按任务卡执行；本轮不运行产品测试。历史npm检查故障只作风险，未来T08必须重核当前基线，不改其它key证据来过检查。未闭合AC留具体缺口和责任卡，不能done。

## 逐项复核补充（2026-11-19）

直接采用[v0.5范本索引](docs/reference-records/index.json)及[四段逐项对比合同](reference-comparison-contract.md)。T01—T10全部直接引用同一套资产；T01—T07交职责内字段证据，T10定义原件回放及报告校验，T08交9例×4段共36行JSON/Markdown对照与原始观测，T09逐行复核。原件回放、当前实现差异、负例拒绝和PM语义分别核实；缺段/串版/无依据差异/未验证不通过。T11继续撤回，产品测试/实施仍not-run。
