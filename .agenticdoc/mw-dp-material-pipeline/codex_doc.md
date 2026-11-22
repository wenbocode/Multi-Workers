# mw-dp-material-pipeline · Codex PM 轻量任务

<!-- mw:codex-template-version: 3 -->

**仅供 Codex PM 使用。** 本页保存目标、验收标准、关键决定、进度和接续信息。只有派给 MW Worker 的工作才需要在本 key 的 `tasks/` 下建立任务卡。

- Workflow: codex-lite
- Key: mw-dp-material-pipeline
- Phase: DONE
- Claim-Id: —
- Status: idle

以上机器字段由 `codex_pm.py` 管理。`_index.parallel` 记录相同的真实阶段、认领和状态；`_index.md` 是全部 active key 的投影。`pm-state.md` 只保留认领接口，`Phase: init` 表示未启用 SDD。

## 目标

按当前八 DP 详细设计实现可追溯材料准备与决策链路，改善 PM/Worker 协作的决策有效性与可回放性。按用户推进指令开始实施，以 QG 的同次证据链为首个验收切片，再扩至其余 DP。

## 范围

控制与目标工作区为 E:/gitlite/Multi-Workers。实施范围是决策材料、预算、传输与 PM/Worker/monitor 接口。以各任务卡的写面为准，验证使用隔离项目及离线替身。150 个 v0.5 冻结副本保持原件。涉及卡片遗漏的公共模块，先核实际接线与冲突，然后补记写面。

## 验收标准

- AC-001: 固定候选完整且不是单选项，auto仅接受2..5真实不同路径，QG覆盖pass/fix/reopen。
- AC-002: 文件必要正文进入请求，超限压缩保留失败/未知/覆盖与候选判据，仅路径材料被拒绝。
- AC-003: desc 最多 10 句。PM 与 Worker 按固定本地预算预计算，1000 单位放行，1001 单位发送前拒绝且决策网络尝试为 0。
- AC-004: 每个模型字段可追溯，本地身份/准备过程/actionplan/作者预期不整体入模。
- AC-005: 缩写/代码/编号在当前请求有完整适用解释，错对象与悬空引用可检出。
- AC-006: QG先独审并核完整AC/VC；sign带目标/偏差和当前同范围QG，失败/未测保留。
- AC-007: prepare顺序/权限/模型/revision/发布吸收由host守卫，越序/越权/旧报告不可发布。
- AC-008: 可区分性覆盖全部候选对，缺偏好/等价有明确状态且不私删合理候选。
- AC-009: auto路径后继/信息价值/停止/上限明确，循环/超预算/刷新额度被拒绝。
- AC-010: 单wire按同版配对恢复全部原因/剩余项，未知wire或错revision不被业务采纳。
- AC-011: 原事项预算跨准备/模型/等待/返工连续，同语义去重，已发未知结果不盲目补发。
- AC-012: 本地材料、实际完整请求、原始返回和真实业务检查分离保存，monitor直接显示原始返回。
- AC-013: 准备失败/DP关闭/不可用沿原continuity接回，无新全局等待/审批或角色冒充。
- AC-014: 必要定向验证、仓库检查和独立复核完成后才报告生产接入通过，历史API实验不充作实现验收。
- AC-015: [REVISED 2026-11-19 用户澄清] 八DP四段参考/9个唯一案例，历史输入/返回原件一致，当前PM参考另标来源。
- AC-016: [REVISED 2026-11-19 用户澄清] 原版/整合版cohort不串版，9份PM参考理由/原因/后续/禁止声明及事实变化对照。
- AC-017: [REVISED 2026-11-19 逐项复核] 9例×4段36行原件/当前实现对照，逐字段基准/观测/规则/差异依据及AC/VC齐全；全部原因与PM语义核对，已知负例不放宽，缺段/无依据差异/未验证/假执行不可通过。
- AC-018: [REVISED 2026-11-19 用户澄清] 历史与当前参考类别明确，缺失生产PM/执行回执仍为空，无新调用/派发/伪造。

