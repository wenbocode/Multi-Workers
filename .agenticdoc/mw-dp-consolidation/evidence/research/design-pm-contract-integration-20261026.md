# PM联合设计源码补核：预算配置与模型理由传输

## 结论
本次PM只读整合发现一个需要明确审核的能力差距：现有决策backend没有自由文本理由答案。不能把失败reason、PM note、选择标签或概率冒充模型生成理由。补全设计可选同次调用中模型选择可溯源理由/依据，或者先取得原传输的上游扩展；不静默更换模型、provider或增加第二次审批。

## 证据
- 全文read `packages/multi-workers/decision_backends.py:1`至EOF（分1～600、601～EOF；实际1124行）。模块文档:1～36只允许timi /v1/decisions，jev-latest，无自由文本类型；ANSWERABLE_TYPES:153为choice/score/noul；build_payload:845附近仅model/state/questions；_decode_answers:859～943只保留value/confidence/probabilities及score的legend，不保留自由理由。_outcome reason:771附近是失败分类，不是业务理由。
- 全文read `packages/multi-workers/autopilot/config.py:1`至EOF。config_path:163附近为 `.agenticdoc/_autopilot/config.json`；DEFAULT_CONFIG及validate_config维持既有21键+单独envelope_fallback，未知键拒绝；load_config:207附近缺文件零写返回未启用默认，部分文件不静默补齐；现有round_budget/worker_timeout不是明确新的项目硬预算授权来源。本设计不得写活config或擅自升级被冻结schema。
- 后续PM全文读 `packages/multi-workers/decision_context.py:1`至EOF：context是可选环境摘录，fit_context可裁剪/丢整slot，不能承载必须完整传输的basis_catalog；该依据采用独立preparation投影，不混入sign四部material/meta。全文读 `scripts/gen_decide_registry_ts.py:1`至EOF，复用已有生成路径及decide-registry.generated.ts，不另造第二权威。
- PM定点读 `mw.py:1530～1749`（非全文）：1585～1598明确decide ask由human输入自由问题，经legacy ungated模型client、标签dp-human-ask。不是仅人工授权表单，human-only隔离保留须单独审核/生产路径资格证明，不按名称宣称不属第九绕行入口；实际后续handler/全部legacy callers未全面核验。
- 锁定SPEC AC007/042要求分别保存PM note和模型理由/依据，AC020/021/036不设实际预算或预授权数值；53AC不改。

## 候选结论到设计
- D012 A：在同次backend请求中用choice选择PM按当前事项准备且含真实材料引用的理由/关键依据组合；模型选择与PM原note分列，标签注明理由文本源于PM预备、所选理由来自模型，不假称自由生成。拒绝未知/不适用/引用不存在的依据。仍只有一次业务判断，无新增固定业务菜单；资源界限按原配置，无法完整准备/传输时明确阻塞，不截断伪造。
- D012 B：原timi决策通道原生理由扩展，必须先有正式API版本/字段/模型能力证据与用户批准，不猜额外字段，不改provider或fallback。当前不可声称能实现。
- 预算/恢复授权使用候选只读decision-policy旁载，避免自行改变原21键；单源授权证明必须来自真实用户明确授权/受控配置或已记录合法授权，不由文件布尔值或模型自报产生。新文件结构仍待审核，不写实际policy。

## 残留与未验证
没运行测试/服务/CLI/provider/凭证探针；上游API当前是否提供未解码理由未知，不能凭当前decoder断言服务绝不支持。没有完整DecisionConfig全文或其他预算生产者全仓审计，不采全局“没有预算”结论。该证据只支撑静态候选权衡，不是设计/AC/QG验收。

## 上下文来源
`.agenticdoc/goal.md`；本key锁定spec.md及RQ18/19已结束的协议/config研究。新的读取仅为PM串行跨问题整合，所有原研究/失败输出不改，不追加worker或扩大研究范围。
