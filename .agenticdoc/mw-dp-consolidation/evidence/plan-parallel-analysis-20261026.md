# PLAN/任务拆分前并行性分析

## 结论
用户最新要求“继续，Plan 生成完开始执行计划”；授权本key已批准设计/逐文件写面内计划与执行，不包括活业务、预算/恢复grant、安装部署、删除保留功能或提交。本窗已switch_key，当前PLAN，既有22个研究终态全部acked、无running。mw_status实际PID27196运行；无需启动/重启服务。

## 可并行单元
- 首批实施前静态核对分Python入口/生成/旧调用分类及TS/框架角色与现有diff两单元，各唯一新证据，源码共同只读；使用既有研究，不重复设计选型或无界补证。
- 单源接口交接后：纯有效性、只读policy、传输/材料可按文件并行；TS工具、PM后继独立模块、Worker/快照与gate基础按真实依赖启动。
- Python签收validator、gate消费者、恢复handler及外部CLI接口按契约依赖协调；前端三文件与观察server可在投影接口冻结后并行；最终跨链测试和只读分域review可并行，PM正式QG串行。

## 共享资源与串行理由
- decision_points、decision_context、generated TS、CLI mw.py、conductor、history及共同测试文件分别单writer；同文件后续任务必须有直接/传递依赖和before/after hash交接。
- 先静态baseline/资格/范围核对→八入口单源→生成/材料链→受限消费者，不能让旧注册/新调用在运行源码边界混用或绕过失败。测试同文件虽不同case仍属于共享写面。
- 核心材料/依据完整性、human-only及H12真实来源、跨keyclaim/预算/实质版本都是硬前置；未证/未列caller需要补面/业务权限时具体上抛，不删除功能、默认approve或用token自报免检。
- npm run check含biome --write且--error-on-warnings，用等字节隔离保护副本规划完整检查、完整输出；禁止并行真实工作树formatter，现旧债非零不谎称check通过。复制/依赖链接等价性不成立就阻塞，不安装或降依赖。

## 本轮意图与残留
PM单写plan/任务卡/依赖manifest/state，先机械检查DAG无环、全部修改测试有验收命令、写面均在批准范围、共享写依赖排序及53VC覆盖，然后经advance_phase TASKS/EXECUTE启动两research核对。计划/卡完成不等于产品或AC完成，coding仅在前置核对和writer占用条件成立后派发。现框架及mirrors已有修改必须保存基线并协调；不重开/改写RQ15/16或旧key26AC/monitor8AC等验收。

## 上下文来源
用户本次执行要求；spec/53AC锁稿、design批准与write-scope；pm-mind Phase1/2/3；当前task list/phase audit PLAN PASS及mw_status。文件角色/写面来自设计，不从研究done/ack推导运行验收。
