# Plan: mw-decision-context

> 用户设计审核通过，授权推进实施到完成；AC20/VC20，指纹ae1bb1791c73。未完成测试/平台验收不跳DONE。

## 并行性分析
- 首批T01业务契约/投影/生成物与T02关联/生命周期安全存取互不争写，可立即并行。
- T01结束后T03 PM dp1/dp2与T04共享工具/dp3可并行：前者独占ui-bridge/triage-client/pm-orchestrator，后者独占decision-tool/index/worker-mode。
- T06history投影/T07case路由与UI可提前并行独立实现；T03原文producer/撤自动dp2同样独立。最终T01/T02/T05接口交付后仍必须接线验证，不把提前局部GREEN当全链通过。
- T05签收+CLI独占mw.py/decide_signoff.py，依T01/T02；不与别卡碰mw.py。
- T08集成/文档/PM最终验证在全部实现完成后串行稳定快照；review与证据检查可并行只读。
- 多会话脏工作树不是本key基线：各worker首写前保存允许面原文hash/diff（含untracked），只精准改变本key范围。不改其它key源码/生成产物/dist或依赖锁。
- 共享文件冲突：decision_points/decision_book归T01，decision_wire及新lifecycle模块归T02；需要后续动则PM转交单写者，禁止越面追绿。

## Stage 1 基础契约与安全反馈
T01：四DP简洁schema/单一model投影，保留dp2原问题，生成物一致；正确行为RED→GREEN。
T02：新决策meta/version/id和安全生命周期结果，现reader可消费基础；同次幂等、精确关联、无wire不算旧。
验收：本地生产路径输入/投影、错误零发送、安全输出、重复事件；明确发布接口，不等待其它卡改代码。

## Stage 2 Agent真实producer
T03：PM dp1原文；dp2主动工具调用接线配合T04，撤自动dp2/自动narrow，通用告警保留。
T04：PM/worker统一材料工具，dp3普通Agent生成背景和候选、原生单选消费、自动反馈；dp25 PM材料准备。
验收：faux harness，无真实api/key/pi子进程激活，真实Pythonloopback必要时tmp。

## Stage 3 签收、工作台与观察case
T05：mw CLI参数envelope和lifecycle唯一入口、dp25有效签收文件/结果复用与重试幂等；反馈失败不撤签。
T06：history新旧版本/4状态/facets/10节点安全投影、输入正文及请求返回分层。
T07：UI5列/filter/DAG/日志弹窗及4完整离线case与观察联动，25通用能力不删。
验收：真loopback HTTP+DOM shim、生产/test树字节变化0；各卡局部GREEN不是整条AC完成。

## Stage 4 稳定快照集成与收口
T08：20AC/VC全部真实生产路径对照，PM独立定向复验、read-only review、quality gate；代码变更后完整npm run check（全部输出）。check含biome --write，待实现worker停写且检查时外来diff存在则先快照、只允许本key格式改动，不擅自改回其它会话内容。
源码既有红明确失败集/本key是否新增，不能只比总数。被改测试逐文件实跑，禁止全vitest/npm test/build。Python大包测试串行避免共享端口/锁踩踏。
真实浏览器/真实Jev/部署build-install仍未授权；不得冒称这些层已验。如最终AC需要该层，报告明确阻塞并问许可，不无限派碎任务。

## Tasks 与契约
| Task | deps | AC | VC |
|---|---|---|---|
| T01-contract | 无 | 001/002/003/004/005/007/017/020 | 001/002/003/004/005/007/017/020 |
| T02-lifecycle | 无 | 010/012/014/016/019/020 | 010/012/014/016/019/020 |
| T03-pm-producers | T01,T02 | 001/003/004/010/014 | 001/003/004/010/014 |
| T04-agent-materials | T01,T02 | 005/006/007/010/014 | 005/006/007/010/014 |
| T05-signoff-cli | T01,T02 | 008/009/010/014/019/020 | 008/009/010/014/019/020 |
| T06-history | T02 | 010/011/012/013/014/015/016/019 | 010/011/012/013/014/015/016/019 |
| T07-workbench-cases | T01,T06接口,T05 CLI | 011/012/013/015/016/017/018/019/020 | 011/012/013/015/016/017/018/019/020 |
| T08-integration | T03,T04,T05,T06,T07 | 001–020 | 001–020 |

