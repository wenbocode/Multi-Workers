# v0.5八DP四段全记录范本

用户所需的是已存v0.5样例：**本地决策本 → 实际模型输入 → 真实模型返回 → PM参考决策**，用于开发理解、对比和回归校验。本轮不新增调用/派发，不以未来真实8/8采集代替本交付。

## 记录性质与版本

决策本/Request.data/模型响应是原保存记录。原实验没有生产PM采纳/执行回执；第四段明确为当前会话补写的PM参考裁定，含采纳/退回理由、后续工作、保留原因、执行前检查及不能声称发生的动作。实际执行字段保持false/null。

原v0.5八份中auto confidence=0.16；整合版八份替换为优化auto confidence=1.0（原schema v0.6-draft）。两套清单、9个唯一案例都保留，不把优化输入与旧回包串接。

## 范本索引

| 案例 | 真实模型返回 | PM参考接回 |
| --- | --- | --- |
| [dp-w-type](dp-w-type.md) | codingA / confidence=1.0 | 参考采纳coding：准备代码与回归测试任务，不把类型选择当已派发。 |
| [dp-pm-steer](dp-pm-steer.md) | splitA / confidence=0.92 | 参考采纳split方向：拆W1/W2并回收；复核工时未计，派发前补预算核算。 |
| [dp-w-check-task](dp-w-check-task.md) | investigateA / confidence=0.98 | 接回investigate：由实际Worker按probe读编码说明后重评；PM不代其自评。 |
| [dp-QG](dp-QG.md) | fixB / confidence=0.64 | fixB反解为F1/F2；质量参考为fix，但payload缺reopen须退回补齐候选。 |
| [dp-gate-approve](dp-gate-approve.md) | approveA / confidence=1.0 | 参考采纳approve该限定只读回放；保留C1/C2，不能扩成额外清理授权。 |
| [dp-sign-key](dp-sign-key.md) | continueA / confidence=1.0 | 参考采纳continue：保留AC-002未验证，补中断证据后复核，当前不签收。 |
| [dp-auto-original](dp-auto-original.md) | retryA / confidence=0.16 | 保留实际retryA回包；原材料缺优先级/完整路径，PM参考退回补材料。 |
| [dp-route](dp-route.md) | route4 / confidence=0.99 | 参考路由到dp-QG准备入口；组织同范围独审/AC/VC材料，不把路由当质量结论。 |
| [dp-auto-optimized](dp-auto-optimized.md) | retryA / confidence=1.0 | 参考采纳先重试路径；60秒一次，失败按余量再读健康，保留停止与报告预留。 |

## 开发如何校验

每个案例提供reference-chain.json、decision-book.json、精确model-input.json、原文model-return.raw.json、pm-reference-decision.json和expected-checks.json。两套8DP组合在[index.json](index.json)明确列出。

1. 回放/反解校验使用实际字节和同版pair-map，核wire、basis、全部原因/剩余项，不调用模型。
2. 当前实现与范本对比字段来源/发送、合法候选、引用、原因集合和PM接回语义；规范性改进导致的新body要单独标版本，不能套旧回包。
3. QG缺reopen是候选不完整负例；旧auto缺目标取舍/完整路径是材料退回范例。不能为了所有范本“绿”而放宽合同。
4. PM参考自然语言无需逐字匹配，但必须保留required_pm_facts，不出现forbidden_pm_claims，不把未执行标为已执行。
5. 原w-check仍由实际Worker负责自评，PM参考只描述如何接回；所有实例的生产owner/权限/预算/正式writer仍未实际检查。
