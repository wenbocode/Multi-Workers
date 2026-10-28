# 固定集成交接（实现优先，不新增研究）

当前基础T01/T02/T06已交付，局部GREEN；仅以下设计闭环必要接线进入固定T08收口。

## 1 新失败记录显式关联
T06 reader前向兼容record-start.decision_id或任一行logical_id+decision_id。现record_start无decision_id、wire common无logical_id，没有consumed等桥时wire记录会误标legacy。
最小方向：T02单写面后续归T08，record_start增加显式可选decision_id并由T05在真实调用前传实际id。若T05无法预生成真实id，再在统一调用入口显式写入关联，不按key/时间推断、不重造身份体系。失败路径也关联，是AC010/016必要，不低影响债。

## 2 dp25实际签收事实
T06当前以record_signoff行判completed且file_verified=false，仅测试用writer声明，不是有效签收文件验收。
T05交付无凭证/模型的签收校验函数/schema后T08单写history接线：同logical_id/snapshot有效文件才证明finalize completed；日志成功文件缺失不得完成。文件成功关联日志失败仍可由有效文件精确关联证明完成并显示反馈失败，不能反过来依赖signoff日志存在才发现签收。
材料变化只影响使用旧选择再次签新事实，不凭新的材料快照自动抹去历史已成功签收事实；签收事实完整性与当前key phase可继续推进分列。

## 3 HTTP和UI
T06 HistoryPage.facets.as_dict()由T07在/api/history响应输出；records工作台已现as_dict输出，detail nodes10/list nodes=[]。固定形状见plan与T06report。请求正文保留实际capture，不拿人工wire工厂示例当实际HTTP。

## 4 T03 producer→CLI→反馈必要对齐
T03局部15P只TS runner stdin、自动dp2轮询检查；反馈buildDp1ConsumerFeedback纯构造未接IO，T08接emitDispatchTriage/dispatchTask真实阶段到T05唯一CLI。失败反馈不重做派发。
- T03 meta initiator_role="PM"，T02闭集="pm"；统一producer小写，不造兼容双词表。T03 event_id=dp1:<logical_id>:<stage>需核T02 token规则，签名必须符合固定卡。
- T03 report §7推荐feedback只logical_id/lifecycle/action等缺meta/decision_id，与T05卡固定{meta,decision_id,dp,stage,event_id,...}不一致；采用T05/T02真实协议，按decision_id精确关联，不按logical_id猜latest。
- dp2旧buildDp2CheckpointState/decideDp2Checkpoint留在pm-orchestrator（T03面），T04不能越面重写；新工具主动入口可直接用新业务schema，不要求复用旧函数。T08删除或替换已被新设计覆盖死路径时精确单写，不让两个worker碰文件。
- T03 real-card 2559B超过T01 Python _fit_state固定2000B；客户端不拦不等服务已允许。保留原文、服务超预算明确拒绝；若主功能真实材料与T07四case验证需改现2000B，依据实际完整HTTP测量统一调整明确预算而非任意限额或绕过transport门。不把T03声称max_state_bytes=0当固定_fit_state已不存在。
- T03旧TS4文件42F/83P与type旧删符号集中T08迁移；不能报告全为既有基线而豁免。

## 5 T05/T07交付后的必要收口
- T05 CLI `run/sign/lifecycle --stdin`与validate_signoff已交付47P含3subprocess loopback。其run用executed action=record写逻辑关联，需T08验证失败或关联反馈写失败时不误legacy，不能把技术关联当业务行动成功。
- T05 validate_signoff(key_dir,key,expected_logical_id,expected_snapshot)校验文件自洽+父链；T08 history须使用精确同次id/snapshot，文件成功反馈失败也能发现，不猜latest。
- T05 legacy sign无stdin已实际坏，按批准不保留旧业务schema，但不能留主命令默认偷偷坏。旧入口应明确要求普通PM材料/新stdin并诚实拒绝，或按已批准新入口接线；不复活计数式判断/二批。
- T05 framework done词表仍continue/narrow/revoke，与finalize不兼容是结案实质阻塞，不标非阻塞。框架脚本禁写，需用户明确授权最小适配才能改，不能伪造continue或关签收门。
- T07 typed4/4与validate HTTP已验，但显式submit→真实模型HTTP编辑正文未做。T08使用合成loopback backend冻凭证证明完整链，不真实Jev付费。
- T07 UI专有test DAG、playground未改，需T08核单次输入/真实请求返回/反馈是否用真实同次projection，不凭页面10节点空壳过AC。
- T07 worker终态needs-clarification exit2因写ledger漏dp1 JSON，不需求问题。PM已核文件1201B SHA256=e1d8e95973934215b1dba1b9cd3062a95f7f03cc44cdcb32367f3ae9fa86cc84与report相符，ack保留终态。产物可用，T08回归drift验证而非修服务框架。

## 6 证据与范围
- T06 RED1 19F原行为运行；后加3用例回放旧模块是修后回放，不test-first，集中披露不重写历史。
- T06邻接DOM回放只能证本卡并非唯一失败原因，不足断言所有失败均非本卡引入；待稳定联合复跑判增量，不滚动追绿。
- T01旧fixtures断言迁移与T03/4/5/7接线失败统一T08，保留当前工作树外来改动。
- 不重做性能/SLA/计数/缓存泛研究。现5项核心实现运行，T08只在相关writer全部终态后派，禁止双写。
