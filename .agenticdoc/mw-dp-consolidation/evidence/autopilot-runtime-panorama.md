# Autopilot运行全景流程图

> 状态：当前源码静态运行模型，非部署验收；最后一图为未批准目标态。
> 用途：为H01-H13逐项需求澄清提供共同上下文。不是新的design.md，不批准实施或实际自动授权。
> 对齐goal.md：文件驱动协调、并行Worker、Extension API边界；不引入新中心服务、不改pi核心。

## 阅读约定

- 图1是总览，图2-7展开真实子流程；图8单独画拟议DP接线，禁止把它看成当前实现。
- 实线为当前函数控制/数据路径；标注“人工/停等”的节点不表示天然必须人工。
- 新生成gate通常在后续tick判答与消费；orchestrate先自动判已有gate，再消费答案，因此已有gate的live自动答案可在同tick生效。
- “答复已写”不等于“业务已推进”。消费者、条件与幂等记录仍须执行；stage/key/phase/ticket是不同状态维度。
- 以下含并列分支的图是结构总览，不表示各模块按图上布局并发执行。真实orchestrate顺序见§9。

## 1. 全景总览：周期循环、stage与key

```mermaid
flowchart TD
    T["conductor启动后周期tick<br>beat、有效配置、提醒、契约锚"]
    B{"可编排且goal未被待答门阻断?"}
    O["orchestrate<br>RULES判门、消费答案、孤儿恢复、claims"]
    R{"roadmap已存在且可读取?"}
    W["缺roadmap:派roadmap-writer<br>损坏:告警并跳过，不当空路线"]
    S["stage激活<br>pending建stage-confirm；halted停等"]
    K["running stage内key前沿<br>状态、claim、依赖、在途与容量过滤"]
    P["SPEC-DESIGN-PLAN-TASKS<br>生成材料、L1审计、L2补证、advance"]
    E["EXECUTE<br>任务DAG、写面守卫、受限并行与重试"]
    V["VERIFY<br>L3评审、修复、done机械事务"]
    C["stage收口检查<br>终态、无在途、证据无争议"]
    G["gate文件闭环<br>生成、等待/答复、分类消费，见图2-5"]
    N["结束本tick；按配置间隔再读文件"]
    T --> B
    B -->|可编排| O
    B -->|disabled或paused| N
    B -->|goal变化建门或仍待答| G
    O --> R
    R -->|缺失或读取失败| W
    W --> N
    R -->|可用| S
    S -->|已running| K
    S -->|新确认门| G
    S -->|halted或提案耗尽| N
    K -->|生成相位| P
    K -->|execute| E
    K -->|verify| V
    P -->|预算或失败升级| G
    E -->|重试耗尽等失败| G
    V -->|质量或契约等升级| G
    P -->|本步结束| N
    E -->|本步结束| N
    V -->|本步结束| N
    K --> C
    C -->|可收口:生成stage-close| G
    C -->|尚不可收口| N
    G --> N
    N --> T
```

图中key状态与收口是同一tick的两个视角；实际stage收口检查在逐key派发之前。goal-change门在tick层优先拦截，不经过后面的RULES pass，见§9已知缺口。

## 2. Gate的生成、答复与消费

```mermaid
flowchart TD
    P["触发生产者<br>stage、预算、stall、goal或xkey"]
    L["按各生产者范围去重<br>获取gates文件锁"]
    C["gates.create<br>分配gate ID、status=pending"]
    F["补默认字段/已知机器事实<br>期限、default_action、authorizes"]
    S["auto模式启用时保存created证据快照<br>随后释放锁、记gate-created等事件"]
    G["持久gate文件<br>等待答案，不直接改phase"]
    H["人工入口<br>TS console或Python CLI"]
    A["现有RULES自动路径<br>shadow只记录；live可写窄approve"]
    V["各答门入口校验与gates锁<br>不把展示身份当执行凭证"]
    W["更新答案字段<br>approved或rejected；保留其他内容"]
    D["按kind、key状态及关联信息路由消费者"]
    U["实际stage/key/ticket变更<br>检查状态与幂等条件"]
    M["适用消费者记录consumed及证据<br>不可把答案落盘当消费成功"]
    Q["budget/goal等通过专属轮询逻辑生效<br>不统一走stage消费分支"]
    R["待答提醒、超时升级或延期复核<br>不是自动批准"]
    P --> L --> C --> F --> S --> G
    G --> H --> V
    G --> A
    A -->|live批准且约束通过| V
    A -->|shadow、暂缓或升级| R
    V --> W --> D
    D -->|状态变更型| U --> M
    D -->|轮询型| Q
    G -->|仍pending| R
    R --> G
```

