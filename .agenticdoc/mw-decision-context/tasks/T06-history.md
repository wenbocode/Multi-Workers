# T06 history安全工作台投影

type: coding
ac_refs: AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-019
vc_refs: VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-019

## 上下文
目标`.agenticdoc/goal.md:1`，批准spec/design/plan `.agenticdoc/mw-decision-context/`。种子`packages/multi-workers/decision_history.py:1732` book-snapshot正文读取和history/detail/fold lifecycle（按符号）；T02独占decision_wire/decision_lifecycle正在实现，新v2 meta；T07独占monitor/UI正在实现。你只写history，不争写接口生产模块。

## 要求
按现history同一读链增加pure workbench投影，禁止第二中心库/第二数据接口、按key时间猜关联。T02接口完成前可先用真实现wire生产事件作fixture验证投影，最终必须读真实T02创建元事实/反馈；只有手填reader测试不算生产闭环。
PM发布T06/T07固定接口：list行及detail增加`workbench`对象：`record_version`(缺失旧= null)、`processing_state`(processing/completed/failed/legacy)、`key`,`task_key`(空null),`question_summary`,`dp_id`,`selection`,`initiator_role`,`nodes`（详情提供，列表不含正文）。history response增加`facets:{keys: string[], dps: string[]}`，按本次全snapshot计算，不受分页/过滤影响。优先沿用现list形状，不随意改旧API。
10节点固定顺序`key,role,dp,input,decide,request,model,response,receipt,action`，每node `{id,label,status,detail}`，status observed/missing/failed；detail为安全化已有结构，不拼造正文。实际capture/usage标记沿原事实。只有明确record_version2新数据有nodes，旧data nodes=[]，新捕获失败仍不是旧。相同logical_id关联attempt和反馈，retry独立新id留retry_of，不覆盖前次。
consumed不等完成；settled实际结果决定completed/failed；dp25仅有效同次签收文件可证finalize completed，反馈失败/缺失独立，不撤销真实签收。continue/user-confirm按照实际PM处理结果无签收。签收文件路径/验证T05后续API交付，先别自行猜签收格式，报告待接线。
正文需读原安全快照而不是拼摘要；公开键值/secret长尾/错误均既有脱敏，当前secret不可确认failclosed；不绕链接containment/打开后身份重核。hash不证明安全，不扩大其它旧债审计。
正确行为RED先行再最小实现，保存首写原文/hash/diff含untracked；保留旧dashboard。仅实现设计，非阻塞细节集中账不泛研究，不改其它文件。禁真实凭证/Jev/browser/build/install/commit/service；tmp HOME/USERPROFILE/PI_CODING_AGENT_DIR/env清理+合成auth/读前spy，测试不付费api。

## 写入允许面
- `packages/multi-workers/decision_history.py`
- `packages/multi-workers/test_decision_context_history.py`

## 写入禁止面
wire/lifecycle/monitor/playground/UI/points/book/CLI/签收/其它测试/配置/dist/锁/框架脚本/真实凭证/其它key。

## 验收命令
`cd packages/multi-workers; python -m pytest test_decision_context_history.py -q`；再原test_decision_history.py定向串行邻接，失败旧断言坐标交PM，不越面修改。记录完整日志UTC/exit。npm run check PM稳定统一，不worker全仓写格式；禁止全vitest/npm test/build。

## 状态
代码完成/局部22P+51P+61P原日志通过，PM report271行/output/run与验收日志回读ack；整体接线待T08。必要三项定点见evidence/integration-handoff.md：失败新记录显式关联、签收有效文件校验（目前只信反馈行且file_verified=false不够）、HTTP facets。
RED1 19F合格先行；实现后追加3用例回放不算test-first，不追认其报告中的先行表述。其它缓存/重复正文/计数集中账，不新研究。

## 改动历史
初派；为并行性提前独立reader投影实现，T02生产格式/T05签收最后接线不省略，但不等待泛研读。主state或schema不改变批准需求。

## 交付格式
report.md和自身evidence：正确RED/GREEN日志、函数API/固定schema实际例子、hash、实际writer→reader证据与仅fixture分列、T02/T05待接线坐标、其它债集中报告。不得写相位文档。
