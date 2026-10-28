# T09 PM 独立交接与原面R2处理

## 结论

原T09实际done/exit0/end2026-10-27T09:02:24.684Z，已吸收本轮完整回读并ack。PM不是按exit0放行：完整读after书库1559LF与test1348LF至EOF，独立assigned109passed两次/rc0，但17个额外边界fixture为4pass/13fail。因此当前semantic_handoff_verified=false。已实际派原T09有界R2处理四个根因，不重复把可修工程问题抛人，不改变原36-task/53AC-VC。

R2：dpc-t09-books-r2@2026-10-27T09:07:42.696Z，PID22708，真实running；原attempt及原红绿/diff/账本报告不改。不是暂停不处理，也不是让T05/T10在损坏的前置上盲跑。

## 证据

- check.py/check.json及原始assigned-1/2.stdout/stderr：09:05:20～25Z网络禁用/绑定实际副本、minimal UTF8/privatefixture/禁cache/pyc的两次109passed。
- independent-negatives.stdout及probe.json：六个合法JSON非对象(null/空list/list[book]/bool/int/float)沿stdin→prepare_request的path重载而抛TypeError；JSON字符串指向同fixture有效book文件则被加载且prepared有效；非法legacy文件报告as_dict缺ok抛KeyError；unknown top/notes key、坏version/unknownDP错误detail四次回显synthetic known-secret；3.0被当成版本3接受。合法fullbook、bundle/坏JSON拒绝及bool版本拒绝四控制通过。13失败是四组根因，不是13任务或模型不可用。
- 当前两产品before/after与worker快照字节一致，完整incrementaldiff分别27hunks/75055B、4hunks/87830B；worker raw diff SHA另记，CRLF→LF文本一致。1883镜像只有原两产品变化；验证期间净变=[]；原worker history/evidence、14pyc及相关两live基线不变。
- t09-r2-pre-dispatch-20261027/check.json：09:07:03Z再次与PM后验inventory逐hash相同，原证据/原worker完整保护，当前两before/rawbytes及原state/dag保存；R2卡SHA f34bf2252bef66d990cc2c5b97a2c57402015eedcbc5ae6dd497ade2d46bf9bc。
- workers/dpc-t09-books-r2/task.md全文回读：实际cardSHA/body/唯一两产品+R2证据面一致；缺isolated的标签照旧留史，不修运行框架。run.json真实running；普通coding/pi/default角色模型、imagesno/allowforeignfalse、不额外设预算或provider。

## 改动清单

PM只新增独立验证/报告/原面R2卡与state/manifest元数据。业务实现交由R2 worker在原两文件内修复；不写live/依赖/parser/CLI/观察代码。原109函数体AST必须保留，新增回归，不许再整文件重写来降低断言。

## 残留与未验证

R2本轮必须关闭：stdin数据非文件读取权、可序列化错误报告、schema secret保护及版本integer严格；新fixture先真实red再green，PM原17fixtures保持不可改，新freshsuite及scope复验后才handoff。不能用原109green/原done/ack代修复。

原T09报告context/观察seam是真正后继集成债但其任务归属描述有误：T10卡只允许wire/lifecycle/task_state与两tests，不含decision_points或decision_context，因此不能口头把model_state_for/context缺口交T10然后当有owner；须PM在原模块writer面内协调后续具体修复，不扩T10面。观察seam的decision_points仍需与原protocol writer协调，playground/monitor/UI按原T27～29完成。旧独立26AC的具体tests不在T09面，是否全部已在85path面有owner仍未核，不能称原套件完整覆盖。

全L2/check/TS编译/reviews/QG/签收/human/H12/locks/effects仍未完成。14pyc不清，真实provider/live部署无授权；净hash审计不是瞬时无写/独占作者/全历史审计。原T08 exit2与旧dp4 unavailable限制均单独保留，不伪造decision/receipt。此报告无再次人工审批问题，一般原面工程修复已组织并实际执行。

## 上下文来源

本轮用户worker终态完整回读、原自动续推/完整开发指令、原T09原/R2卡及report/run、PM完整after源码read、独立probe/check/rawbytesdiff、新R2baseline及dispatch真实返回；原T05/T10卡和DAG依赖。T05与T10均依T09合格，只能在R2独立交接通过后并行释放。