## 关键决策

流程为Codex PM codex-lite，保持SPEC；用户明确要求的spec/design/plan/任务卡作为实质开发合同，不调用普通SDD阶段脚本混写轻量状态，不宣称已过正式SDD门禁。当前spec为draft，未记录虚假的用户锁定时间。

用户要求独立新key，依赖来源为已完成mw-dp-detailed-design与mw-dp-design-validation-integrated；不认领/改写其它key。docs为原v05的字节副本（去除体积大的QA截图目录），保留相对链接与API证据；新增目录说明放key根README，不改冻结副本。QG历史例缺reopen保留为已知差额，需未来修复新输入。

## 执行与验收

仅编制规划文件并自查副本/引用/AC→VC→任务覆盖，不运行产品测试、不派Worker。任务卡均planned，未实现/未验证，真实API新增0次；实现AC当前全部待执行。

- 2026-11-19已复制v05中150个设计/原始证据文件，1,515,377字节；排除大体积QA截图目录，所有复制/来源SHA-256一致。
- v1已完成draft spec（14 AC）、design（14 VC/全覆盖映射）、plan、证据要求、KDR和研究留底。
- v1已完成T01—T09九张规范卡及tasks/index.json；每卡有依赖/AC/写面/验收argv，未来测试交付目前不创建/不运行。
- 纯规划自查见evidence/planning/verification.json、traceability.json、mermaid-check.log；依赖无环、AC→VC→主任务覆盖100%、文档链接与Mermaid检查通过。不是本key实现验收。

2026-11-19 v2反馈：同意v1仅保留合成HTTP回包/离线计划，没有所有DP的真实派发与后继结果验收。追加AC/VC-015—018和八DP样例/对比规约，新增T10/T11，T08/T09增加覆盖/采集/独审依赖。v1规划文档/检查结果保存在evidence/planning/revisions/v1；docs冻结副本不变。当前18 AC/VC、11张卡，真实闭环0/8，全部not-collected/not-run。

v2纯规划检查通过：18 AC/VC/主任务覆盖100%，11张卡无环，8场景全部结果为空且明确not-collected，28固定离线分支计划完整，150原件未变。T11仅原PM执行、普通Worker不可自动派发。当前产品测试/派发/新API均0。

## 接续须知

用户已要求按两个 key 推进。调用策略 key 完成后按 `codex_pm.py status` 恢复本 key，并复核权威索引与共享文件。无在途 Worker。按 [同次对账合同](decision-chain-reconciliation.md) 从 QG 开始记录生产入口和离线验证。规划记录保存在 planning-delivery.md。

## v3范围纠正与当前交付

用户明确要v0.5决策本→实际模型输入→真实返回→PM参考裁定全记录作开发范本，不是未来live采集。现已整理8DP/9案例、两个cohort及9份当前PM参考接回，标清历史生产PM/执行回执缺失。旧v2计划在revisions/v2-before-v05-clarification保存，AC-015—018按澄清修订，T10改为现有范本消费，T11撤回不再是验收依赖。所有实际API原件不改，无新调用/派发；产品实施仍未开始。

v3文档/参考资产自验：9例实际请求/回包逐字节一致，111原案例/捕获与150冻结副本不变；9份PM参考/校验向量齐全，8DP覆盖。23页/70页签HTML检查及PM/原始回包视觉检查通过，18 AC/VC映射与10待执行卡无环。证据见evidence/reference-records/verification.json、visual/和evidence/planning/verification.json；不是产品实现或独立复核通过。

## 2026-11-19 四段引用与验收复核

按用户要求只复核/修正规划：补齐T01—T07直接引用；T01—T10统一采用reference-comparison-contract.md及唯一范本索引，明确9例×4段36行原件/当前实现对照、字段差异依据、负例拒绝及PM语义审查。spec AC-017、design VC-017和规划/证据要求同步，spec仍draft，产品测试/派发/新API均0。保持SPEC，完成文档复核后释放；不实施。

