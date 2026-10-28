# RQ10 毕业考：八DP职责、命名与旧集合冲突（只读对账，非验收）

范围：RQ10 卡。只读本 key 文档与 goal；无源码/registry/配置/服务/凭证操作，无测试/build，无额外 ask_decision；结论不声称 SPEC/AC/QG/实现验收通过。

## 结论

- 事实：六个保留职责与两个新增入口的目标名称已全部确认，共 8 个目标名（spec.md:66-67；pm-state.md:72、:74）。发起主体/判断对象/已确认业务选项可按最新确认给表（见证据 A），但**"八DP"在名称上已换成分**：旧八项含 dp7-gate-failure、dp20-stage-close（spec.md:21，key-decision.md:6），最新八项目标为 dp-w-type/dp-pm-steer/dp-w-check-task/dp-QG/dp-gate-approve/dp-sign-key/dp-auto/dp-route（spec.md:66-67）。数目相同、组成不同，是本轮最易误读的点。
- 事实：§1.1 旧保留集合与"退役其余 17DP"（spec.md:21-22）已被标注为待重审旧基准（spec.md:6、:125），但 AC-001/002/003 仍直接引用 §1.1 的"8 项/17 项"（spec.md:84-86），因此该三 AC 目前指向失效基准，无法据以判定；按新集合推算，被退役的**旧 ID**为 19 项（旧 25 − 保留 6，含 dp7、dp20），dp-auto/dp-route 为新增、无旧条目。此推算为本次算术推导，未获批准，不据此改任何文件。
- 事实：其他已识别的旧口径冲突集中在 §1.5 的过期待定语（spec.md:65）、旧 17 计数复用（spec.md:74）、AC-011 去重范围未覆盖新入口（spec.md:94）、以及三份历史文档中的二选项 dp15、动态 dp3、dp15/dp20 旧归属（autopilot-requirements-clarification.md:35、:66、:68、:76；spec-gate-authority-20261024.md:46、:48、:65）。逐条替换建议见证据 B，均未执行。
- 推演（非验收）：路由→业务→执行三段可分；固定节点直调不要求先路由；角色资格与复合问题拆分存在明确缺口（证据 C/D）。不可默认放行：路由不可用同样是阻塞，不得回落成"直接调固定 DP"或"视为已批准"（spec.md:60；AC-012 spec.md:95；decision-tool.ts:1137 现有 unavailableDirective，经 pm-question-action-context-review.md 复用）。
- 残留：目标集合口径、退役名单/数量、dp-route 的发起角色与失败后行为、dp-QG/dp-gate-approve/dp-sign-key 的明文发起角色、dp-w-type 与 rag-research 等框架类型映射、H01 stage 启动判断的 DP 归属、复合问题拆分主体与顺序、steer/need_fix 后重送是否同证据版本，均**待确认**（证据 D）。本报告不替这些定答案。

## 证据

### A. 八目标入口职责表（事实 + 已确认出处）