- 标准生成口`_create_gate`为默认字段盖章；goal-change在tick中直接create，但同样先盖章再created快照。
- `authorizes: []`是新门默认；TS答门省略/空authorizes保留旧行，并不撤销授权。
- Python CLI reject有`--confirm-destructive`前置；TS console当前无同等二次确认，不能画成一致。
- `_mark_gate_consumed`等适用消费者记录消费；budget与goal消费方式不相同，不保证每类都有相同字段或步骤。

## 3. Stage生命周期与两个阶段门

```mermaid
flowchart TD
    P["roadmap中的pending stage提案"]
    G["生成stage-confirm<br>初次激活或前stage收口后开放"]
    A{"stage-confirm答案?"}
    W["仍pending:停等/现有RULES处理"]
    R["reject后有界重提案<br>新roadmap比拒绝记录更新才建新门"]
    H["已用两次提案:等人修改roadmap"]
    K["approve消费成功<br>stage=running，释放key派发"]
    V{"全部key为done/closed-legacy<br>且无在途、无证据争议?"}
    D["继续key工作或处理pending-review<br>不生成stage-close"]
    C["写stage-close dossier<br>生成stage-close门"]
    J{"stage-close答案?"}
    N["approve消费成功<br>当前stage=closed；开放下一确认门"]
    X["reject消费成功<br>stage=halted；普通状态机不回退"]
    P --> G --> A
    A -->|pending| W --> A
    A -->|rejected| R
    R -->|额度未耗尽且新提案落盘| G
    R -->|两次已耗尽| H
    A -->|approved| K --> V
    V -->|否| D --> V
    V -->|是| C --> J
    J -->|pending| C
    J -->|approved| N
    N -->|仍有下一pending stage| G
    J -->|rejected| X
```

`pending-review`不是终态，既不释放依赖，也不允许stage收口。stage-close批准不自动批准下一stage；reject不是可逆hold/rework。gate生产者负责pending去重，图中的回环不表示每tick重复生成dossier或新门。

## 4. Key相位与EXECUTE任务推进

```mermaid
flowchart TD
    K["通过key前沿过滤<br>读取当前phase与真实worker轮次"]
    P{"当前phase?"}
    A["SPEC/DESIGN/PLAN/TASKS<br>缺材料先派phase-writer"]
    L["材料齐后L1 dossier<br>TASKS另查plan引用任务卡缺口"]
    B{"存在blocking gaps?"}
    F["额度内L2 verifier<br>同轮phase-writer补证，再审计"]
    G["额度耗尽建budget-exhausted<br>approve加1轮；reject/加轮耗尽转stalled"]
    X["advance框架机械门<br>成功才改变phase；连续失败会stalled"]
    E["EXECUTE读取任务卡DAG<br>损坏/歧义整key回退串行，不扩大并发"]
    D["任务前沿受容量/写面守卫限制<br>等待冲突不是stalled"]
    R["派coding Worker；按真实轮次重试<br>失败额度耗尽生成stalled"]
    V["全部任务family有done<br>advance到VERIFY；进入图6"]
    N["本tick结束；后续tick重读文件"]
    K --> P
    P -->|生成相位| A --> L --> B
    B -->|无blocking| X
    B -->|有blocking且有额度| F --> N
    B -->|无额度| G --> N
    X --> N
    P -->|execute| E --> D
    D -->|有可派任务| R --> N
    D -->|全部任务已done| V
    D -->|等待依赖/在途/写面| N
    P -->|verify| V
    P -->|done| N
```

相位路径是SPEC→DESIGN→PLAN→TASKS→EXECUTE→VERIFY→DONE。这个顺序是当前机械advance框架路径，不代表每相位都新建人工gate。已有跨key/写面硬拒绝不能被模型建议跳过。

## 5. 现有RULES自动答门与延期复核