自查通过：[复核报告](evidence/planning/four-stage-audit/report.md)与verification.json。10卡引用一致、18 AC/VC主任务覆盖100%、任务无环、71处引用有效；9例四段/全部原因一致，150冻结副本及111原案例捕获未变。Mermaid检查0错误/0警告。这是文档/范本自查，未来36行产品对照及独立复核仍not-run。

## 2026-11-22 当前源码复核

补充[现状与差额](evidence/research/current-code-review-20261122.md)，更新 design、plan 和 T01–T08 的复用入口与剩余验收。生产 renderer 的随附 QG 样例仍只出 fixA，auto 的六项及改名等价路径仍通过旧校验。文件/配对/来源新鲜度定向回归 101 passed、2 skipped。四段范本和 36 项验收继续适用，当前阶段为 SPEC。

同日[跨项目回执采集](evidence/dp-blocked/20261122/report.md)扫描 23 个目录，在 6 个项目收集 193 条唯一回执。计划与 T08 已引用回执作为附加回归输入。

193 条回执按实录归入 13 类，完成项目、DP、原因的交叉统计和 10 个典型四段对照。spec、design 和 T01–T09 引用同一份[案例与差额](evidence/dp-blocked/20261122/v05-blocked-comparison.md)。已有能力和诊断复用，运行恢复需绑定实际证据。v0.5 36 项对照继续适用。

用户确认先取消 dp-route 的常规模型调用，再对 dp-w-type 和 dp-sign-key 使用本地证据优先的调用策略。已记入[计划](plan.md)。DP 定义和 v0.5 四段验收继续按原合同，阶段保持 SPEC。

用户确认细化 dp-auto 的卡点后路径选择，已交[独立设计草案](dp-auto-stalled-path-design.md)和 Gaze、continuity 两份四段附录。重建时先核原时点权限和期限，合成进入正例的额度与条件单独标明。现有 DP 合同及 v0.5 验收继续适用，项目实现与模型验证留待后续指令。

文档自查通过：12 处链接，两个范本各为一题两候选、同版反解。Gaze 最长路径连同模型和报告占合成额度 1110/1200 秒，continuity 为 130/180 秒。实际请求、原始回包、执行结果均为空。v0.5 的 36 项验收与 spec 指纹一致。

2026-11-22 按可独立交付结果拆分。[mw-dp-call-policy](../mw-dp-call-policy/codex_doc.md) 负责 route 常规本地路由、w-type 明确类型本地采用和 sign-key 独审证据优先。原 key 保持完整材料链、18 条 AC、36 项 v0.5 验收及两份 dp-auto 补充范本。共享入口按新 key 先交策略、原 key 后接续的顺序写入。当前两组均在规划阶段。

补齐[八个 DP 同次对账](decision-chain-reconciliation.md)。T08 在原 36 行中逐项关联决策本、调用、返回和原主体接回/回执，T09 从回执反查。每 DP 按既有角色及具名 writer 核验。历史范本与当前运行各自保留来源。当前未达到运行时 8/8，等待实施与复核。

## 2026-11-22 实施进度

[调用策略 key](../mw-dp-call-policy/achieved.md) 已按四条 AC 验收结案。本 key 已认领并进入 EXECUTE。首批实现包括八 DP 发送时去除重复准备目录、保持引用正文和冻结反解；QG 预检要求 pass/fix/reopen 三组条件，本地仍按实际选择核业务前提。[QG 同次离线回放](evidence/implementation/qg-short-chain-20261122/report.md) 保存实际请求、替身原始返回和真实 PM 接回 writer 记录。该回放的执行状态为未执行。

auto 已实现候选 2～5 个和正文完全重复检查，保留自由 ID。更细的路径比较、偏好/反转条件及预算结论归入 T04/T05。八 DP 的离线请求与回包均按 `call_id + attempt_index` 核对并验证反解，[传输原件](evidence/implementation/qg-short-chain-20261122/all-dp-wire.jsonl) 共 24 条。当前只有 QG 的此回放带同次 PM 接回回执。其它固定候选覆盖、完整材料字段与术语、准备宿主流程、正式质量产物和 36 项验收仍按原计划推进。

