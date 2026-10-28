# DESIGN首轮研究PM吸收与使用边界

## 结论
截至本轮终态回读，RQ13/14/17 done，RQ15/16 needs-clarification；五任务证据/output已回读且逐一ack。ack不等于设计采纳或验收，报告自称Done不覆盖run状态。当前DESIGN，SPEC/53AC锁定；联合设计、证据需求、精确实现写面尚未批准。

## 证据与真实终态
| RQ | worker | 真实状态 | 证据 | 使用限制 |
|---|---|---|---|---|
| 13 | dpc-rq13-design-contracts | done，acked | research/design-entry-contracts-20261026.md | Python协议/backend及TS实现只部分读取，不能称全入口/消费者审计完成 |
| 14 | dpc-rq14-design-autopilot | done，acked | research/design-autopilot-effects-20261026.md | gates/contract_guard完整，conductor及xkey/config/状态部分未读；预算/恢复全仓断言未成立 |
| 15 | dpc-rq15-design-pm | needs-clarification，exit2，acked | research/design-pm-orchestration-20261026.md | output未给机器可识别产物引用；139行证据实际存在，原no-product失败保留 |
| 16 | dpc-rq16-design-worker | needs-clarification，exit2，acked | research/design-worker-feasibility-20261026.md | 证据有四节，但output只加粗内联标题，框架报recovery-incomplete缺四标题；原失败保留 |
| 17 | dpc-rq17-design-signoff | done，acked | research/design-signoff-observation-20261026.md | 签收/历史核心读码可作设计线索；CLI/TS/UI/安装与测试部分未核，无动态验收 |

RQ15 run_id=dpc-rq15-design-pm@2026-10-25T16:07:13.702Z，ended=2026-10-25T16:09:39.134Z；RQ16 run_id=dpc-rq16-design-worker@2026-10-25T16:07:13.667Z，ended=2026-10-25T16:10:20.223Z。证据和原run/output/trace/worker.log各自保留。RQ13 trace出现edit工具不存在，后用worker_file重写其唯一允许证据；writes=none不是未写证据或全仓字节不变证明。

## PM勘误与候选约束
1. 八行活动表、只读退役解释、生成TS枚举可作为推荐候选；不是已批准架构，更不是仅改表就覆盖所有运行入口。旧编号请求须明确拒绝，不恢复旧dp3运行机制。
2. dp-route七目标可用独立静态枚举。只有沿用旧dynamic_choices校验时才遇到≤5/cN限制，不宣称七目标与所有机制天然冲突。dp-auto不套旧数量/ID限制，正常传输资源边界另核。
3. 业务material、本地identity/meta、PM预拟note、模型理由、实际动作/结算必须分层；局部白名单不足以证明所有链路已隔离。
4. 旧PM-only集合不能反推目标role矩阵；vision映射unknown不证明资格，也不自动意味着现有dp3绝对不可调用。路由不授角色。
5. 不采纳把现状unknown图像能力放行作为目标方案。需图必须vision且有效模型满足能力门禁；未知待核，不能冒充有能力。模型路由仅换model是既有分层事实，不自动判成类型系统全部失效。
6. Worker终止真实结论不必须新增队列终态。候选可比较现有终态加原因/结论类别与新增状态的消费者影响；不能把不可达与产物不合格混同，也不伪造done。补证来源、预算、结束判据需可核，不新增固定时长或同步PM等待。
7. 未全文核预算/配置/dispatch时，不采纳全仓无硬预算/补证来源机器载体的绝对证明；报告只能描述已读路径。已有watchdog余量不自动等于完整业务预算授权。
8. gate队列状态与四业务选择可设计为正交，不必把steer/need_fix折成reject，也不预先冻结旧40字段。每个事项的条件和效果必须完整。
9. steer/need_fix后继不是任意可忽略建议：AC-049条件满足时PM须发起对应请求并留下调用证据；选择不等于发起/执行。不能用acted字段代推各业务效果。
10. 固定直调和临时route已是确认要求，不再拿全入口强制route或无route方案作为合法架构备选。框架可承载PM已准备的受权意图，但不能代造材料/角色/授权或把后继发出当完成；具体持久化/消费者仍待比较。
11. H12仅新增gate kind或排除AUTO_RULE_BY_KIND不足以证明隔离。必须核发起主体、预授权证据、原因消除、检查和刹车受限写入位置、失败出口、观察再熔断；被熔断链不得自批，不可用不绕通道。
12. 签收共用只读validator是候选方向，不直接采纳RQ17无logical_id就保留continue/narrow/revoke成功放行的legacy分支。历史解释不等于满足当前必需有效finalize；目标新调用为dp-sign-key，不能冻成dp25旧ID别名。
13. RQ17已定位至少四处词表差异，但dp apply/authority-change旧功能与key交付签收不是同一职责。不把finalize自动映射promote/demote/revoke，不能以统一词表扩大写权。
14. 文件自身logical_id/snapshot自洽不证明对当前受审对象/实质证据仍有效；共用validator仍需原适用范围、真实关联、实质变化影响与并发消费约束。无logical_id不自动降级为legacy成功。
15. RQ17同段说finalize先被旧正则拒绝、又说换旧finalize仍通过，后句不能作现状动态结论。只能记录关联绑定缺口的风险，须在正确finalize合同下验证。
16. 只读历史应保留原词表/原字节解释，不等于新增旧运行兼容。安全失败审计可真实追加，不要求一切账本零新增。

