# PM研究复核：RQ2 / RQ3（首轮，非正式质量验收）

## 结论

用户明确允许PM接手复核。PM另写本记录，保留RQ2/RQ3 needs-clarification/exit2及原回执；不重派、不补写原report、不将worker状态改成done。本轮恢复处理不再等待dp3服务裁决，但服务的input-incomplete问题并未修复。

复核结果：两份证据可作为有明确限制的设计输入，不能整体标PASS。已核报告内部一致性、与八DP保留目标的冲突及五个完整文件的静态事实；未完成完整producer→writer→consumer→projection审计。RQ1是交叉参照，其exit0也不代表所有断言正确。

必须纠正的研究使用口径：
1. RQ2方案B提出退役/降级dp7、dp20，与spec §1.1已确认的八DP可调用集合冲突，不作为本key实施候选。无需重新把已确认保留集合交给用户选择。
2. RQ2方案A同时说dp15是六类gate裁决者、dp20是stage-close唯一owner，文字仍有双审歧义。设计须明确：同一stage/证据版本收尾只有一个业务裁决owner，协议校验不能伪装成第二审批。
3. RQ2的continue/narrow/revoke不是今天gate writer的原生动作；尤其narrow不能仅靠传空authorizes清除旧授权，见E2。现有人工policy gate也不能因增加模型审核而自动获批。
4. RQ3的“唯一registry耦合”“观察面不受结构性破坏”“读者不动即可”均超过其自述覆盖面，降为待验证假设。问题文案因退役定义缺失而不可显示，不等于当时未记录；需区别记录状态与当前定义不可用。
5. RQ3四个当前case零交集结论只限该目录，不能推广成全部book/docs/config无需迁移。RQ1删除候选也是路径候选，不是整文件删除许可；模板里的dp6必须保留并随批准设计更新。
6. RQ1把显式CLI sign归入auto不代表autopilot自动触发；legacy零POST推论也不涵盖完整book/stdin入口。精确8DP收敛仍须逐入口拒绝/零副作用证据，不能以当前input-incomplete代替退役拒绝。

## 证据

### E1 — 材料阻塞与交付缺节是两个独立事实
- RQ2/RQ3的run/output/trace与独立研究证据已全文回读；终态分别255秒/165秒，均exit2。研究文件四节俱全，output缺四个恢复标题；原终态已ack但不改写。
- trace末各有自动dp3 input-incomplete/acted=false；这些事件不证明完成HTTP调用或发生业务处理。
- PM上一轮真实ask_decision(dp3-worker-clarify)返回available=false/input-incomplete，missing_fields列出dp2五项与dp25四项；调用material中前五项已提供，后四项不适用而为空。直接原因是本地材料拒绝，具体传递/校验层尚未定位，不能归因网络或风险否决。
- 本轮用户直接允许PM接手，仅处理研究复核；不把人工授权伪装成服务成功。没有可用服务decision_id，不伪造executed/settled receipt。

### E2 — 已完整读回的gate writer
`packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts`全文。
- `answerGate:169`，`:170`仅将approve/reject转换成approved/rejected。
- `:177-178`：authorizes缺省或空数组时不写该字段，旧行保留；非空才写闭集值，未知值先拒绝。
- writer只改已有frontmatter行、不创建gate；显式authorizes行缺失时拒绝。`:200`取锁，`:216`原子rename。
- 因此模型选项映射和授权收窄需要单独冻结消费者契约，不能把建议映射说成当前已支持。上述是静态实现证据，不是实际锁/并发/消费者验收。

### E3 — 默认自动面，而非当前项目配置
`packages/multi-workers/autopilot/config.py`全文：`:102`默认auto_gate_mode=off，`:123`闭集off/shadow/live；缺配置零创建、非法配置fail-closed。未读取活项目配置，也未执行loader；不能据默认值声称当前服务必处于off。
RQ2关于conductor规则、stage-close注释/代码冲突、shadow与配额的坐标是研究引用，PM本轮未通读conductor，尚不作为独立完整核验。

### E4 — 模板与case边界
`packages/multi-workers/decide_book_template.json`全文：仅dp3与dp6两个book；dp6键在`:31`。它属于保留DP，不应因路径被列入R6而删除。
只读目录枚举确认`decide_cases/`四个文件名dp1/dp2/dp3/dp25；本轮未重读其全部内容，内容零退役引用仍是RQ3研究结论，不是PM新增证明。

### E5 — 保存快照的语义与测试数量
`decision_task_state.py`与`test_decision_task_state.py`全文。
- 前者`:9`字段为status/observed_at/source/completed/remaining/blockers；`:16`严格校验并复制列表，`:43-48`拒绝after早于before，不查询当前任务状态。
- 后者13个test函数，其中一个参数化六项，按源码展开对应18实例；本轮未collection或跑测试。RQ3“13例”应读作函数数，不替代既有18P或本轮动态结果。
- 同任务创建关联、历史只读、安全过滤等断言在测试中存在，不等于本轮验证实现通过。

### E6 — 工作流及并行性
- 原RQ1/2/3独立取证已全并行，均终态并ack。本轮比较同一spec与三个报告，PM单写本记录；不重派相同研究、不增加源文件写者。
- switch_key确认本窗口持有mw-dp-consolidation；detect_root/index list/audit_phase回读为SPEC/PASS。audit仅证明当前工作流一致性，不是14AC验收或完整spec批准。

## 残留与未验证

- dp3材料传递/校验具体根因；未额外调用服务探针、未修源码。人工接手不消除该技术缺陷。
- RQ2所引conductor六类门创建/消费、stage-close live自动面、retry授权是否确实无消费者、dp6质量材料生成与dp25词表冲突仍需完整源码及隔离路径复核。
- RQ3全历史registry依赖、提交/provider直接调用拒绝、retired标记位置、文档/config与安装产物未完整核验；不主张“无需迁移”。
- 四门问题/选项/具体动作、证据版本复用与失效策略、stage-close唯一owner仍未批准。联合职责建议以dp6正式质量审核、dp7失败处置、dp20阶段收尾、dp15既有流程授权为方向，不把退役17项重新藏入dp15。
- 14AC草案未锁定；没有design.md或实施批准。旧mw-decision-context的26AC、格式决定及其他未结项不受本轮授权影响。
- 本轮未运行测试、check、build/install、共享服务起停、部署或签收；未对原worker/研究文件、源码、配置或生产历史执行写操作。没有整仓字节/运行验证，不能声称对应AC已通过。

## 上下文来源

- 本轮用户授权：允许PM接手复核RQ2/RQ3。
- `.agenticdoc/goal.md`、本key `spec.md`、`pm-state.md`。
- `evidence/research/spec-runtime-inventory-20261024.md`（RQ1）及其run/output/report；`spec-gate-authority-20261024.md`（RQ2）、`spec-history-regression-20261024.md`（RQ3）及原终态回读。
- `evidence/research-terminal-events-20261024.md`：之前真实事件与阻塞记录，保留不重写。
- 本轮E2–E5五个完整文件读回及只读目录/坐标检查；无测试命令执行。

## 后续诊断勘误（2026-10-25）

本记录E1及残留项对dp3“材料传递/校验契约不一致”的解释被后续证据纠正：PM混入了九个其他DP字段，闭合集正确拒绝；工具将unknown/invalid/missing三类问题全部命名missing_fields，导致误读。纯dp3 case在直接与registered入口均正常，混合九键均在Python前拒绝，四组faux断言通过。worker自动trace则是无agent material的既有零spawn降级。详见`dp3-boundary-diagnosis-20261024.md`及原始diagnostic.log；不删除原观察、不伪称服务被修复。