## 2026-11-22 QG 正式产物与同次验收

隔离 QG 由 `fixB` 接回，实际补了排序断言和锚点。独立 reviewer 运行正常断言并用故意排序的变异做负测，逐 AC、VC 和流程核对修后文件摘要。L3 正式 writer 产出质量门禁报告及本地证据签收，原决定下记录实际修复和结算，重放返回同一事件。隔离 key 停在 VERIFY。证据见 [QG 本次 manifest](evidence/acceptance/runs/dp-QG/manifest.json) 和 [正式 QG 报告](evidence/acceptance/runs/dp-QG/quality-gate-report.md)。

CLI 回执现在必须由合法当前主体绑定到已接受的原请求，并拒绝跨 key、任务、决定、选项及阶段借用。默认 PM gate 客户端携带同次 ID 记录请求和回包，实测由正常 gate writer 落限定效果。8 个 DP、9 个隔离运行已采到同次回执。steer 参考方向留在待预算核对，sign 模型见证为 continue，gate 使用独立的已绑定局部效果场景。

[v0.5 逐项报告](evidence/acceptance/v05-four-stage-comparison.md)覆盖两个 cohort 的全部 36 行。历史原件、原始请求/返回及同版反解回放 36/36。当前对照 19 项失败、17 项未验证，主要缺口为 `desc`、术语/AC/VC 定义闭包、结构化原因、完整 prepare 合同以及按对应 v0.5 事项做 PM 语义对照。旧 QG 缺 `reopen` 在发送前拒绝；旧 auto 的当前复现输入仍发送，PM 接回后返回 rework，故本项不通过。保留 EXECUTE，独立 QG 复核不能代替全量 T09 验收。

## 2026-11-22 材料修复与 36 项复跑

旧 dp-auto 缺有来源的取舍、每条路径的硬上限和停止/条件后继，直接在输入校验退回。隔离 CLI 原例收到 `input-incomplete`，请求和返回均为空，保存正式阻塞记录。优化版隔离样例沿用 v0.5 的当前响应优先和原额度，反解先重试，原主体记录待复核权限及余量后再行动。该样例没有执行重试或读健康快照。

八个 DP 共用经过白名单的 `desc` 和术语投影。PM/Worker 工具支持写入本次目标、偏差、事件和证据，旧生产者暂从专属业务事实生成有限简述。输入校验最多十句及 1000 估算 tokens，目标模型精确计量仍为 `null`。QG/sign 取当前 key 的 spec/design 文本，带出引用正文、VC 对应 AC 和已提供的核验状态。简述与核验状态里的文件引用复用授权读取和压缩。QG `fixB` 从本次冻结配对反解 F1/F2，独立执行复核并走原 writer，模型签收隔离样例同次返回结构化遗留项。

[上轮逐项基线](evidence/acceptance/v05-before-material-rework.json)和[材料修复对账](evidence/acceptance/v05-before-lineage-rework.md)均保存。上轮 19 失败、17 待证。本轮 3 项符合历史旧 auto 的拒绝预期，1 项记录有依据的 QG 反解差异，16 项仍失败，16 项待证。失败集中在完整本地字段追溯及配对表、通用引用及枚举含义，待证集中在各原例的返回和原主体裁定。独立 review 的本轮 QG 文件见 [正式报告](evidence/acceptance/runs-material-rework/dp-QG/quality-gate-report.md)，完整 T09 仍待验证。使用本地替身完成八次发送，保留原记录中的历史 Jev 回包。阶段保持 EXECUTE。

## 2026-11-22 字段来源和原例回放复核

同次本地快照保存正文投影的字段来源、变换、实际发送落点和完整候选配对。发送和反解使用同一张冻结配对表。具名引用可携带正文或由宿主按授权文件和行段解析出正文，后者通过 `source_id` 指向本次实际发送的文本。调用前校验选择器归属，解析失败和已具名引用被外部选择器重绑都退回材料。业务选项解释来自当前规则或候选正文，其余业务枚举可以由准备者定义。

