# Autopilot统一推进控制面：dp7 / dp15 / dp20讨论草案

状态：讨论建议，未获联合设计或实施批准。用户本轮要求收束三个DP，结合autopilot分析。纠正前轮把三者讲成通用独立审批的角度；不据此修改已确认八DP集合。

## 核心判断

三者服务同一个autopilot推进闭环，应统一事件、证据关联、授权检查、写入/消费及反馈机制，按具体推进事件选择一个业务裁决owner；不是每次推进固定串联三次模型批准。conductor继续是现有文件协议的执行者，不新增中心调度器。

建议暂保留三个可调用职责：
- dp15：autopilot流程gate的推进/暂停审核，遵循既有自动与人工授权边界；不再第二次裁决stage-close，不替dp7重选同一恢复方案。
- dp7：autopilot相位推进失败且既有机械整改不能解决时的恢复处置，不泛化为所有worker失败或所有质量审核；不豁免原phase gate或授予额外预算。
- dp20：autopilot的stage级收尾/交接审核，唯一阶段收口业务owner；不重做dp6质量审核或dp25 key签收。

正常可确定推进继续按既有机器规则，不增加固定模型批准。需业务判断时选择对应分支；同对象同证据版本复用有效判断，材料/授权条件变化才重新判断。纯人工policy gate只能材料审核/建议与升级，不能因模型选择而自动批准。

## 本轮新增核验（静态，非完整审计）

全文阅读autopilot/gates.py及TS autopilot/gate-writer.ts；定点读取conductor中完整消费、阶段收尾、自动单门处理函数及规则表。原三个研究已全并行并终态；本轮是共享基准的PM串行综合，不重复派发、不进入新phase拆解。

1. `gates.py:75` GATE_KINDS六类：stage-confirm/stage-close/stalled/budget-exhausted/goal-change/xkey-authorize；状态pending/approved/rejected。文件协议是真实消费面，改DP定义不自动产生推进能力。
2. `conductor.py:910-974 _consume_answered_gates`：stage-confirm approved使stage running；stage-close approved使stage closed并调用_ensure_next_stage_gate开放下一stage确认门，不等于下一stage已获启动批准。stage-close rejected使stage halted；紧随其后的阶段rank将终态定义为吸收态，不能把hold/rework随便映射为reject。
3. `:1272-1331 _stage_closure`：全部key终态、无in-flight、无reconciliation争议，写dossier并建立stage-close gate。终态还包括closed-legacy，因此终态计数不能冒充全量成功或质量PASS。
4. `:6888-7049 RULES/auto_decision_for_rule`：stage-confirm/goal-change/xkey-authorize是guard；stalled/budget-exhausted/stage-close有窄approve规则。stalled还要求显式paperwork及已证明false-negative。不能把全六类当成同权限的模型可放行门。
5. `:8348-8456 _auto_decide_one`：已有效决策去重，机器facts/proposition，必要时defer pending-review；approve先检查证据binding/drift，再过shadow历史门及night/key quota，才answer_gate_auto。off无auto；shadow不放行；live仅窄面。未读取活项目配置，不声称当前模式。
6. `:6535`旧注释称stage-close只guard，与`:6912`附近approve规则冲突。本轮确认存在冲突，不擅自收紧或扩展现有边界；批准设计需明确以哪些既有规则/消费者为边界。
7. TS writer `:169-216`仍只原生approve/reject；空authorizes保留旧授权，非撤销。三DP新选项到writer/consumer的映射仍未批准，不能宣称已有hold/rework/narrow原生动作。

## 推荐闭环（目标态，不是现有已接线事实）

conductor发现推进事件 → 既有硬门/事实/授权及预算检查 → 可确定自动处理则走原规则 → 需要判断则选择唯一dp7/dp15/dp20分支 → 写入已有gate/恢复载体 → 原消费者执行 → 反馈实际状态变化。

- stage-close需要判断：dp20唯一owner；dp15不追加一次“同意关闭”。已有确定性窄自动规则如何与dp20衔接需冻结，不先额外加模型审批。
- phase gate失败：先用机器缺项整改/重验链；需要恢复选择才dp7。仍在既有授权内不追加dp15审批同方案；需要额外预算形成budget-exhausted gate时，审核对象是新增额度而非再审恢复方案。超出现有权限仍转人工。
- stalled/budget-exhausted的流程授权归dp15，worker checkpoint处置仍归dp2；不因共享“失败/停滞”文字重叠触发重复裁决。
- goal-change/xkey-authorize/stage-confirm按当前guard/人工边界；dp15可审核材料和升级，不自动替人签权。
- 阶段质量/签收证据复用dp6/dp25有效结果，不修改其四DP业务契约或增加第二次签收。

## 收束建议与剩余决定

推荐“机制合一、事件分流、单一owner”，暂保留三个ID及真实职责，不将dp7/dp20退役为隐藏别名或材料builder。若用户选择只保留一个DP，那是重新调整八DP范围，需要显式确认；当前未做。

待讨论冻结：
- 三类事件边界、各自问题/选项与真实消费者动作；不能把所有DP字段混入同一material。
- stage-close既有窄自动规则与dp20业务审核的关系，避免新增重复审批或静默改变自动面。
- hold/rework与pending/halted及后续整改的真实动作，防止reject造成不可逆halt。
- 同gate实例/证据版本/授权与预算条件的复用及失效，off/shadow/live、服务不可用和未执行回执的统一处理。

本轮未完整通读conductor，未审计全部 producer/writer/consumer、实时配置或部署版本；无测试、额外模型请求、源码修改、服务操作、phase推进或签收。恢复detect_root/list成功；组合命令尾部可选PI环境读取因缺失项返回exit1，不代表工作流恢复失败。audit_phase为SPEC/PASS，仅工作流一致性。
