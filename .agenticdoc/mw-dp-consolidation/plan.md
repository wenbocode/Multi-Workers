# Plan: mw-dp-consolidation

> 状态：已经工具进入EXECUTE；本轮用户答“是”批准隔离副本实施，执行覆盖见implementation-isolation.md及evidence/implementation/isolation-approval-20261026.md。原DAG/卡保留历史；当前物理执行只用implementation-isolated-dag.json与tasks/isolated/映射卡，仍原7stage/36task/53AC-VC/依赖及语义出口，不授权主树回移或部署。计划/setup不是产品测试/QG/签收。

## 1. 锚点与交付边界
SPEC/53AC SHA256=cfe737d29aed2d0c4e79d8b02107f754f254a225bb21ea8d900eaa5ba289d006；design.md/evidence-requirement.md/design-write-scope.md确认见evidence/design-approval-20261026.md。八名/六迁移/19退出/25旧ID拒绝，D012A及human-only保留、框架两文件特批不变。goal文件驱动/锁/进程凭证隔离及不改pi核心继承。现存26AC/monitor8AC/formatter/dropdown/dp3等旧债独立，不因本计划完成。

## 2. 并行性与调度
拆分前分析见evidence/plan-parallel-analysis-20261026.md。implementation-dag.json是原依赖/写面manifest历史，implementation-isolated-dag.json是其用户批准的可逆物理映射（保留原卡/source path/hash），不是新调度服务/决策ledger；实际队列只用现有dispatch_worker及文件锁。每stage入口须前stage出口实证成立，stage屏障已展开为deps；同stage frontier立即补派，没依赖的文件并行，不对同文件双writer。两research首批可并行；后续按完整dependency/writer检查，回读实际证据后ack与补派。

单task预计30～60分钟工作粒度（research静态25分钟）；不是新grant/超时设定，预算尾段真实checkpoint收口，超界需合法处理。粒度或已批准写面不足时具体上抛，不能模型自行重写目标/任务/权限。

## 3. 七个stage（stage不是autopilot活stage文件）
| Stage | 单一交付 | 出口条件 |
|---|---|---|
| S0 | 范围/基线/资格核对 | 两只读证据齐备；用户批准的独立bytes副本/限定写面规避活源码即时切换及原dirty冲突，仅允许核实后启动纯协议T03；真实human/H12/运行身份仍相关consumer与验收阻塞，不默认获权。 |
| S1 | 八入口协议单源 | T03/T04合同/快照/TS锁通过；不调用正在运行的旧缓存入口。 |
| S2 | 纯有效性/政策/传输/材料及case | 只读规则与完整依据、book/真实关联及八case验证；四旧case字节不变。 |
| S3 | 并行producer及gate基础 | TS/PM/Worker/vision与三轴/受限effects验证；共享测试按DAG串行。 |
| S4 | 场景消费者/CLI/signoff/隔离恢复 | H01～H13实链与框架接口验证；human/H12资格未证则阻塞。 |
| S5 | 历史/观察/窗口投影 | 只读安全投影/八表单，observe_only零生产副作用；旧债不改。 |
| S6 | 集成/check/独立审计/QG | 所有规定L2和完整check证据充分，三个独立审计吸收；QG/签收各有真实合法决定。 |

