# Autopilot人工决策盘点与dp7/dp15/dp20覆盖（PM综合草案）

## 结论

按用户最新原则：默认先DP自动决策，上报人必须说明人工必要性；不沿用旧“当前人工面永不改变”的目标态前提。本轮三路research已done/exit0并全文读回output/run/证据、逐一ack；原报告保留，不将exit0等同于结论全部正确。

本轮按实质问题去重识别13类决策/人工作业面（含13号条件性的key签收缺口），另列尚无生产入口的能力和主动治理开关。不把同一gate的approve/reject分成两项，也不把14条stall原因当14个决策。部分外围模块/调用者未完整审计，因此这是当前识别清单，不宣称全仓零遗漏或线上触发频率。

三DP当前定义不能实现“先DP→自动推进”：无conductor触发/答案消费接线，dp7只有失败原因分类，dp15缺kind专属事实与真实动作，dp20缺阶段凭证与恢复/收口动作。缺口首先是材料/问项/消费者，而不是DP数量不足；不能仅凭当前占位定义判必须新增，或直接退役合并。

## 证据

### 决策清单（当前路径与目标态候选分列）

“候选DP”不是现有已接线能力，也不是本轮批准的归属。三个DP编号为角色候选，需进一步冻结唯一owner。

| ID | 当前需要人决定/处理什么 | 当前触发与实际入口/后果 | 先DP的候选覆盖 | 人工必要性应如何证明 |
|---|---|---|---|---|
| H01 | stage提案是否启动，还是退回重提案 | stage-confirm；approve→running；reject→有界重提案。conductor:1110/1145/910 | dp15 | 目标/优先级/依赖有无法从已授权goal确定的信息时才升级；结构校验本身不是人工理由 |
| H02 | 当前stage是否收口 | stage-close；approve→closed并开放下一stage确认门，reject→halted。:1272/954 | dp20（与dp15的stage-close仅一owner） | 证据不足先补证/待处理；是否接受真实遗留影响超出授权或不可逆处置未授权才人决 |
| H03 | stalled key继续投入还是遗留关闭 | stalled；approve→running，各受约束loop +1轮；reject→closed-legacy。:6367/4146/4215 | dp7恢复方案；dp15额度/流程选择，需避免同事项双审 | 风险/预算在授权内可DP；不可逆遗留关闭没有授权或后果不能界定时升级 |
| H04 | L2额外追加一轮还是转stalled | budget-exhausted；approve买1轮；reject→stalled。:1690-1723/4067/4079 | dp15 | 区分软轮次额度与已授权硬预算；额度选择可DP，超硬预算不能自行扩权 |
| H05 | pending-review待复核key恢复还是返工 | 48h/其他key终态使_review_escalate报人；原stalled/budget gate approve=resume，reject=rework，两者→running。:4451/4540 | dp7或dp15恢复分支；质量事实复用dp6 | 超时本身不是必须人选；材料/目标明确即可DP。文案escalate与两值writer的关系仍待冻结 |
| H06 | goal变化后是否采用新目标继续 | goal-change直建gate；问题文案approve/reject，当前tick任一答案后均刷baseline恢复。:3769-3870 | dp15（需goal差异/影响/授权材料） | 已授权目标中的澄清/调整可DP；无法推断的新业务意图或目标越界才问人。reject语义缺口不是人工必要性 |
| H07 | 跨key受限修复是否授权 | xkey-authorize；批准后才派proposal并受限apply；拒绝→ticket rejected。:5127/5201/5279 | dp15；任务恢复可能交dp7，非重复批准 | blast_radius⊆write_scope是机器检查；已批准写面内可DP，未经授权写面/合同目标变动才升级 |
| H08 | 是否允许修改冻结AC/VC | gate答案authorizes含contract-change、key匹配；done前contract_guard.evaluate核查。contract_guard.py:322/334/384；conductor:2932 | dp15的契约授权场景需扩展（当前仅6kind不足） | 区分不改变交付目标的调整与改承诺；授权不覆盖新目标/无法确定业务取舍时问人，不能因冻结标识一律人审 |
| H09 | 跨key proposal派发耗尽后怎样恢复 | _xkey_proposal_exhaust:5363；escalation.md，approved ticket留下proposal_exhausted_at；目前人手清标记或落proposal，非gate/受控新决策入口 | dp7恢复+dp15额度边界，须设计受控消费者 | 通道故障/可界定修复可DP；无源key/未知写面等信息需要补齐。不能把手工清标记当已有安全自动恢复 |
| H10 | roadmap提案两次耗尽后如何重新规划 | _dispatch_roadmap_writer:1176-1217达到2次直接等待人改roadmap，可能只静默停等；不是额外gate | dp7或dp15重规划分支，材料/动作目前不足 | 若仅工程拆解失当可先DP；目标、优先级或资源取舍缺业务意图才问人 |
| H11 | 已halted的stage如何恢复推进 | _stage_activation:1090遇halted返回；现状态机不允回退，注释要求人改roadmap。当前无受控恢复入口 | dp7恢复或dp20后继阶段策略需明确 | 不因实现只支持手工就认定必须人；要有可审计、不覆写原终态的恢复方式。超授权重规划才人决 |
| H12 | 自动决策熔断后是否/如何恢复 | _trip_auto_breaker:7792写auto-brake.md，action要求人清；持久刹车阻断auto，不是普通kind gate | dp15治理/恢复场景需扩展 | 熔断先停止；原因可验证消除且恢复已预授权可先DP，否则需人授予恢复。模型不能自批越过硬保护 |
| H13 | 条件适用的key决策签收是否成立 | 有kind=decide且未显式disable时done要求签收文件/档案重算；失败是硬门→恢复缺口，不是新增stage gate。advance_phase.py:309 | 已保留dp25，不由三个DP取代 | 现有dp25自动签收契约与user-confirm兜底；不能因框架旧词表/未接线就宣布必须人签收 |

