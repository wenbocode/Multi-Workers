# DP v0.5：完整设计与真实API验证

这是供后续开发使用的统一设计验证文档，已合入dp-auto路径/可区分性修订及prepare Worker流程。最新dp-auto实际返回 **retryA → retry，confidence=1.0，概率retryA=1.0/diagnoseA=0.0**；原始API完整返回在图表第2页直接展示。

## 阅读入口与设计状态

| 入口 | 内容 |
| --- | --- |
| 最新API原始返回 | 完整响应原文、时间/ID/usage、传输与反解结果；不是仅列作者预期 |
| 八DP本地 / 完整payload / 返回检查 | 八DP当前设计的三部分，按DP页签切换；dp-auto已使用新路径设计 |
| 真实jev结果 / 八DP实际body与原始返回 | 当前八份真实捕获的汇总和逐项完整请求/返回 |
| 开发设计 | dp-auto目标/证据/后继/停止、prepare工具顺序、字段来源和接入验收 |
| 历史对照 | dp-auto旧缺证例的完整设计、原始返回与低confidence，保留原字节 |

本包是设计和合成材料的真实API验证；专用prepare Worker/新工具/生产守卫尚未实现。没有执行UEPerformanceFlow/Bearing业务决策。dp-auto增加了明确合成前提，不能把新旧confidence变化当成同事实受控实验。其余七DP沿用v0.5输入，本轮文档整合没有新增API调用。

模型需要两层解释：一层知道AC等缩写是什么意思，另一层知道本次AC-001具体要求什么。两层都必须在实际发送的JSON body中，不能只存在本地决策本。

## 本次结构

| 字段 | 是否发送 | 内容 |
| --- | --- | --- |
| state.desc | 发送 | 当前目标、偏差、事件、证据和未知，沿用最多10句/1000tokens合同 |
| state.material | 发送 | 本决策需要精确比对的AC完成情况、验证结果、资源/约束等 |
| state.references | 发送 | 本请求引用编号对应的完整正文、类型、对象范围及关系；验收项不是只有ID |
| state.terminology | 发送 | 当前文本/业务字段使用的缩写全称与语义，例如AC、VC、QG、PM、CSV、ASCII及独审等 |
| state.enum_meanings | 按需发送 | 本请求状态、业务选择代码和资源单位的明确含义 |
| 本地来源/准备模型/权限/预算账本/hash/提取过程/pair-map | 仅本地 | 原件和真实授权/新鲜度检查；调用参数model及影响选择的约束仍按请求明确发送 |

AC为Acceptance Criterion/Criteria（验收标准），VC按本项目定义为Verification Contract（验证合同/验证项），QG为Quality Gate（质量门禁/正式质量审核）。例如导入适配器的AC-001是“拒绝重复键且失败时不写入”，稳定导出的AC-001是“特殊字符往返保持一致”；相同编号不能跨对象混用。

## 覆盖范围与准备顺序

扫描desc、material、题干、每个选项及业务字段，提取当前缩写/编号 → 从当前范围原件取定义 → 只投影本次必要词条 → 核引用/正文/冲突/未知缩写 → 冻结并发送。候选wire别名的含义由完整criteria明确给出，返回仍按同一pair-map反解。

编号定义覆盖AC/VC、审查发现、剩余工作、准入条件、决策入口。常见中文简称“独审、直执、补证、未测”也有显式解释。准备方必须说明新缩写；注册表/模式检查能发现机械缺项，不能声称正则理解所有自然语言或证明定义忠实。普通未注册缩写返回具体材料缺口，原PM仍可按原权限补取，不成为全局停止门。

## 保留原业务边界

QG先有同范围独立review并核完整适用AC/VC，核对完成不等于AC通过；sign带目标、偏差、当前同范围QG业务结论。desc仍由原主体或受托准备方起草，jev仍只作单选；角色/独审/原预算和唯一writer不改变。字段解释不授予权限。

本版保留三部分完整展示：本地决策本、完整模型payload、返回反解与本地检查。输入是合成规范样例，真实API调用不等于当前项目review、生产QG或签收动作。desc token计量沿用估计预检/精确计量区分；新增词典属于整份请求预算，不挤占或伪称desc精确计数。

## 冻结版本与证据位置

七DP当前样例在cases/各DP/；dp-auto当前样例在cases/dp-auto-current/，其实际发送schema保留v0.6-draft，整合不改写API记录。cases/dp-auto/是原缺证基线，不再作为当前dp-auto正例。

原字节捕获已集中到captures/：七DP各自目录、dp-auto-current及dp-auto-baseline。integration-manifest.json逐项绑定原始证据与本包副本。旧v0.5文档和HTML在本次任务evidence/before保留；v0.6独立实验保留历史，不再作为必须跳转的主入口。