| # | 目标名（确认） | 旧 ID/旧名（仅迁移对照） | 发起/材料准备主体 | 判断对象 | 已确认业务选项 | 不替代关系 | 出处 |
|---|---|---|---|---|---|---|---|
| 1 | dp-w-type | dp1-dispatch-type | PM | 本次任务派发类型 | coding/research/review/vision（vision 须满足图像能力门禁） | 不扩大角色权限/写面；不移除 rag-research、decide_prepare 等框架现有类型；不等同 dp-pm-steer 编排 | spec.md:26、:7；pm-state.md:78 |
| 2 | dp-pm-steer | dp2-checkpoint-split | PM | PM 下一步任务编排 | narrow/split/direct-exec/escalate（ID 不改） | narrow 不改目标/验收；不要求 Worker 等待 PM；不替代 Worker 侧可达性判断 | spec.md:27；dp2-pm-convergence-definition.md |
| 3 | dp-w-check-task | dp3-worker-clarify | Worker | 当前事实/权限/预算下本任务是否可达及继续方式 | 继续任务／终止并输出结论／继续并补充证据 | fire-and-forget；"上报 PM 等指示"不是选项；终止≠目标完成或 key 收窄；不替代 PM 编排 | spec.md:28；dp3-worker-initiated-discussion.md 最新确认节 |
| 4 | dp-QG | dp6-qg-verdict | PM 提交审核材料 | 本次正式质量审核结论 | pass/fix/reopen | 不派返工、不替代 dp-sign-key 签收与 dp-gate-approve 审批；机器通过≠正式通过；reopen 不授改目标/验收 | spec.md:29；AC-005 spec.md:88 |
| 5 | dp-gate-approve | dp15-autopilot-gate（并承接 dp20-stage-close） | PM（送审前预拟 note） | 本次 gate 是否满足条件及按何动作继续/收尾 | approve/steer/need_fix/reject | steer→PM 发起 dp-pm-steer，need_fix→PM 发起 dp-auto；均不视为放行或已整改；不替代 dp-QG/dp-sign-key；approve 不批准下一 stage | spec.md:31；gate-four-option-confirmation.md；h02-stage-close-confirmation.md |
| 6 | dp-sign-key | dp25-signoff-conclusion | PM（交付结论） | 该 key 交付是否可签收 | finalize/continue/user-confirm | 同次判断写签收、无第二次 PM 批准；签收≠phase done/stage 关闭；QG 通过不自动签收 | spec.md:25；h13-signoff-gate-link-confirmation.md |
| 7 | dp-auto | 新增（原称 dpcommon/dp0）；承接原 dp7 处置 | PM | 现场问题从 PM 已准备候选中选一项 | 动态候选（PM 按现场准备，非固定菜单） | 仅从已准备候选选择，不临时造新方案；选择≠执行；不替代固定 DP、不降目标、不豁免硬门；材料非法/不可用/无有效选择属阻塞非业务结果 | spec.md:59-60；AC-009 spec.md:92；autopilot-requirements-clarification.md:57 |
| 8 | dp-route | 新增 | PM（临时问题） | 本次问题用哪个入口（6 固定 + dp-auto 共 7 个目标） | 选择入口（七入口） | 只选入口，不替所选 DP 做业务判断、不执行；不改变角色资格；路由成功≠业务决策成功/已执行 | spec.md:62-63；pm-state.md:74 |

补充事实：目标名不再用 dp+编号，也不默认保留编号可调用别名（spec.md:66）；dp-w-type 取代前一条 dp-worker-type，dp-QG 大小写保留（spec.md:7、pm-state.md:72）。目标名已确认不等于运行注册/schema/迁移完成（spec.md:66）。

### B. 新旧冲突清单（位置 / 性质 / 建议替换含义 / 已确认出处）