以 [上轮 36 项](evidence/acceptance/v05-before-lineage-rework.md) 为对账基线。当前原例回放 36/36。上轮 16 项失败已补齐，16 项待证中核对完成 15 项。当前 32 项为有依据的差异、3 项符合预期拒绝、1 项待证。旧 auto 的原主体接回缺历史回执，保留当前宿主拒绝、本轮 PM 裁定与原参考为独立证据。各案例的 [请求、返回和同次裁定](evidence/acceptance/v05-four-stage-comparison.md) 分段保存。原例 QG 和 gate 的准备、接回不借用补充隔离案例的修复或执行回执。补充案例分别验证了真实 QG writer 与限定 gate writer 的隔离效果。

本轮回包来自离线替身，历史 Jev 回包及其使用量、置信度和概率留在各自原请求下。Jev 精确 token 计量仍为未知。完整 T09 独立验收未完成，阶段保持 EXECUTE。

## 2026-11-22 T09 独立复核与正常入口

Codex 协作执行者 `/root/t09_reviewer` 与 T08 实现者分开复核，逐条核了 [32 项差异与其余四行](evidence/review/t09-v05-row-review.json)。真实扩展的 PM/Worker 工具启动实际 mw.py 子进程，决策传输用本机 HTTP 替身，原业务材料仍来自范本。七个带准备材料的案例走完请求投影、同次配对反解和相应回执，六个工具自动写入 `consumed`，sign 写入零签收的 `continue` 交接。单纯提供业务材料的 PM/Worker 入口均退回缺 `preparation`。五个 PM 正常显式接回均由注册 `decision_receipt` 写入对应决定的 `settled=pending`。 [正常入口核对](evidence/review/normal-entry/verified-entry-summary.json)

同一 Worker 原输入的文件行号引用可入模，但执行侧按字面文件名打开失败。调整后的受限 Worker 以既有授权的 inline 材料和可执行文件路径完成一次实际读取，框架自动记录调查的 `executed` 和 `settled`，随后用新事实另作 `continue` 判断。正常 PM gate 无匹配待处理门，本地只返回路由。旧 auto 的历史原主体接回和当前 gate 的正常入口裁定仍待证。 [独立复核报告](evidence/review/final-review.md)

独审复现单候选 w-type 仍发送、未释义材料缩写仍入模、3600 秒无限循环 auto 路径仍发送。完整 AC/VC 和正式 MW 独审运行身份仍有缺口。当前决策本、模型输入、回包和裁定的 [36 行对账](evidence/acceptance/v05-four-stage-comparison.md) 保留已核证据及其边界。T09 门禁未通过，保留 EXECUTE。

## 2026-11-22 T09 缺陷修复和复跑

固定 DP 的候选以注册表为准，发送及预览前要求完整配对。`dp-auto` 校验原约束余量、结构化耗时上限和后继图，拒绝超额、抬高原余量及循环。随请求发送的缩写需有解释，授权文件正文在解析后同样核对术语。Worker 在现有读范围内解析 `file:line[-line]`，实际读取指定行后根据同一次工具结果写调查回执。

真实 PM/Worker 工具和 CLI 使用隔离模型替身复跑，保存实际请求、同次配对、回包和回执。固定候选缺失、正文未释义缩写、超预算、抬高预算及循环反例在发送前拒绝。调查读到指定行，同一决定记录 `consumed`、`executed` 和 `settled`。Gate 原例的隔离 PM 正式 CLI 获得 `approve` 并写入同次 `consumed` 和 `settled=pending`。本项目当前没有匹配的待执行保护门。 [正常入口摘要](evidence/review/normal-entry/verified-fixed-entry-summary.json)

