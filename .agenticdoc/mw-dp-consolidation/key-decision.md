# KDR: mw-dp-consolidation

## 最新联合设计确认（2026-10-26；批准设计/写面，不是运行验收）
- 用户对完整审核包三项回复“1.接受。2.保留。3.批准”；原字节、对应确认及限定权限见evidence/design-approval-20261026.md。
- D012A同次模型选择PM预备可溯源依据已接受；human ask保留严格human-only隔离；框架签收门禁脚本及配套测试限定写面批准。其他clone/mirror、实际授权预算/恢复、活对象写入、部署、commit/push仍不授权。
- 联合设计D001～012、53VC/映射和逐文件面按本次审核定案，原候选推理保留；SPEC/53AC、原历史与独立未完成债不改。只能通过框架进入PLAN及继续任务准备，不跳实施门禁。

## 最新需求整合（2026-10-25毕业考后，review_status: confirmed；仅SPEC/53AC）
- 目标为六固定加两新增：dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route；八名及职责已逐项确认，旧dp7交通用行动、旧dp20交gate审批。
- 六旧职责迁移，原17项及dp7/dp20共19项退出独立职责；目标无旧编号可调用别名，历史原编号只读。此为范围草案整合，不授源码删除/迁移权限。
- dp-w-type加vision、PM四项精化、Worker固定三项fire-and-forget、gate四项及PM预拟note、H01–H13规则以最新spec/独立确认文件为准；下方“原四合同不改”“原八项/17”已被这些后续确认替代。
- RQ10/11/12并行done，唯一证据与output全文回读且acked；PM勘误不采旧候选数量套用、签收数组改null或以缺schema否定可验性。用户现已整体确认并锁定SPEC/53AC，正文不变；确认/指纹见evidence/spec-lock-confirmation-20261025.md，研究勘误见evidence/graduation-pm-review-20261025.md。
- stage-close owner已确定为dp-gate-approve；gate与PM编排/行动、QG与签收的职责已确认，具体schema/role/状态/consumer、版本/预算/授权/恢复隔离、签收词表及框架写面留联合设计。
- 本次确认后经advance_phase进入DESIGN，RQ13～17并行running，design.md仅前提锚定/候选问题，联合设计及精确写面待审。无实际预算/预授权、签收、源码/registry/服务/历史或独立key验收变更，不把DESIGN phase当设计已批准。

> 以下R/A/I保留建key时的历史快照；其中旧组成、原合同不改、归属待定语不作为当前实施或审核依据。最新依据为上述整合及spec.md。

## R（需求）
- 创建：2026-10-24；用户明确确认独立开 key。依赖 mw-decision-context，独立交付，不结案或改写旧 key 的锁定 AC。
- 来源：用户本轮确认，以及 `.agenticdoc/mw-decision-context/evidence/requirements-dp-consolidation-confirmed.md:3` 的既有确认。
- 保留：dp1-dispatch-type、dp2-checkpoint-split、dp3-worker-clarify、dp25-signoff-conclusion、dp15-autopilot-gate、dp7-gate-failure、dp6-qg-verdict、dp20-stage-close。
- 删除：其他17个DP的运行能力，包括注册、调用入口、配置、提示词及对应运行测试；保留退役历史的只读解释与测试，不保留可调用的兼容运行入口。
- 用户确认1：dp6承担正式的质量审核，不限于争议或异常处理建议。
- 用户确认2：dp15按当前设定的边界，给autopilot模式做gate审核。不能把这句话解释成扩权，也不能未经联合设计批准缩减现有边界。
- 用户确认3：独立新建 mw-dp-consolidation。
- dp1/dp2/dp3/dp25现有业务设计不改。dp6/dp7/dp15/dp20联合优化，职责、触发、材料、问题、选项、实际动作、失败策略须共同审核。
- 技术栈：Python后台、TypeScript扩展、文件驱动协调。遵守goal.md；不修改pi核心，不改凭证，不移除安全守卫。
- 需求状态：方向已确认；spec为草案，完整AC及四DP联合设计待审核，不把角色确认冒充完整设计批准。

## A（架构）
### 2026-10-26联合设计定案
- D001 活动协议：选A，否B（复用现有生成单源）。
- D002 材料/身份：选A，否B（保留分层和真实来源）。
- D003 选择/路由：选A，否B（避免动态全局限制）。
- D004 gate效果：选A，否B（集中有效性与条件复核）。
- D005 PM后继：选B，否A（持久真实意图便于恢复）。
- D006 Worker：选A，否B（保留终态及真实原因）。
- D007 签收门禁：选A，否B（复用只读validator）。
- D008 H12：选B+A隔离handler，否无持久意图方案（真实来源与恢复可核）。
- D009 注册/退役：选A，否B（物理八行降低误调用）。
- D010 UI投影：选B，否A（生成合同加专门语义）。
- D011 权限/签收：选A，否B整批类型迁移（不合并词表和执行权）。
- D012 理由：选A，B未采用（当前同次choice已有能力）。
- 出处：evidence/design-approval-20261026.md及design.md各决策Pros/Cons；未选方案保留比较，不宣称不可实现。

### 建key时待议项（历史；已由上列定案替代）
- 待联合设计。dp15六类gate的现有实际授权边界应以生产创建和消费链取证，不仅看生成注册表或旧文档。
- 待明确stage-close在dp15/dp20之间的唯一审核归属，以及stalled在dp15/dp2之间的流程授权与任务处置分工。
- 待明确dp6正式质量审核与dp25交付签收的证据复用关系，不重复审批同一个结论。

## I（实施）
- 2026-10-26确认设计及精确写面，准备通过框架进入PLAN；尚无本key产品修改/测试/活业务恢复/部署。框架已有未提交修改须实施前保存基线并协调，审批不授权覆盖他人工作。
- 本轮只创建需求文档、研究安排和框架管理状态；无源码删除或运行迁移。
- 建key轮曾因派发隐式真实dp1未授权而暂停；用户随后确认“按真实触发 就行”，允许正常派发路径真实触发dp1，恢复并行研究。不额外进行真实服务探针，不修改配置或绕过门禁。
- 旧key的格式差异决定、完整检查和独立review仍待处理；新key不豁免这些事项。