```mermaid
flowchart TD
    A{"auto_gate_mode?"}
    O["off:不运行自动pass"]
    Q["读取auto-decisions与熔断状态<br>选择有规则、未处理的pending gate"]
    B["熔断:写/保留auto-brake与升级记录<br>停止自动pass，非关闭全部conductor"]
    F["gate_facts与类型规则命题"]
    R{"规则结果?"}
    D{"可延期的key门且无在途等条件满足?"}
    P["shadow仅defer预览<br>live改key=pending-review并记defer"]
    K["guard通过且不适用延期<br>不写答案，不等于批准"]
    S{"shadow还是live?"}
    J["shadow记录判定<br>gate与roadmap不变"]
    L["live批准前检查<br>证据绑定/漂移、shadow资格、夜间与key配额"]
    W["写approved与auto决策记录<br>后续分类消费者推进业务"]
    E["live升级记录<br>gate保持待答，进入提醒/人工处理"]
    Z["结束该pass/该gate处理"]
    A -->|off| O --> Z
    A -->|shadow或live| Q
    Q -->|熔断激活| B --> Z
    Q -->|有新待判gate| F --> R
    Q -->|无待判或已处理| Z
    R -->|approve| S
    R -->|无动作或escalate| D
    D -->|可延期| P --> Z
    D -->|不可延期且无动作| K --> Z
    D -->|不可延期且escalate| S
    S -->|shadow| J --> Z
    S -->|live且approve| L
    S -->|live且escalate| E --> Z
    L -->|约束通过| W --> Z
    L -->|约束失败| E
    W -->|答案写入失败| E
```

这是现有机器RULES机制，不是dp7/dp15/dp20。pending-review在48h期限/stage闭环压力下升级复核；人答原门approve=resume、reject=rework，均回running。不是“暂缓即收口”，也不是“shadow实际执行”。

## 6. VERIFY：L3、修复与DONE事务

```mermaid
flowchart TD
    A["VERIFY无在途评审/修复时<br>派L3 reviewer或读取最新裁决"]
    V{"L3结果与来源?"}
    R["below/有效裁决但产物不足<br>额度内repair后重新L3"]
    U["流中止/无裁决/来源可疑<br>按各自受限规则重评，不冒充质量below原因"]
    S["相应评审/修复额度耗尽<br>mark_stalled并生成stalled门"]
    C["meets且来源合格<br>done事务先核冻结AC/VC授权"]
    H["契约未授权变更<br>未写QG/achieved前拒绝并stalled"]
    D["保存QG与meets来源<br>受控写achieved草稿及PASS行"]
    F["advance DONE机械门<br>含条件适用的签收、证据与报告核验"]
    P["门拒绝:保留真实meets<br>草稿问题受限重提；其他问题重试/失败升级"]
    I["advance成功后回读index<br>确认DONE，不以exit=0代替状态核验"]
    M["下一相位机步将key标done<br>进入stage收口条件检查"]
    A --> V
    V -->|below或草稿不足| R
    V -->|中止/缺裁决/来源可疑| U
    R -->|额度内修复完成| A
    U -->|可重评| A
    R -->|耗尽| S
    U -->|耗尽| S
    V -->|meets且来源合格| C
    C -->|无授权的变化| H
    C -->|契约核查通过| D --> F
    F -->|失败| P
    P -->|可重提/重试| A
    P -->|相应额度耗尽| S
    F -->|成功| I
    I -->|状态不符且修正仍失败| S
    I -->|DONE已确认| M
```

key决策签收由已有dp25业务承担，但当前done事务不自动触发dp25；不要在当前图虚构该调用。框架签收旧结论词表与dp25新词表不一致，是已知接线/适配债。L3 meets不保证DONE，也不允许伪造below覆盖机械门失败。

## 7. 跨key修复分支与gate外升级

```mermaid
flowchart TD
    A["xkey_repair开启时<br>聚合L3 below中的handoff注册"]
    T["验证注册/owner状态<br>合成ticket与授权请求"]
    G["生成xkey-authorize门<br>此时还没有proposal执行产物"]
    V{"授权门答案?"}
    N["拒绝:ticket rejected并记录"]
    P["批准消费后ticket approved<br>派proposal worker"]
    E["proposal派发耗尽<br>持久proposal_exhausted_at并报人"]
    D["proposal落盘且匹配冻结ticket<br>写面/blast radius/内容条件复核"]
    X["受限apply与验证<br>保留replay/evidence/ledger"]
    C["成功:ticket闭环<br>source key可再推进/重评"]
    R["失败:复原/记录具体失败或阻断<br>按ticket状态处理，不擅改其他写面"]
    W["仍pending或不满足处理条件<br>等待后续tick/人工补信息"]
    A --> T
    T -->|合法需授权| G --> V
    T -->|无可用ticket/条件不符| W
    V -->|pending| W
    V -->|rejected| N
    V -->|approved| P
    P -->|派发耗尽| E
    P -->|proposal已落盘| D
    D -->|条件满足| X
    D -->|拒绝/不匹配| R
    X -->|验证成功| C
    X -->|失败| R
```

图里approve是授权后续受限proposal/apply，不是对已完成proposal的追认。contract-change是批准gate的附加授权，与xkey-authorize不是同一业务许可。roadmap提案耗尽、halted stage恢复、auto-brake恢复也存在gate外停等，不统一塞进普通reject。