Python 定向回归 487 项通过，材料回归 25 项通过。隔离源码副本的 `npm run check` 通过。两组定向 TypeScript 套件 75 项通过，既有 `terminate` 用例未通过，运行终结后回执写入仍待处理，原 v0.5 调查正常回执可独立复验。旧 `dp-auto` 历史回执缺失继续待证。 [独立反例复核](evidence/review/t09-independent-rework/index.md)

正式定向独审 `cx-22fe10fe7b7ba132c4f0` 已交付，任务队列和本次运行均为 `done`。独审复算正常入口与证据摘要并独立重跑 25 项材料用例。原全包独审第一次运行超时，其重启记录另存。以本次定向报告收录进 36 行对账。对账统计为 32 项差异有据、3 项符合预期拒绝、0 项失败、1 项历史待证。18 组 AC/VC 中 8 组通过、9 组待证、1 组未通过，正式验收器退出 2，材料 key 保持 EXECUTE。 [正式独审报告](evidence/review/t09-focused-mw-review.md) · [最终四段对账](evidence/acceptance/v05-four-stage-comparison.md) · [验收记录](evidence/codex-pm/cx-22fe10fe7b7ba132c4f0/1795345076196623500-i4on69u2/result.json)

## 2026-11-22 旧 dp-auto 的当前 PM 接回

用户确认旧历史回执保持 `null`，AC-017 第四段采用当前 PM 正常入口复跑同一负例的接回。隔离 PM 会话通过实际 `ask_decision` 和 `mw.py` 得到 `input-incomplete`。同一会话的 PM 回复关联真实阻塞事件和当前角色身份，记录退回理由、补齐优先级和有界路径的下一步及原授权和额度。模型调用为零，未执行重试或读取健康快照。 [当前 PM 接回](evidence/review/normal-entry/dp-auto-original-pm-handoff/pm-handoff.json)

更新 AC-017、VC-017 与四段合同，旧案第四段为 `expected-rejection`。当前对账为 32 项差异有据、4 项预期拒绝、0 项失败、0 项待证。前次正式独审保留当时的结论，新增证据由当前 PM 核验。总验收仍有其他缺口，保留 EXECUTE。 [36 项对账](evidence/acceptance/v05-four-stage-comparison.md)

独立复核已签收 AC-017 / VC-017。签收绑定现行 spec 和 36 项比较摘要。历史回执继续保存为空。AC-014 保持待完成。 [独立复核](evidence/review/ac017-current-pm-independent.md) · [签收索引](evidence/acceptance/evidence-index.json)

## 2026-11-22 PM 与 Worker 异常复跑

在 AC-017 签收后验证并发、未知传输、取消、服务和 Worker 超时、Worker terminate。已修同一认领重建 PM 时的事项去重、已发送而未获完整回包时的重发与诊断、已批准 terminate 的终态回执。取消及 Worker 到期补齐正常入口证据。修后仍由同一负例验证旧 dp-auto 零发送，已有签收快照保留。当前范围未绑定跨认领转移，AC-014 保持待完成。 [原因、修复和复验](evidence/review/continuity-normal-entry-report.md)

## 2026-11-22 AC-014 补验与跨认领接回

使用正式认领入口在同一隔离 key 切换两名 PM。修复事项摘要被认领 ID 改变的问题，原决定已返回与传输结果未知两种场景均首次发一次，接手 PM 零重发并读回原决定或原阻塞。同版接回已有证据，旧版逻辑 ID 的迁移未验证。

修复 auto 的缺偏好和等价路径拒绝、QG 无独审误接受，以及 sign 借旧全量独审覆盖较新 QG 或在审查证据漂移后仍有效的问题。Monitor 用实际 HTTP 从八个 DP 各读回一对原始请求与响应，全部双 SHA 一致。精确计量仅完成现有降级验收。T04 已有派发角色可复用，宿主顺序约束、凭证隔离和同版发布/吸收尚缺实现。QG/sign 尚需固化同对象、适用范围和版本的来源绑定及模型投影。 [本轮补验](evidence/review/ac014-followup.md) · [独立复核](evidence/review/ac014-followup-independent.md)