所有卡必须有信封/准确文件写面/验收命令/改动历史。T01/T02/T03/T06/T07实体已建立；T03/T06/T07提前仅做独立边界，T04/T05待API交付后精确补齐。

## 最小固定跨卡接口（内部不发模型）
T01 registry业务state：dp1 task_goal/task_requirements/task_deliverables；dp2三任务字段+pm_decision_background，可选worker_execution；dp3 question/background四键/handling_options{id,label,description}；dp25 delivery_goal/actual_completion/verification_evidence{verified,unverified}/unfinished_impact。
任务原文用string，背景/交付四部分可typed结构或string按设计但单一权威；无必要内容不编造。缺/null/[]合法性每DP逐字段明确。
T02 `DecisionMeta`固定record_version=2, logical_id, key, task_key可空, initiator_role PM/coding/research/review/unknown, retry_of可空；关联在local envelope，model0 meta。生命周期consumed/executed/settled/signoff语义与event_id去重。输出提供元信息、反馈状态与公开安全化，不以无wire判旧。
T06/T07固定投影：workbench{record_version,processing_state:processing/completed/failed/legacy,key,task_key,question_summary,dp_id,selection,initiator_role,nodes}，详情nodes按key/role/dp/input/decide/request/model/response/receipt/action排序，每项{id,label,status:observed/missing/failed,detail}；list无正文。facets{keys:string[],dps:string[]}全snapshot，不受分页影响。T01/T02在自身report中给出精确API与例子，PM用它发布最终下游接线契约。真实CLI参数读取由T05负责；先用生产函数验基础，不能只stub空壳骗GREEN。

## Stage 5 用户确认的可读性修订
T10-backend：本次置信阈值持久事实/安全history可读投影，四case完整questions，观察专用questions覆盖与统一预览构造，dp3单候选源；只写后端及后端测试/生成case。
T11-ui：十节点有向图/侧边详情、输入仅材料、实际捕获JSON格式化及原文复制、精简日志、questions编辑与完整请求预览；只写html/js/css和DOM/assets测试。
二者同时派发，接口字段以evidence/design-workbench-readable-revision.md为准；接口未知先明确报告，不越写面。PM终态后联合HTTP+DOM验证AC015/021～024、既有安全隔离及完整check；未build/真实browser不能称安装已更新/视觉已验收。

## Stage 6 当前讨论落地 T12
PM 独占页面/criteria 正规化写面，T10/T11 均终态 ack；不新派 worker，不触发隐式真实 dp1。后台 criteria 与 UI 共享观察契约，联合验收串行。
T12-page-polish.md 记录端口、5-row 分页、纵向 DAG/details、debug prose 清理、业务 state 与高级 book 分离、静态 choice criteria 编辑和实际 observation DAG 详情。先行为 RED，再最小 GREEN；非法业务 JSON 必须零提交旧材料。
验证逐文件隔离、完整 raw logs；全 npm check 在完整工作树字节副本运行，避免 biome --write 改外来源码。副本 formatter 改动不自动回写，失败必须报告具体归属与未执行后续步骤。自动重启另 key，不混当前交付。

## Stage 7 T22 任务前后状态（用户确认并入）
追加AC025/026对应VC025/026，原24不改。T22唯一PM writer，schema→Python writer/CLI→TS真实producer→history→默认任务变化UI串行接线，先RED后源码。保持local meta不发模型、队列不确定unknown、历史不回填、观察不执行业务；完整精确写面及验收在tasks/T22-task-state-transition.md。worker派发暂停，避免隐式模型请求。未真实浏览器/部署与原质量阻塞仍单列。

## 结案条件
实施产物、完整RED/GREEN、稳定集成、review/quality报告、achieved与phase gate全部符合才DONE。仅漏日志不能撤真实签收，但不能虚报反馈已成功；非阻塞技术债集中记录，不开滚动研究。旧dashboard未完成AC不因新key自动豁免。