## 8. 拟议DP接线位置（未批准，当前不存在）

```mermaid
flowchart TD
    E["待决定事件与证据版本<br>普通gate或gate外恢复"]
    H["确定一个业务owner<br>推进授权/失败恢复/阶段收口"]
    M["准备该场景闭集材料<br>目标、影响、权限、预算、事实与可执行选项"]
    D["默认先DP决策<br>dp15/dp7/dp20候选归属待逐项确认"]
    V["答案校验与硬保护<br>权限、证据时效、状态、关联与幂等"]
    A["受控消费者执行<br>真实动作才记执行与settled"]
    U["人工升级<br>记录不可代替的业务信息或超授权原因"]
    R["可补证/工程修复先完成<br>新证据版本重新决策，避免同版本双审"]
    E --> H --> M --> D --> V
    V -->|授权内且可执行| A
    V -->|可补事实/修复| R --> M
    V -->|需用户意图或新权限| U
```

模型服务不可用等真实阻塞须停止并报告；本图不授权绕过UNAVAILABLE或现有硬检查。dp25仍为key签收，dp6仍为正式质量，dp2/dp3业务合同不变。

## 9. 源码坐标与当前缺口

核心源码：`packages/multi-workers/autopilot/conductor.py`。

| 图/步骤 | 主要完整函数坐标 |
|---|---|
| 启动与周期 | main:8673；tick:3769；配置停机、提醒、契约锚、goal检测在orchestrate之前 |
| 编排顺序 | orchestrate:595；依次auto_decide_gates→_consume_answered_gates→reconcile_orphans→claims→roadmap读取/激活→key恢复→xkey聚合/proposal/apply→每stage延期复核/收口→逐key派发 |
| gate生成 | _create_gate:3903、_stamp_gate_defaults:3952、_gate_default_fields:4013；goal直建:3812附近 |
| stage门 | _consume_answered_gates:910、_ensure_next_stage_gate:1065、_stage_activation:1090、_activate_pending_stage:1110、_dispatch_roadmap_writer:1176、_stage_closure:1272 |
| key相位/执行 | _advance_key:1619、execute_loop:1953；失败连续计数:_record_advance_result:1565 |
| 自动机制 | _auto_decide_one:8348、auto_decide_gates:8467、gate_facts:7381、_defer_declined_gate:8277 |
| pending-review | _process_deferred_reviews:4451、apply_review_decision:4494、_apply_review_decisions:4540；key恢复:4146/4215 |
| VERIFY/DONE | _verify_loop:2626、_done_transaction:2932；advance.py封装框架门 |
| xkey | _xkey_aggregate:4967、_xkey_ensure_gate:5127、_consume_xkey_gate:5201、_xkey_proposal_stage:5279、_xkey_proposal_exhaust:5363、_xkey_apply_one:6190 |
| 答门 | answer_gate_auto:7913、answer_gate_confirmed:7981；TS gate-writer.ts:169、console.ts:457；CLI mw.py:_ap_answer:9438 |
| 签收硬门 | .agents/skills/agentic-task/scripts/advance_phase.py:_decision_signoff_problems:309 |

当前实现必须显式保留的缺口：

1. goal-change pending导致tick提前返回，后面的RULES不会处理该门；任何已答状态随后都刷新baseline并恢复，与reject保持halted文案不一致。
2. 标准stage-confirm/budget等生产者未填RULES读取的部分机器事实，不能把“有规则”画成“通常自动放行”；外部/手填字段路径仍未全审。
3. dp7/dp15/dp20登记未接线，没有当前自动DP消费链；图8只是讨论入口。
4. stage-close reject为halted终态，不能拿来表达hold/rework；halted阻断后续激活。
5. 人工TS/Python reject确认不一致；空authorizes不等于撤销。重评与负记录撤销函数未找到生产创建入口。
6. diagram基于静态读回，不读取当前live配置/gates/ledger，不验证服务启动、实际触发频率或真实多tick执行。完整外围模块与调用者审计仍有未覆盖。

## 10. 验证边界

本轮已运行`python .agents/skills/agentic-task/scripts/check_mermaid.py .agenticdoc/mw-dp-consolidation/evidence/autopilot-runtime-panorama.md`，结果`MERMAID GATE PASS: 0 error(s), 0 warning(s)`。它只检查常见语法风险，不等于浏览器渲染、源代码测试或运行路径验收。没有PNG/SVG生成或线上操作。

本轮复用RQ4/RQ5/RQ6并行研究，PM定点全文补读上述核心函数并串行综合；不声称自己通读整个conductor或全仓零遗漏。
