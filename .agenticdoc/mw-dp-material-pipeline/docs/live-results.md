# 八DP真实API结果与验证边界

使用现有timi `/v1/decisions` 与jev-latest。当前采用七份v0.5捕获，加一份最新dp-auto路径设计捕获（原schema保留v0.6-draft）。完整body、原始返回和反解见“八DP实际body与原始返回”；最新dp-auto完整响应在第2页单列。本次整合没有新发API。

## 当前设计对应的结果

| DP | HTTP | wire | 反解 | confidence | 所选wire概率 | input/output tokens |
| --- | --- | --- | --- | --- | --- | --- |
| dp-w-type | 200 | codingA | coding | 1.0 | 1.0 | 1308/56 |
| dp-pm-steer | 200 | splitA | split | 0.92 | 0.94 | 1692/57 |
| dp-w-check-task | 200 | investigateA | investigate | 0.98 | 0.99 | 1674/52 |
| dp-QG | 200 | fixB | fix | 0.64 | 0.76 | 2433/43 |
| dp-gate-approve | 200 | approveA | approve | 1.0 | 1.0 | 1519/56 |
| dp-sign-key | 200 | continueA | continue | 1.0 | 1.0 | 2003/48 |
| dp-auto（路径修订） | 200 | retryA | retry | 1.0 | 1.0 | 2847/39 |
| dp-route | 200 | route4 | dp-QG | 0.99 | 0.99 | 1889/75 |

当前8份捕获合计usage：input 15365 / output 426，不是本轮新调用量。旧v0.5先发8次，中文简称修订后对5份新body各发一次，其余3份复用同字节捕获；13次历史调用合计input 22788 / output 701。随后dp-auto新路径单次input 2847 / output 39。历史共14次调用，合计input 25635 / output 740；本次整合新增0次，未估算费用，未为confidence重试。

旧dp-auto的retryA、confidence=0.16、retryA概率=0.58、usage=1150/39保留在历史对照与captures/dp-auto-baseline。它缺少优先级、超时阶段和来源范围，不用于证明当前路径设计。

## 结果含义与限制

全部当前body有HTTP200与有效官方解码/本地映射。QG选择fixB，保留F1/F2两项原因；auto新例明确优先取得当前状态，但两条有界路径仍均合法，不把confidence当业务正确率。当前auto正例和21个反例通过材料检查，未部署专用prepare Worker或生产守卫。

旧v0.5同时加入desc、AC/VC状态/QG链和术语定义，不能把与v0.3的confidence变化单独归因于术语。新auto增加合成目标/证据前提，也不是同事实受控实验。验证只说明这些payload被真实接口接收并产生所列选择；不证明生产业务、来源自动提取或独立review已经通过。原请求/响应字节、ID和usage均保留。生产身份/权限/取消/当前预算、QG/签收writer检查未执行；全仓npm run check被其它任务9个嵌套Biome根配置阻断，后续阶段未运行。