### 另列：不是当前主动上报人的独立业务项

- re-attest重评：conductor:4608有创建能力，:4661消费新gate；本轮在mw.py/TS console及conductor搜索未找到生产调用。原RQ5称“CLI入口”不成立，降为已实现能力/缺生产入口。不列为已自动发起的第14个业务决策；将来应是同事项新证据版本重评。
- 自动决策撤销：conductor:7683负记录函数，本轮未找到CLI/console调用；不能声称已有可用人类撤销命令，不能把负记录等同于撤回已发生的stage/key动作。
- off/shadow/live、enable/pause/resume、signoff:disable等治理配置是主动操作/授权配置面，不等于autopilot每次请求人的业务决定。初始授权如何形成、模型何时允许改变治理配置，后续设计须讨论。
- status/monitor/gate reminder/phase evidence ready/claim skip是观察/通知或机器安全拒绝，不能虚增决策项。
- L1/L2/L3既有补证、修复、质量判断不是逐次人工问项；不能为了接DP拆掉已有机器与worker闭环。正式质量dp6、任务checkpoint dp2、澄清dp3仍保留其业务合同。

### 三DP现合同核对

PM定点读回decide_registry.json完整三条目：dp7:419-486、dp15:1000-1079、dp20:1354-1431。

| DP | 当前材料/选择 | 无法满足的地方 |
|---|---|---|
| dp7 | gate.name/missing_items/verdict_age_hours/has_config_error；仅gate_cause四类原因 | 不是恢复方案，不能表达投入/返工/重规划/停止；占位executor，未接conductor失败链 |
| dp15 | 六kind、pending_items/age_minutes/evidence_refs；continue/narrow/revoke | 缺每kind所需事实、目标/授权范围/预算/明确动作；不覆盖gate外恢复与治理面；空authorizes不能收窄；未接执行链 |
| dp20 | tasks_done/tasks_total/open_blockers/evidence_refs；close/hold/rework | 数量不能代替多key终期凭证/争议/遗留影响；hold/rework不能随意映射reject→halted；未接消费 |