## RQ18～20补证吸收

三任务实际done，唯一证据及终态回读已吸收/ack。RQ18补完整decision_points/backend/decision-tool；RQ19补完整conductor/xkey/config；RQ20补完整ui-bridge/dashboard。均是源码取证，不是运行验收。RQ21/22补其明确未覆盖的monitor/playground及完整CLI，各唯一新证据；不继续无限扩张全仓审计。

追加使用限制：
- RQ18称共享纯描述方案必然是第三权威不成立：若旧注册只组合描述与执行器而不重复定义业务合同，仍可单源；其新增装载/生成成本可作为真实劣势，不能用非法重复实现作为唯一备选。
- RQ18的auto最低两候选、label上限和rationale引用材料键是未批准技术候选，不反推已确认需求。理由非空/键存在不等于语义依据充分；沿用传输限额需核完整DecisionConfig，不凭注释确认所有数值。
- RQ18模型可见questions_version/摘要候选不可直接采：身份/关联仍本地，精确模型白名单待审；不将本地meta字段改送模型。
- route无业务副作用与acted=false不是同义证明。acted保留真实服务结论；是否配置无executor及其词表、真实业务动作0分别验证，不伪改回执。
- RQ19字段0命中只证明已查文件/路径；未全文读dispatch/evidence/TS等生产者，不采全仓无人写、guard永假或唯一人工恢复的全局定论。authorizes为空也不自动证明全部项目授权缺失，具体授权来源必须核。
- RQ19“复用原consumer不改语义”只能指复用低层受限操作；旧reject→halted/rework/closed-legacy和goal任意答案采用等必须按目标合同调整，不能在新adapter里原样保留。
- released不能仅由answer_kind==approve派生；必须满足有效决定、具体条件、当前授权/预算/claim/锁/版本等硬检查。reject获授权遗留收尾来自已有明确方案，不是本次reject新授关闭权；报告I1/I4需避免矛盾。
- S1 pending/answered是新技术状态方案，不是原三状态不变；所有writer/parser/提醒/TS/消费必须同步。旧approved/rejected只作历史解释，不默认许可旧运行状态继续放行。Disposition如作为意图/效果载体不能另造决策账本。
- 全文sha变化和pointer-set变化不自动等于实质变化；EOL归一也不能覆盖所有纯排版。需区分原字节证据指纹、实质影响/对象版本和复用依据，不能因无关材料或纯排版重复审批，更不归一写回历史。
- H04追加量不固定恰1轮；现有bonus一轮是源码事实，授权/具体note才限定实际追加。新目标不得继承固定数值为验收承诺。
- RQ19 R1移函数到tick顶部不足以证明与熔断链隔离；布尔preauthorized或自报人类身份不替代真实授权证明。R2双钥匙/双主体/独立账本/再熔断永久要求人工均未获要求或授权，不直接采。隔离应核实际请求源/资格和受限消费，不硬设每次真人/两人门。
- RQ20未核Python接口前，“/api/dps全部旧项”“两个面完全不相通”“窗口上下文不落盘”“所有gate/note全无载体”只限已读UI的直接语义组件/消息通道；generic raw文本和已有生命周期关联不能被据此否定。
- RQ20混合ui.status=retired到活动注册/下拉禁用不是目标方案：活动运行枚举仍精确八名，退役历史目录分列。ui.options若复制业务选项会成为第二合同，必须引用生成单源而非另存一份；全部UI用八入口名字判别合法，不笼统禁止必要业务组件。
- RQ20方案A“UI零改动”保留旧硬编码所以不完整；合法替代应同时完成旧字面分支迁移，比较纯生成渲染与生成描述+显式组件，而非把未满足需求的方案当合法备选。
- RQ20“unknown今天启动Worker”仍是派发侧静态推断，没读实际启动完整链/执行测试不能当运行证据。目标仍须证明有效图像能力；unknown可先受限核实，未核实不放行，不把未知永久判成无能力。

## RQ21/22终态吸收与边界纠正