AC-014 保持开放，key 保持 EXECUTE。AC-017 原限定验收照旧引用，旧 dp-auto 历史 PM 回执保留为空。

## 2026-11-22 受限准备与正式 QG 输入

复用现有 `decide_prepare`，增加卡片显式选择的受限运行。从原事项预算实际预留固定子额度，验证 Worker 顺序、来源句柄、指定模型和同一 revision 的原子发布。正常 PM 对同版材料记录语义确认后吸收。越序、越界、错版、来源变化和三步耗尽有同次拒绝记录。

sign 实际请求带宿主核定的 QG 对象、当前完整范围、版本、发布和独审摘要。整 key 通过写出同次签收，局部旧引用、过期、错对象和在途变更退出拒绝。独审复现较新正式失败被旧通过覆盖；修后实际请求使用最新独审的 fail/not-run 和未闭项，宿主仍拒绝模型的 finalize。Jev 精确计量边界待证。 [正常入口及实际 payload](evidence/review/ac014-bounded-prepare-sign.md) · [独立复核](evidence/review/ac014-bounded-prepare-sign-independent.md)

独审再验证 `dp-w-check-task`。批准行号由受限 Worker 捕获正文并进入同版资料，实际原 Worker 吸收、决策、读取、回执和重评成功。已修委托子额度放宽原 Worker 字节及调用上限的问题，两个入口都扣同一实际运行的累计额度。当前切片独审结果单独记录，AC-014 及 key 继续开放。

## 2026-11-22 Jev 计量实测与剩余缺口

已实测 `timi/jev-latest` 单选与同网关 `messages/count_tokens`。真实计量返回 1000 和 1001 的两个合成样本在当前 PM 正常入口均发出一次回环决策请求，估算分别为 504 和 505。精确计量尚未接入，计量接口与 Decisions 的 desc 分词口径待确认。正式验收索引存在 9 项源码摘要过期，本 key 正式合同尚未覆盖当前 18 条 AC 的解析。AC-014 继续开放。 [请求、回包、正常入口与缺口](evidence/review/ac014-remaining-and-jev.md)

## 2026-11-22 同批正式合同、QG 及 T08/T09

将原验收条款改为正式冻结入口可读的形式，保留 18 条 AC 原文和旧 AC-017 签收快照。轻量 PM 派发桥新增只读 review 卡支持，继续使用同一 key 认领和 Worker 权限检查。正式冻结覆盖 18 AC、18 VC、3 FLOW。真实终态独审用于发布，QG 以 `verified/fix` 进入本 key 的正式证据签收。签收返回 `continue/refused`，无正式签收落盘。key 进入 VERIFY。

Timi 未确认目标模型计量合同，精确值留空并保留 AC-003 待证。T08 源码绑定更新为本批 24 项，36 行为 32 项差异有据、4 项预期拒绝。T09 独立判断 15 组通过、1 组待证、2 组未通过，其中 AC-005 的 `dp-w-type` 悬空 `AC-999` 反例已用正常入口实测；AC-014 等待缺口闭合。 [同批对账与正式回执](evidence/acceptance/final-batch/summary.md) · [独立复核](evidence/review/ac014-final-independent.md)

## AC-005 引用修正

按用户指令在当前 `VERIFY` 中修复已检出的 AC-005 实现缺陷。复用同一 key 和冻结合同。写面为模型材料投影、文件水合后的发送前校验及相关定向测试。PM 和 Worker 复跑使用本 key 的原始生效合同及隔离传输。AC-003 保留待证。

2026-11-23，八个 DP 的共同校验通过定向验证，PM 和 Worker 正常入口各得到 1 次合法回环发送与 5 次明确拒绝零发送。当前同源 36 项为 32 项差异有据和 4 项预期拒绝。T09 独审认定 AC-005 已满足，16/18 组满足，AC-003 待证，AC-014 验收器退出 2。 [本批复跑和原始回放](evidence/acceptance/ac005-rework/summary.md) · [独立复核](evidence/review/ac005-t09-independent.md)