所以后续应先确定问题家族：推进/授权、失败恢复、阶段收口、治理恢复/重规划是否独立。只有当某家族具备独立材料与动作且不适合前三者才讨论新增DP；若合并，也必须按场景闭集材料，不能再次混填所有DP字段。

### PM纠正研究结论（原报告不改）

1. RQ4的“恒缺/恒escalate/生产仅两处”仅在所检查标准生产路径成立；未完整审计外部调用者，且手工gate字段允许存在，不能推广所有历史实例。PM已核stage-confirm/budget创建不传对应machine_fields、gate_facts读取这些字段；其他外部路径仍未证。
2. RQ4/RQ6把当前guard-only、不可逆、冻结契约直接说成“事实不可去的人工必要性”，与用户新原则混淆。它们是当前限制/风险输入，是否需人取决于授权及信息，不能据此拒绝先DP。
3. RQ6 C-13称goal-change reject保持halted错误：PM全文读tick已确认任一答案后恢复。原RQ2同类解释亦以此纠正。
4. RQ6 C-05称TS/CLI拒绝二次确认已对齐错误：PM完整读cmdGate:457与writer:169，TS无confirm；CLI _ap_answer:9438才传confirm_destructive。此处不修源码或放宽拒绝。
5. RQ5称closed-legacy“绝对不可逆”过强：普通状态机不回退，但reattest消费者可从closed-legacy恢复running；只是当前未找到生产入口。不能据此判一定人决。
6. RQ5合同授权“永久有效”改成可核事实：PM全文读contract_guard，批准查找不检查消费/有效期/该次diff绑定，存在可复用授权风险；不声称任何未来实现永远有效。
7. RQ6“两个平面完全无关/零交叉”“无证据复用”超过部分阅读可证范围：限当前未找到三DP与conductor自动请求/业务消费接线，不排除其他工具/监控/档案层关联。不建议因该研究句子直接删除auto-decisions账本。
8. RQ6把signoff:disable当普遍治理推荐/签收必须人工不接受；旧dp25/框架词表不一致已知债不能作为新增人工必要性。本轮只核条件性缺口，四DP契约不改。

## 残留与未验证

- 当前13项为本轮识别/去重，不是全仓零遗漏承诺；未审完整pm-orchestrator/monitor/status-model、dispatch/state/roadmap/evidence及所有外部CLI调用链。
- RQ5声称完整读conductor，RQ4/RQ6明确仅局部；不将单份自述代替全阅读覆盖验收。PM只补读关键完整函数，不声称自己通读conductor。
- PM全文补读advance.py/closure.py/contract_guard.py，xkey.py尾段1261到末、tick/activation/roadmap proposal/review/reattest/breaker/shadow/create/facts以及TS cmdGate/CLI answer完整相关函数；不是运行验证。
- 新权限目标、每项人工必要性、13类到DP的唯一owner/材料/动作/失效尚未批准。已确认八DP集合作为旧草案基准，新原则下允许讨论合并/增加，未实际改registry/spec/phase。
- 未运行测试、provider探针、签收、共享服务起停、build/install/commit或配置/源码变更；正常研究派发有模型/真实dp1反馈，不宣称全轮零模型。
- 当前项目live配置/ledger与安装行为未读；无法断言当前线上哪些gate发生过、触发多少次。

## 上下文来源

用户最新放权/清单优先要求；goal.md；本key三新增任务卡/原run/output/唯一研究证据：spec-autopilot-human-gates.md、spec-autopilot-human-recovery.md、spec-autopilot-human-pm-framework.md；派发与拒绝记录autopilot-human-inventory-dispatch.md。上文conductor/contract_guard/advance_phase/console/registry坐标为静态证据，非模型执行收据或生产验收。