| # | 位置 | 性质 | 建议替换含义（未执行） | 已确认出处 |
|---|---|---|---|---|
| B1 | spec.md:21（§1.1 旧保留 8 项，含 dp7、dp20 与旧职责名） | 历史原文，但因 AC-001 引用而被**误作当前合同** | 保留为历史；当前目标集合另立"6 保留 + 2 新增"，dp7/dp20 不在保留集 | spec.md:43、:45、:67 |
| B2 | spec.md:22（"退役其余 17DP"+名单） | 数目/名单基于旧八项，**误作当前合同**（AC-002/003 引用） | 按新集合重算退役**旧 ID** 名单（推算 19 项，含 dp7、dp20），并说明 dp-auto/dp-route 为新增无旧条目；须先确认再生效 | spec.md:43、:45、:67 |
| B3 | spec.md:84 AC-001（"精确等于§1.1的8项，退役17项"） | 引用失效基准 → 不可判定 | 指向新的目标集合条目，并显式含 dp-auto/dp-route | 同上 |
| B4 | spec.md:85-86 AC-002/AC-003（退役 17 项口径） | 集合口径失效 | 随 B2 更新；保留"拒绝调用、历史只读"语义 | 同 B2 |
| B5 | spec.md:74（"不把 17DP 隐性重新装入 dp15"）与 spec.md:6（"退役 17 项旧基准"） | 旧计数复用语，数与组成均已变 | 改为"退役集合"表述，避免与新计数并存 | spec.md:43、:45 |
| B6 | spec.md:65（"是否设数字别名…固定集合待讨论"） | 过期待定语 | 别名问题已由 spec.md:66 回答（不用编号、不默认别名、历史编号原样保留）；"固定集合"已由 :67 汇总 | spec.md:66-67；pm-state.md:74 |
| B7 | spec.md:94 AC-011（"四门及 dp2/dp25"为去重范围） | 范围未覆盖新入口 | 去重职责应覆盖 dp-auto/dp-route 与 dp-w-check-task，或显式说明为何不含 | spec.md:63、:67 |
| B8 | key-decision.md:6-7、:11（旧 8/17 + "dp1/dp2/dp3/dp25 现有业务设计不改"） | 需求记录历史原文；:11 已被 dp1 加 vision、dp2 语义精化、dp3 三固定选项替代 | 加"已被 RQ 修订"指针，不改原文；不得据 :11 反对已确认变更 | spec.md:25-28；pm-state.md:70、:78、:82 |
| B9 | autopilot-requirements-clarification.md:66、:68（dp15 二选项 approve/reject） | 仅历史原文 | 只作历史；dp-gate-approve 现为四选项 | gate-four-option-confirmation.md:9；spec.md:31；AC-007 spec.md:90 |
| B10 | autopilot-requirements-clarification.md:76（dp20→dp15 "选择 approve/reject"） | 合并结论有效，选项措辞历史 | 合并结论保留；选项按四选项表述 | 同 B9；h02 |
| B11 | autopilot-requirements-clarification.md:35（dp3 2～5 动态候选为"现有材料合同"）、pm-state.md:83 | 仅历史原文 | dp3 目标合同为三固定业务结果；动态候选/2～5 不再适用 | spec.md:28；AC-004 spec.md:87 |
| B12 | autopilot-requirements-clarification.md:27（"是否使用数字别名…未冻结"） | 仅历史原文（当时未确认） | 已由 spec.md:66 取代 | spec.md:66 |
| B13 | pm-state.md:33（"名称/编号仍待定"） | 仅历史日志行（带日期） | 不作当前状态；当前见 pm-state.md:72、:74 | pm-state.md:72、:74 |
| B14 | spec-gate-authority-20261024.md:46、:48、:65（"dp20 唯一 owner""dp7 只做失败处置""dp15 不重复裁决"） | 历史研究原文；其**职责归属结论**已被 dp7→dp-auto、dp20→dp15 替代，其**源码现状事实**仍属当时静态观察 | 职责结论只作历史；不得用来反对合并，也不得当作"源码已迁移/未迁移"的当前验收 | spec.md:43、:45、:132 |
| B15 | spec.md:91 AC-008（"gate 自动处理所需启用条件或授权"） | stage-only 时代的措辞，未体现四选项 | 重述为四选项下的自动放行边界（approve 不放行未授权副作用） | gate-four-option-confirmation.md:9、:36 |
| B16 | spec.md:130、:132（dp15 六类 gate、dp7 当前仅原因分类） | 事实性描述，与合并结论不冲突 | 保留但明示"源码未迁移"，避免被读成目标职责 | spec.md:43、:132 |

未在此列：dp15 旧名 autopilot-gate、dp3 旧名 worker-clarify、dp2 旧名 checkpoint-split 的名称与职责落差，已由上表 A 的"旧名仅迁移对照"覆盖，不另立冲突行。

### C. 静态场景推演（推演，未运行、未验收）

1) 临时问题路由
- 推演链：PM 遇到非固定节点问题 → 整理"决策主体/判断对象/具体待决问题" → dp-route 选入口 → 按所选入口的合同决策（固定 DP 用其材料/选项；dp-auto 用 PM 准备的候选）→ PM 在既有权限内执行 → 执行/结算分别记录。
- 结论：两段判断必须分开留痕；route 结果不能当业务结论，也不能当已执行（spec.md:62-63、:60）。
- 缺口：route 自身是否产生独立决策记录/回执、其不可用时的处置（是否允许改走固定直调），未确认（spec.md:65 明示决策本格式待定；AC-012 只要求阻塞）。