## AC-005 正式签收复跑

复用本次 T09，通过同一 VERIFY 认领补发只读 review 取回终态报告。轻量派发桥的调整仅涉及 VERIFY 的只读复核，实施任务仍走 EXECUTE。验收口径沿用冻结合同。

2026-11-23，终态复核 `cx-941e0bccfcf2620b5537` 已绑定正式 QG。AC-005 和 VC-005 均为 `met` 并移出未关闭清单，正式 sign 回执为 `continue/refused`，首个未满足条件是 AC-003。

AC-003 复验了正常 PM/Worker 各一条 10 句放行和一条 11 句零发送。精确字段为 `null`。需要 Timi 对 Decisions 的 `desc` 计量合同，以完成 1000 放行、1001 零发送的边界。当前保持 VERIFY。 [正式 QG、sign 和 AC-003 回放](evidence/acceptance/ac005-official/summary.md)

2026-11-23 复查 Timi 实际计量能力。单文本分词入口返回 404，模型查询未给出部署或分词器版本，兼容消息接口仅有整条输入计数。AC-003 保留待证。下一步依赖 Timi 提供同一 Decisions 部署的 `desc` 分项计量合同或同版本 tokenizer 与输入处理规则。 [复查证据](evidence/acceptance/ac005-official/summary.md#timi-计量能力复查)

## AC-003 本地预算改约

按用户授权在当前 VERIFY 认领下修订 AC-003/VC-003，采用原本地计量公式作为固定预算。写面限本地预算检查、合同及定向证据，在当前源码用 PM 与 Worker 正常入口验证后重跑 T08/T09 和正式 QG、sign。

2026-11-23，PM 与 Worker 正常入口均通过 1000 单位和 10 句正例，1001 单位与 11 句均零发送。T08 的 170 项通过，1 项跳过，36 项对账为 32 项差异有据、4 项符合预期拒绝。终态独审确认 18 组 AC/VC 和 3 条流程。正式 QG 为 `verified/pass`，未关闭清单为空。正式签收为 `finalize/written`，回读有效。当前 key 为 VERIFY。 [验证、QG 与正式签收](evidence/acceptance/ac003-local-budget/summary.md)

## 结案入口

保留已签收的 `achieved.md` 和 QG 原文。轻量 Done 验证当前独审签收和全部 AC 的同源回执，再从本节后的遗留记录核对已终止的旧 Worker。签收、对账和历史运行均继续可回查。

## 结案遗留

- `cx-22fe10fe7b7ba132c4f0` 是早期独审试跑，结构验收退出 2。由本次 T09 终态复核和正式全范围签收取代。
- `cx-36563aec5d5bb935138d` 是旧合同的 QG 复核。其整 key 拒签记录留作历史，本次 QG 已完成所有原未关闭项。
- `cx-57f6f31b9aa3daa065db` 队列为 `done`，原 trace 有退出 0 记录，PID 已结束。旧 `run.json` 仍显示 `running`，该快照仅作历史，验收使用本次独审终态。
- `cx-941e0bccfcf2620b5537` 是 AC-005 修正后的阶段性复核，后继全范围报告重核该项并保留既有证据。
- `cx-9f69d2ccd84be23e990a` 是早期正式合同读回，后继复核完成证据绑定并取代其签收候选。
- `cx-ee474fbc353feb7aba95` 是本次签收绑定的独审终态。Done 适配使原验收命令的全仓指纹过期，结案检查重新核对同一终态、原始 QG 和 sign 回执，并记录当前源码上全部 AC 的通过结果。
- 旧 dp-auto 的历史 PM 回执仍为空。本轮 PM 同次拒绝与接回已通过 AC-017。

## 正式结案

2026-11-23，经 `codex_pm.py done` 结案，权威状态 `DONE / idle`，ClaimId 清空。原 QG、sign 和 v0.5 36 项均核对可回查。 [结案与发布回查](evidence/acceptance/closure/summary.md)