两任务实际done、证据与终态回复已回读且分别ack；RQ21报告monitor/playground全文，RQ22报告mw.py全文。只取静态路径事实，未测试/部署/签收。补证批次结束，不继续无限追加全仓研究；PM整合D009～011及Flow。

- RQ21方案A活动/退役混入registry或/api/dps.points不直接采用；暂选八行活动注册+同单源退役目录。25旧ID全部拒绝，19是独立职责退出数，不只拒19。successor不得强制所有退出职责有唯一继任者。
- RQ21注册表12字段实际所列不止12，monitor行数2750却引用2845/2983、末尾2801～2750不存在区间；不能把这种统计/引用直接当当前源精确证据。EOF读取是worker报告，不代PM独立源审计。
- RQ21“全仓非测试0命中”“退役id当前四返回码”只限定已读路径；删除注册后的返回是推断，不是已执行迁移。enabled=false观察调用与真实退役拒绝必须分开。
- RQ21以page token证明PM/Worker资格不成立；仅声明观察通道身份/意图，不授业务角色权限。安全拒绝审计是可写真实审计，不称新增“只读审计位”并要求其记录；readonly指消费而非不存在writer。
- RQ21 route不得有任何executed/settled行的断言过强：可真实记录接收/本轮处理，不能冒充目标业务动作。签收字段数组与QG材料独立，不能把AC053归为签收数组验证。
- RQ22“CLI全经registry/唯一决定入口/只有两处真实写入”不成立于其自身human/legacy/lifecycle/book/config路径；这些必须另列真实用途、actor、写面和门，不能仅改标签使第九业务路径免责。
- RQ22 replay在旧身份判定前的风险作为真实顺序设计输入，不让零模型次数代替明确拒绝。未知/非法ID可能有真实安全失败审计，不能要求全部记录和写入皆0。
- RQ22 validate_signoff合法闭集包含continue/user-confirm，不证明其valid即有效finalize；门还须conclusion==finalize及当前受审/实质证据绑定。孤立全archive hash变化不自动等于受影响签收需重判；非实质和无关变更须合法复用。
- RQ22 dp apply保留原有意权限配置与安全门；禁止合并finalize词表。产物类型拒绝候选需保证合法权限配置不误拒，历史无类型字段只读解释不恢复旧运行兼容。dead helper、dry-run/allow-empty、人面功能和旧计数指标不得未经确认删除或接回。

## 并行补证决定
三独立只读单元：RQ18完整协议/生成契约；RQ19完整conductor/xkey/config与条件化效果；RQ20完整UI提交/上下文/历史消费者。各唯一新证据，不覆原研究；源码共享只读无冲突。PM串行写联合design、覆盖/VC/证据需求。没有新的业务意图问题需用户重复确认，两个NC作为原输出契约失败保留；未修框架产物门，也不人工重判原run为done。

## 03:09联合候选整合更新

- 本轮已写完整候选审核包：design.md的D001～012/M01～10/F01～11/16Coverage/53VC/53行映射，evidence-requirement.md逐AC证据充分性，design-write-scope.md逐文件候选面。只是文档候选齐备，不把它当用户定案或产品验收。
- PM补核全文backend/config/context/生成器与mw.py人面定点范围，证据见research/design-pm-contract-integration-20261026.md。当前decoder不保留自由模型理由；D012A模型选择预备理由须明确接受，不能拿PM note/失败reason冒充。必须完整的依据不用可裁剪context承载，原sign四部material/三数组不变。
- human ask源码明确自由问题直连模型，不仅是人工授权表单；候选human-only隔离保留必须用户审核且生产资格实际可证，不能凭标签免责第九绕行。删除有意功能另需明确批准。
- H12/policy/后继意图/三轴效果/签收validator均候选；真实资格、授权来源、受限writer、崩溃窗口效果对账仍要L2证明。没有创建实际policy、预算或恢复预授权。
- 53AC原字节核同锁稿；新鲜结构53→53零漏项/未绑定及12图零错误/警告，audit DESIGN PASS。初次157R2边引号错误后仅修本文档图语法，框架不改；完整记录见design-joint-document-check-20261026.md及json/log。机械PASS不代语义审查，仍需用户审核D012/human边界/框架脚本与配套测试面。

## 残留与未验证
未实现/测试/部署/恢复/签收；没有用户批准的联合设计或53AC/VC及证据需求产品验收。完整CLI/caller及安装内存身份仍有缺口。旧26AC、monitor8AC、dropdown、dp3反馈、formatter/check/部署债不因本轮结清。补证与设计推荐不授源码/框架/配置写权。

## 上下文来源
锁定spec及锁稿、RQ13～17唯一研究证据/原output/run/trace、design-dispatch-20261026.md、现有H确认、用户继续请求。事实来自静态报告和终态读回；未独立全面重核所有源文件，原报告不改写。