2) 固定节点直调
- 推演链：任务派发→dp-w-type；PM 阶段收敛→dp-pm-steer；Worker 执行中自检→dp-w-check-task；正式审核→dp-QG；gate 节点→dp-gate-approve；key 交付→dp-sign-key。均不经 dp-route。
- 结论：固定节点直调不强制先路由，与路由路径并存（spec.md:61）。
- 缺口：同一事项既在固定节点触发、又被 PM 作为临时问题送入 dp-route 时，如何避免对同一对象+证据版本二次审批，只有 AC-011 的原则要求，没有识别/拦截机制（spec.md:94）。

3) 角色资格
- 推演链：dp-w-type/dp-pm-steer/dp-gate-approve/dp-sign-key/dp-auto/dp-route 由 PM 发起；dp-w-check-task 由 Worker 发起。route 不得让 PM 冒充 Worker、也不得让 Worker 调 PM 专属 DP（spec.md:63）。
- 静态对照：现有源码事实只有 dp2/dp25 为 PM-only 集合，dp3 不属 PM-only（dp3-worker-initiated-discussion.md 引用 decision-tool.ts:214；沿用既有证据，未新审源码）。因此"dp-QG/dp-gate-approve/dp-w-type 的发起角色"在目标态没有明文矩阵，dp-route 的 Worker 侧用法也无定义。
- 结论：目标角色资格目前只有 dp2/dp25/dp3 的旧静态事实与 dp-route 的原则句支撑，不足以成为可判定合同。

4) 复合问题拆分
- 推演链（例）：一次交付同时涉及质量未过、key 未签收、stage 待关闭 → 拆成 dp-QG（结论）→ dp-sign-key（finalize 才签收）→ dp-gate-approve（stage 关闭）；证据可复用但不跨 DP 冒充结论（spec.md:29、:25、:31；AC-011）。
- 另一例：dp-gate-approve 选 steer/need_fix → PM 分别发起 dp-pm-steer/dp-auto → 之后再回到同一 gate。
- 结论：拆分后每个子问题只有一个 owner；顺序影响证据版本；重送同一 gate 是否算"同证据版本不重复审批"取决于中间动作是否产生新证据，未定义（spec.md:77、:94；AC-007）。
- 缺口：拆分的批准主体、拆分顺序与"拆分集合"的落盘方式未定（spec.md:63 仅要求"多个独立判断先拆清楚"）。

5) 服务不可用
- 推演：任一 DP（含 dp-route）UNAVAILABLE → 保持阻塞、记录原因、不得默认批准或改用另一入口冒充。既有工具契约 decision-tool.ts:1137 unavailableDirective 已是"停止门控动作、禁止猜/绕过、报告 blocked 并等人工"（经 pm-question-action-context-review.md 复用，非本轮新审）。
- 缺口：blocked 状态在决策本中的表达、以及"暂不推进该 stage"与"改走固定直调"的边界未确认。

### D. 缺口清单（待确认，本 RQ 不定答案）