## 4. 任务与依赖
每卡含ac_refs/vc_refs、原AC正文及VC四行、目标/要求/允许/禁止/验收/历史/交付。下表卡名是原历史坐标；T03～T36生效卡改为tasks/isolated/同名.md、产品写面/cwd加implementation-worktree前缀，原卡不改，T01/T02原真实终态保持。代码/验证状态以新manifest与真实服务观察为准，当前setup无产品通过。
| Task / Card | Stage/type | deps | 目标 |
|---|---|---|---|
| T01 / `tasks/T01-python-preflight.md` | S0/research | 无 | 实施前核对Python生产调用/生成入口、已批准文件现有diff和未列迁移面，输出明确可开始或具体阻塞。 |
| T02 / `tasks/T02-ts-framework-preflight.md` | S0/research | 无 | 实施前核对TS/框架原diff、真实PM/Worker与human/H12入口身份边界、单writer及未列迁移面。 |
| T03 / `tasks/T03-protocol.md` | S1/coding | T01,T02 | 八活动ID/独立退役目录、材料/角色/选择/依据投影单源成立，25旧ID在replay之前明确拒绝。 |
| T04 / `tasks/T04-context-ts-generation.md` | S1/coding | T01,T02,T03 | Python描述生成TS八入口合同/角色/白名单/字段约束，核心材料不进入可裁剪context。 |
| T05 / `tasks/T05-eight-cases.md` | S2/coding | T03,T04,T09 | 八个完整隔离case从单源产生，四旧case原字节只读保留且不再出现在可提交菜单。 |
| T06 / `tasks/T06-validity.md` | S2/coding | T03,T04 | 实现只读事项/实质依赖/授权及证据适用性核验，不以全字节hash变动强制重复审批。 |
| T07 / `tasks/T07-policy.md` | S2/coding | T03,T04 | 只读policy校验真实授权引用/范围/单位/累计预算及恢复条件，缺失或非法fail-closed。 |
| T08 / `tasks/T08-transport.md` | S2/coding | T03,T04 | 原timi通道同次业务choice与basis选择校验成立，失败无默认执行，完整材料不截断。 |
| T09 / `tasks/T09-books.md` | S2/coding | T03,T04,T08 | book及stdin准备器采用八入口完整合同，material/meta/preparation分层，非法状态先拒绝。 |
| T10 / `tasks/T10-lifecycle-state.md` | S2/coding | T03,T04,T09 | 真实request/action/settled/terminal与前后快照关联，独立保存PM note与模型选择依据。 |
| T11 / `tasks/T11-ts-tool.md` | S3/coding | T05,T06,T07,T08,T09,T10 | PM/Worker工具schema消费生成八合同，真实bound actor与辅助材料分层，退役hook不代造请求。 |
| T12 / `tasks/T12-pm-followup.md` | S3/coding | T05,T06,T07,T08,T09,T10 | 已准备PM意图恢复/去重和真实后继请求可核，不新建决策账本或同步等待Worker。 |
| T13 / `tasks/T13-pm-orchestration.md` | S3/coding | T05,T06,T07,T08,T09,T10,T11,T12 | PM真实准备note/basis、四编排选择与steer/need_fix后继调用接线，不降低目标或夺claim。 |
| T14 / `tasks/T14-vision-dispatch.md` | S3/coding | T05,T06,T07,T08,T09,T10,T11 | 四任务类型选择与真实有效image capability门接线；未知/不支持不启动且不退coding。 |
| T15 / `tasks/T15-worker-reachability.md` | S3/coding | T05,T06,T07,T08,T09,T10,T11 | Worker自主continue/terminate/investigate三分支、真实结论/有界补证消费成立。 |
| T16 / `tasks/T16-ts-task-state.md` | S3/coding | T05,T06,T07,T08,T09,T10,T11 | TS任务前后快照与Python事实链保持真实关联和null/[]区分。 |
| T17 / `tasks/T17-gate-contract.md` | S3/coding | T05,T06,T07,T08,T09,T10 | gate transport/business/effect三轴writer/parser与事项引用跨语言一致，answered不是released。 |
| T18 / `tasks/T18-gate-effects.md` | S3/coding | T05,T06,T07,T08,T09,T10,T17 | 四分支受限effects/CAS/真实失败出口成立，approve重核当前条件，reject不默认关停/返工。 |
| T19 / `tasks/T19-conductor-h01-h05.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18 | H01启动/H02关闭/H03停滞/H04软追加/H05复核条件接入原conductor且不自批解锁。 |
| T20 / `tasks/T20-xkey-contract.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18 | H06指定goal采用/H07受限跨key/H08具体冻结条目变更复核与实质重验。 |
| T21 / `tasks/T21-recovery-handler.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18 | H11/H12独立受控handler验证真实来源/预授权/原因消除/观察再熔断，普通链自调用明确拒绝。 |
| T22 / `tasks/T22-signoff-validator.md` | S4/coding | T06,T10,T11,T12,T13,T14,T15,T16,T17,T18 | 当前valid且finalize与对应证据成立，key签收和authority-change typed消费严格隔离。 |
| T23 / `tasks/T23-cli-request-replay.md` | S4/coding | T09,T11,T12,T13,T14,T15,T16,T17,T18 | 所有生产CLI/book/stdin/replay先活动身份/合同校验，25旧ID明确拒绝而非复用历史成功。 |
| T24 / `tasks/T24-cli-human-sign.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18,T21,T22,T23 | CLI human-only保留隔离、同次sign writer/只读validator接口及typed apply明确拒绝串接成立。 |
| T25 / `tasks/T25-framework-sign-gate.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18,T24 | 只在原必需范围用只读validator识别当前valid且finalize及对应证据，不豁免其他phase硬门。 |
| T26 / `tasks/T26-autopilot-recovery-closure.md` | S4/coding | T11,T12,T13,T14,T15,T16,T17,T18,T19,T20,T21,T25 | H09/H10有界恢复/重规划、H11/H12受控入口及H13签收/阶段关闭实际接线保留旧失败与累计量。 |
| T27 / `tasks/T27-history-projection.md` | S5/coding | T10,T15,T18,T19,T20,T21,T22,T23,T24,T25,T26 | 八入口note/模型依据/后继/request/action/settled真实只读投影，退役原记录不回填。 |
| T28 / `tasks/T28-observation-server.md` | S5/coding | T05,T19,T20,T21,T22,T23,T24,T25,T26,T27 | 观察八合同/退役只读目录及隔离WireScope提交成立，观察成功无业务executor。 |
| T29 / `tasks/T29-web-components.md` | S5/coding | T19,T20,T21,T22,T23,T24,T25,T26,T27 | 八生成合同表单与独立note/依据/后继/执行/结算语义组件和安全DOM成立。 |
| T30 / `tasks/T30-window-console.md` | S5/coding | T19,T20,T21,T22,T23,T24,T25,T26,T28,T29 | 窗口/console消费八合同与真实状态，未知能力/依据/动作不伪报成功。 |
| T31 / `tasks/T31-integration-evidence.md` | S6/coding | T26,T27,T28,T29,T30 | 逐VC真实producer→writer→consumer→projection L2证据完整，并发/崩溃/秘密/旧ID/角色负例有实测断言。 |
| T32 / `tasks/T32-protected-check.md` | S6/coding/PM-direct | T27,T28,T29,T30,T31 | PM串行执行等字节保护副本中的完整npm run check与生成锁，输出真实完整结果及旧债/新回归分类。 |
| T33 / `tasks/T33-review-protocol.md` | S6/review | T27,T28,T29,T30,T32 | 独立只读审计八协议/传输/CLI/signoff/human边界及对应原始L2证据。 |
| T34 / `tasks/T34-review-effects.md` | S6/review | T27,T28,T29,T30,T32 | 独立只读审计H01～H13/真实授权/恢复隔离/锁/预算/对账及效果证据。 |
| T35 / `tasks/T35-review-ts-ui.md` | S6/review | T27,T28,T29,T30,T32 | 独立只读审计PM/Worker/vision/窗口观察历史的资格、真实终态与来源安全。 |
| T36 / `tasks/T36-formal-qg.md` | S6/review/PM-direct | T27,T28,T29,T30,T33,T34,T35 | PM正式QG核对53AC/VC与独立审核证据，明确可签收或具体缺口，不自动完成/关闭stage。 |

## 5. 单writer/交接规则
唯一owner来自卡product_write_face，均为批准清单子集，不授目录通配。共用文件仅在有序依赖结束后接管；before/after bytes/SHA256/EOL/原diff和合同版本必须留证，接收者读完整最新源再edit。代码状态/验证状态分别更新，not-queued/pending/running/done由真实服务状态对照，不手改原worker终态。测试文件也算共享文件，T31要接管前序全部测试writer。新增需修改未列文件、目录/模板/提示词/类型依赖必须先报exact path/影响/最小补面，审批前停止对应任务。

## 6. 测试/证据执行顺序
先每task红测→最小实现→绿测；新增/修改测试逐文件具体运行，Python hermetic HOME/project/env/fake backend、禁自动插件/cache/pycache写，TS harness+faux provider。T31提供53VC producer→writer→consumer→projection实链及逐case原始记录；所有值按fixture范围实测，attempt/业务决定/动作/完成分开，NULL与[]保真。Coded writer不能fixture手写gate/ledger/PASS。

T32 PM串行保护副本中完整npm run check，版本/源码/config/scripts/依赖链接等价须核，全部stdout/stderr和rc保存；Biome --write --error-on-warnings真实失败后后链未跑明确标记。不安装/降依赖/build/npm test/full vitest，不把非零旧check吞掉；必要修复回原卡/另批，不替其他session处置旧formatter。当前代码副本检查≠实际已部署，安装/内存身份仍未验。

## 7. AC/VC覆盖与验收责任
所有AC-001～053由同号VC保持原断言。编码/集成卡引用全部53个AC/VC，逐case/原记录与Output同时满足才充分；T31不单凭计数/worker done/observe_only/全grep通过，T33～T35只读分域独立审计。T36 PM按evidence-requirement.md逐AC正式QG，必要证据/check/入口资格缺口不通过。签收仍原适用范围内合法dp-sign-key同次finalize及对应证据，QG和phase/stage关闭分开，不能伪签或二次批准。

## 8. 失败、现有变更及运行身份
源代码现仍旧25入口；计划/机械门不能称已迁移。首批T01/T02具体核对现有dirty/未列caller/身份边界/框架mirrors，不能复用报告EOF冒充独立全源审核。框架两脚本及mirrors已有原diff，未协调独占不得写；不覆盖或归为本轮修改。

任何失败按实际证据debug/合法决策流程处理；服务或模型不可用保持阻塞，正常派发可能消费既有隐式dp1，不做额外真实决策探针。现PID仅服务在运行证据，不证明其加载新源码；运行缓存不识别新八名则具体申请必要reload/部署，不回用旧编号/暗自重启/切换provider或绕刹车。human-only/H12实际来源未证时任务blocked，不能以新kind/token/TTY/自报role冒充。旧失败/次数/要求/批准/worker状态原字节保留。

## 9. 明确禁止与下一动作
固定八名dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；25旧编号拒绝、原历史只读。模型理由为同次选择PM预备依据，失败reason/概率/note不冒充理由。保留原角色/claim/O_CREAT|O_EXCL锁/凭证/硬预算/进程隔离；route不授权，选择/请求/动作/结算/完成分开。禁止pi核心、冻结config/活policy/gate/brake/ledger/权限/预算/签收/goal/spec/其他key/四旧case、依赖lock/dist/mirror/install/服务重启/commit/push。不删human ask/legacy显示/dead helper；未列面具体报告后另批。只在隔离fixture走生产writer，不真实provider。编码前完整读取本卡文件到实际EOF、保存bytes/SHA256/EOL/既有diff并确认单writer；只做获批差异，先红测再绿测。修改TS使用erasable语法/顶层imports、不滥用any，读node_modules类型。不得手改Phase或原worker run/output。超原预算实际检查点收口，不重置watchdog/私设timeout/grant。

原计划已通过advance_phase进入EXECUTE，T01/T02终态已吸收/ack；此次隔离覆盖setup/新卡检查后仅派T03，其他stage仍真实语义出口/原DAG，不以acked跳依赖，不改Phase。PM仍常驻，原RQ15/16退出状态不改、不结案其他key，不写活autopilot stage/roadmap。