| # | 缺口 | 现有依据 | 为什么不能自行定 |
|---|---|---|---|
| D1 | 目标集合口径（"八"=旧八还是 6+2）与退役名单/数量（17 vs 推算 19） | spec.md:21-22、:67 | 属业务/范围取舍，且涉及删除授权 |
| D2 | dp-route 的发起角色（Worker 可否）、是否独立决策记录、失败后是否允许固定直调 | spec.md:62-63、:65；AC-012 | 新权限/schema |
| D3 | dp-QG/dp-gate-approve/dp-sign-key/dp-auto 的明文发起角色与拒绝语义 | spec.md:63；dp3 证据中的 PM-only 现状 | 角色资格变更 |
| D4 | dp-w-type 候选与 rag-research/decide_prepare 等保留框架类型的映射（保留类型≠可被 dp-w-type 表达） | spec.md:26；pm-state.md:78 | 派发类型语义 |
| D5 | H01 stage 启动判断归哪个 DP（旧 dp15 为 stage-only，现 dp-gate-approve 为通用 gate 审批） | AC-015～019（spec.md:98-102）；spec.md:130 | 职责归属 |
| D6 | 复合问题拆分主体/顺序/记录，及 AC-011 去重范围是否含 dp-auto/dp-route | spec.md:63、:94 | 流程与 schema |
| D7 | steer/need_fix 后重送同一 gate 是否同证据版本（是否二次审批） | AC-011；AC-007 | 幂等判据 |
| D8 | 迁移期间保留 6 项旧 ID 是否仍可调用（"无别名"与"历史编号保留"的运行含义） | spec.md:66；AC-002 | 运行拒绝策略 |

## 残留与未验证

- 全部为纸面/文档对账：无源码审计、无 registry/活配置/ledger/凭证读取，无测试/build/install/commit、无服务操作、无额外 ask_decision 或 provider 探针；不构成 SPEC/AC/联合设计/QG/签收/实现验收。
- 只做了 5 个场景的静态推演，未枚举全部 H01～H13 组合，也未构造反例矩阵（RQ11 职责范围）。
- AC 机械可判定性未评（RQ12 职责范围）；本报告只指出 AC-001～003、AC-008、AC-011 与最新职责的引用/范围落差。
- 未验证：dp-auto/dp-route 在当前运行实例是否存在、保留 DP 的旧 ID 是否仍可被调用、工具 schema/CLI/提示词现状——均按任务边界不做运行核验。
- 未做：任何文件替换、删除建议的落地、退役名单确认；证据 B 的"建议替换含义"只是措辞建议，未获批准。
- 未覆盖文档：pm-state.md 仅按关键词定位读取（未全文）；h03/h04～h12 各确认文件与 RQ7/8/9 研究证据未全部全文读；源码未新审。

## 上下文来源

全文读：
- `.agenticdoc/mw-dp-consolidation/spec.md`（140 行，含 §0～§5）
- `.agenticdoc/mw-dp-consolidation/evidence/autopilot-requirements-clarification.md`
- `.agenticdoc/mw-dp-consolidation/evidence/pm-question-action-context-review.md`
- `.agenticdoc/mw-dp-consolidation/evidence/dp2-pm-convergence-definition.md`
- `.agenticdoc/mw-dp-consolidation/evidence/dp3-worker-initiated-discussion.md`
- `.agenticdoc/mw-dp-consolidation/evidence/gate-four-option-confirmation.md`
- `.agenticdoc/mw-dp-consolidation/evidence/h02-stage-close-confirmation.md`
- `.agenticdoc/mw-dp-consolidation/evidence/h13-signoff-gate-link-confirmation.md`
- `.agenticdoc/mw-dp-consolidation/evidence/research/spec-confirmed-intent-20261024.md`
- `.agenticdoc/mw-dp-consolidation/key-decision.md`
- `.agenticdoc/mw-dp-consolidation/tasks/RQ10-graduation-dp-contracts.md`（本卡）
- `.agenticdoc/mw-dp-consolidation/evidence/graduation-audit-dispatch-20261025.md`

定点读（关键词/行区间，未全文）：
- `.agenticdoc/mw-dp-consolidation/pm-state.md`：:7、:33、:70、:72、:74、:75、:78、:83 相关行
- `.agenticdoc/mw-dp-consolidation/evidence/research/spec-gate-authority-20261024.md`：:8、:11、:36、:37、:45-:51、:65 相关行

锚点：
- `.agenticdoc/goal.md:5`（项目目标）；goal 仅读前若干行，未全文重读。

未读（不在本 RQ 范围）：其他 key、packages/** 源码、活配置/gate/ledger/凭证、RQ7/8/9 研究证据全文、h03～h12 确认文件、RQ11/RQ12 任何产物。
