# RQ20 — UI 可提交面 / 上下文与历史消费者补核（设计取证，静态）

> key `mw-dp-consolidation`（DESIGN，联合设计/实施未批准）。type research，images=no，时间盒 25 分钟，唯一证据文件。
> 只做读码取证与候选建议：未运行测试/build/install，未起停服务，未开浏览器，未调用 provider 或裁决服务，未读活配置/gate/ledger/签收/凭证，未改源码/UI/框架回执，未签收。
> 证据等级沿用 RQ17 定义：**L0** 行级静态事实；**L1** 隔离生产路径测试；**L2** 真实链/安装镜像观察。本文全部为 **L0**；文中不宣称 AC/QG/设计/运行/签收通过。

## 结论

1. UI 侧实际有两个互不相通的“可提交面”：`decision_dashboard.js`（HTTP 只读页 + `scope=test` 的 observe_only 观察提交/校验/骨架/离线 case）与 pi 窗口的 `/mw decide ...`（转发 Python）+ `ask_decision`/`dispatch_worker` 工具面。二者没有共同的可提交协议：前者由 `/api/dps` 的注册表行驱动表单，后者由 `pm/decision-tool.ts` 的**手写 25 条 id 枚举**驱动。旧编号在这两处都仍是“可提交选项”（静态事实，非运行验证）。
2. 仪表盘的表单确实是“协议驱动”的（`fieldTable(point.required_state_fields/optional_state_fields)`、`/api/dps` 直出），但**语义分层是硬编码的**：`DESIGN_FIELDS`（dp1/dp2/dp3/dp25 四个旧 id）、`dp3-worker-clarify`/`dp25-signoff-conclusion`/`dp2-checkpoint-split` 的字面分支、`MATERIAL_LABELS`、`validationGuidance` 的 dp3 指引、`deriveDp3Criteria`。旧编号退役后这些分支要么指向不存在、要么静默失效（`DESIGN_FIELDS[dp] || []` 少一道检查而不报错），因此 AC-003 的“可提交选项数=0”今天无法由协议层保证。
3. 历史面已按“只读 + 不许补造”实现（`legacy` 处理状态、无 v2 workbench 不开 DAG、`未记录` 而非 0/false、`consumed` 明示“不等于采纳或完成”、`settled` 明示“不代表整个任务已交付”），但**没有“退役 DP”标记**：`processing_state=legacy` 只表达“旧数据无 v2 创建事实”，不能表达“该 dp 已退役、不可新发起”（AC-013 的正向可读 + AC-002 的明确拒绝两件事缺一件）。
4. gate 四选项 / PM 预拟 note / 模型理由 / 后继调用状态在当前 UI **完全没有承载面**：注册表 dp15 仍是 continue/narrow/revoke + `gate.kind` 六值（RQ13 A 节）；窗口侧 `DECIDE_CONCLUSIONS = ["continue","narrow","revoke"]` 只用于渲染 `verdict <conclusion>` 预览行；仪表盘没有任何 gate 组件、note 字段或 follow-up stage。因此 AC-007/049 的“note 与理由分开保存”“steer→后继 dp-pm-steer 未发起/失败/返回分别可见”今天不可观测。
5. 图像硬门现状是**三态里只有 `no` 拒绝**：`planDispatchFrontmatter` 注释与代码明写 `"unknown" fails open by design`（L1851-1857），`modelImageCapability` 的未知分支（空值/无 registry/非 pi cli/无 modelId/CLI executor 前缀/无 provider/registry 未命中/异常）全部返回 `"unknown"`（`dispatch-models.ts:236-249`）。所以“需读图 + 能力 unknown”今天会**照常启动 Worker**。这只能作为现状陈述，不能拿 unknown 当能力证明；目标断言应为“vision 任务仅 `yes` 可派发，unknown 与 no 都 0 启动”，且不得把 `roleForTaskType` 的 unknown→coding 回退当作能力兜底。
6. 签收职责边界：窗口 `/mw decide sign` 已“无 conclusion 位参、无 --auto”，Python 单写面决定并只在 `signed_via`/`path` 出现时显示为已签收（`runMwDecideCommand` L4988-5075；`parseDecideSignOutcome`）。但四处 finalize 错配里，只有 `decision_history._CLOSED_SETS` 属**历史显示**（把 finalize 显示为未记录结论），`mw.py:2233/3485/3611` 与 `decide_archive._CHANGE_BY` 属 **`dp apply` 旧权限/authority-change 功能**（会写状态），done 硬门（`advance_phase.py:41,339-343`）属**执行放行**。因此不得把 finalize 直接接进旧 promote/demote/revoke 执行器，也不得保留旧 DP 运行别名。
7. 推荐**方案 B′（协议驱动表单 + 显式业务组件消费统一语义投影）**：注册表加“UI 语义块”（选项集合/材料分节/note 与 reason 槽位/followup stage/retired 标记），仪表盘由通用表单渲染器消费该块，gate/sign/route 用少量显式组件消费**同一投影**；禁止再按 dp id 写字面分支。理由与代价见 §C。

## 证据

### A. 覆盖面（本任务书要求的“全文读”）

| 文件 | 行数/大小 | 覆盖 |
|---|---|---|
| `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts` | 5289 行 / 228859 B | **全文读完**（1-1136、1137-2329、2330-3445、3446-4645、4646-5289） |
| `packages/multi-workers/decision_dashboard.js` | 3371 行 / 152064 B | **全文读完**（1-1169、1170-2260、2261-3371，至 EOF） |
| `packages/multi-workers/decision_dashboard.html` | 10635 B | 全文读（DOM 骨架/静态文案/按钮与 select id 清单） |
| `.agenticdoc/mw-dp-consolidation/spec.md` | 53AC 锁稿 | 全文读（§1.1-1.6、§2、§3 AC 全表、§4） |
| `evidence/research/design-signoff-observation-20261026.md`（RQ17） | 全文读 | 用于“四处 finalize 错配”归属 |
| `evidence/research/design-entry-contracts-20261026.md`（RQ13） | 全文读 | 用于 dp15 现状词表、`ASK_DECISION_DP_IDS` 手写清单 |
| `shared/dispatch-models.ts` | 定点读 | `DISPATCH_ROLE_BY_TYPE`/`DISPATCHABLE_TYPES`/`roleForTaskType`/`modelImageCapability`（L52-251） |

**未全文读、明确声明未覆盖**：`packages/multi-workers/decision_monitor.py`（124534 B，路由/CHROMIUM/开窗）、`decision_playground.py`（submit/validate/scaffold/case 的 Python 侧校验与预算）、`decision_points.py`（注册表权威，按 RQ13 行号引用）、`pm/decision-tool.ts`（按 RQ13 L132-234 引用）、`decision_history.py`。因此本文**不**宣称全仓 caller inventory 已完整。

### B. 现状盘点（逐项：事实 → 缺口）

**B1 旧编号可提交选项（AC-001/002/003 的可观测面）**
- 仪表盘 `renderDpOptions()`（L2161-2178）把 `/api/dps` 的 `points` 全量灌入 `<select id="dp-select">`，选项文本 `id · tier · enabled`；`renderSelectedDp()`（L2119-2160）再按该行直出 required/optional 字段表。注册表若仍是 25 行（RQ13 A1/A2），下拉就是 25 个旧编号可提交项——**这是“UI 提交面仍有旧编号”的直接结构原因**，不是渲染 bug。
- 手写语义只在 4 个旧 id 上存在：`DESIGN_FIELDS`（L80-91）、`localCaseIssues` 的 dp3/dp25/dp2 分支（L3086-3175）、`renderQuestionsEditor` 的 `dp === "dp3-worker-clarify"`（L2887/2946）、`deriveDp3Criteria`（L2823-2836）、`choicesText` 的 `dynamic_choices`（L2809-2821）。dp id 改名/退役后：字段表仍会渲染（协议驱动），但 `DESIGN_FIELDS[dp] || []` **静默跳过**必填检查（L3111-3113），dp3 专属派生也不再触发 → “退役后仍能提交但校验变弱”，比直接报错更危险。
- 工具面：`ask_decision` 的 dp 枚举来自 `ASK_DECISION_DP_IDS`（`pm/decision-tool.ts:132-158`，25 条硬编码，RQ13 A3），与 `decide-registry.generated.ts`（生成物）并存；本文所在会话的 `ask_decision` schema 亦列出 dp1…dp25 全 25 项（工具描述静态可见）。这是第二份“可提交选项”事实源。
- 无“退役”概念：未注册 id 在 Python 侧是 `DecisionInputError`（RQ13 A4），所以退役后下拉里根本没有该项，也**没有**“此 id 已退役、可读历史、不可发起”的呈现位。AC-002 要求的“明确拒绝”只能靠未知 id 错误，无法与拼错区分。

**B2 case/book 动态契约**
- `case-select` ← `GET /api/test/cases`（`loadCaseList` L3050-3080）；`openSelectedCase`（L3082-3114）把 `found.book` 整体写入 `book-editor`，`syncMaterialEditor()` 再投影出 `book.state` 到 `material-editor`；两者任一输入都回写（`updateBookMaterial` L2731-2750）。
- questions 来自 case 的 `questions`（`renderQuestionsEditor` L2838-2912）：`instructions` 可编辑，`criteria` 在 dp3 下**只读派生**（唯一来源 `state.handling_options`），`collectQuestions` 对 dp3 **删除** `next.criteria`（L2940-2960）——单一来源纪律在 UI 侧成立。
- `dynamic_choices` 仅以文本呈现（`choicesText`），候选值不在 UI 另存一份；dp3 候选结构校验在 `localCaseIssues`（≥2、id/label/description 必填、label 互异，L3120-3150）——这是**旧 dp3 的 2..5/c1..cN 合同**的 UI 影子，与 AC-042/046 目标（dp-w-check-task 三固定、dp-auto 不套 2..5）冲突，需随注册表迁移一起移除，否则成为第二份合同。
- 观察提交：`submitSelected`（L3300+）→ `sendSubmit` → `POST /api/test/submit`，body 固定 `observe_only: true` + 新 `submit_id`，`retry_of` 只在显式重试时带；`submissionFeedback`（L1975-2010）对 busy/duplicate/low-confidence/unavailable/rejected/unknown 各给一句**不重试**说明。`renderSubmissionDetail`/`submissionDagNodes`（L2263-2400）十节点里 `receipt` 恒 `missing`、`action` 恒 `not-executed`（observe_only 不写业务事实）——与 AC-050“不以 consumed/选择代执行”一致。
- 边界未核（需 Python/CLI 进一步核）：`/api/test/validate` 的 typed 校验是否与注册表同源、`/api/test/scaffold` 的骨架是否按 dp 名硬编码、`/api/test/cases` 的固定表（RQ13 提到 `decide_cases/dp{1,2,3,25}.json`）是否随迁移改名。这些都在 `decision_playground.py`/`decision_monitor.py`，本文未读。

**B3 只读历史标记（AC-013）**
- `PROCESSING_STATE_LABELS = {processing, completed, failed, legacy:"旧数据无状态"}`（L61-66）；`processingStateOf` 无 workbench → `legacy`，有但无字段 → `unknown` → 显示“未记录”（L66-90）。
- `dagAvailable` 只在 `workbench.record_version === 2` 时开 DAG（L373-378）；legacy 行只有“日志”按钮 + `record-dialog-legacy-note`（html）+ “旧数据无状态：不展开 DAG”。
- `renderReceiptAndAction`（L1272-1300）legacy 回退只渲染已记录的 consumed/responded/executed/settled 与 archive 三字段，空 stage 行保持沉默；`renderReceiptFacts`（L1000-1020）对 consumed 固定加“接收不代表采纳或处理完成”，`renderActionFacts`（L1140-1190）对 settled 固定加“不代表整个任务已交付”，未知前后状态写“不根据接收或本轮结算补猜”。
- 缺口：**没有 retired 标记**。`STAGE_LABELS`/`STAGE_ORDER`（L24-56）只有 suggested…book 12 个旧 stage 词，无 follow-up/route/retired 语义；历史行没有“该 DP 已退役”徽标，也没有“不可发起新运行”的显式陈述（只有页面级“本页不执行业务动作”的总免责声明）。

**B4 模型选择与语义类型分层**
- 仪表盘里的“模型选择”是**答案选择**（`renderDecideNode` L971-1050：`policy.selection`、`policy.confidence`、`model` 节点 detail 的 transport/model/confidence_source），不是派发模型。它与 `task.md` 的 `model:`/`model-reason` 完全无关，命名上极易被误读为同一层（缺口：文案未区分“决策模型”/“模型选择答案”/“worker 派发模型”）。
- TS 侧分层清晰：`type`（语义类型，`DISPATCHABLE_TYPES` 六值：coding/review/research/rag-research/vision/decide_prepare）→ `role`（`DISPATCH_ROLE_BY_TYPE`，`roleForTaskType` unknown→coding）→ `model`（dispatch.yml role 默认 / 显式 override / vision auto-route）。dp-w-type 目标候选是 **4 值**（coding/research/review/vision），与 `DISPATCHABLE_TYPES` 的 6 值**不是同一个集合**：前者是 DP 选项菜单，后者是框架任务类型白名单；AC-044 要求“不移除未列菜单的既有类型”，因此两者必须继续分开呈现，不能拿菜单去裁剪白名单，也不能拿白名单冒充菜单。
- 图标/徽标：`renderDecideNode` 有 `zero_call`、`available:false`、阈值“未记录不按当前配置补造”等诚实标签；派发侧 `echo` 行区分 `model: dispatch.yml <role>=<id>`、`model override: … (reason: …)`、`model: dispatch route default`、`(model-source: auto-route, <role> -> vision)`（ui-bridge L1890-1930）——四态可区分是既有资产，应被 UI 复用而不是重造。

**B5 PM 事件 / 当前窗口 tool result 上下文**
- 窗口侧两条通道：`displaySummary`（L201-214，`sendMessage` 无 `triggerTurn`，被动展示）与 `deliverPmAlert`（L218-232，`triggerTurn: true`，唤醒 PM 回合）。工具结果以 `execute` 返回的 `content[].text` 进入对话；`ask_decision` 的不可用/缺字段结果同样只回到当前窗口上下文。
- 仪表盘协议**没有任何 PM 事件或 tool result 通道**：它只读 `/api/history`、`/api/dps`、`/api/test/history|cases|submissions|validate|submit|scaffold`（js 全文）。因此“PM 事件/当前窗口 tool result”今天**不能**在仪表盘呈现；若设计要求呈现，必须新增 Python 侧协议（`decision_monitor.py` 路由 + 投影），这不是 UI 单侧可完成的（边界）。
- 反向亦成立：仪表盘的全部事实来自后端投影（`workbench`、`calls/attempts` 捕获、`outcome`），窗口上下文（对话、工具返回值、watch key）不落盘、不进投影——AC-014 的 producer→writer→consumer→projection 链在“跨语言”段只覆盖到 HTTP 载荷，不覆盖对话上下文。

**B6 gate 四选项 / note / 理由 / 后继调用状态（AC-007/049）**
- 现状词表：dp15 注册行为 `continue|narrow|revoke` + `gate.kind` 六值（RQ13 §1 表）；目标是 `approve|steer|need_fix|reject` + 送审前 PM 预拟 note（事项/批准后动作/目标/证据/预算/授权依据）+ 与模型理由**分开保存**。UI 侧：`MATERIAL_LABELS`（L120-165）不含任何 note/reason/disposition 键；`renderBasis`（L1000 前）只解释“依据行”；没有任何组件渲染四选项、note 或“steer/need_fix 不等于已放行”的提示。
- 窗口侧：`DECIDE_CONCLUSIONS = ["continue","narrow","revoke"]`（ui-bridge L4603）用于 `formatDecidePreview` 逐结论打印 `verdict <conclusion>: ok|REFUSED`；`/mw decide sign` 本身不再接受结论位参（正确方向），但这三个旧词仍被当作“应存在的结论集合”渲染——若迁移后给 dp-sign-key 之外的面复用，就会把旧词表当成验收词表显示（历史显示可解释，不能反过来当目标契约）。
- 后继调用状态：`STAGE_ORDER`/`STAGE_LABELS` 无 `followup`/`route`；`renderActionFacts` 只分 before/executed/settled/after；`feedbackErrors`（L1206-1240）只汇总 call attempt 错误与 receipt/action 的 `errors[]`。因此“gate 选 steer 后，PM 的后继 dp-pm-steer 请求未发起 / 调用失败 / 返回选择 / 实际整改”四态**无呈现位**，AC-049 的正反观测缺载体。
- `role` 资格：仪表盘不判角色（页面 token 只证明“页面角色”）；窗口侧 `role-forbidden` 由 `ask_decision` 返回（RQ13 A3）。呈现层若要根据身份隐藏/禁用按钮，必须读取服务返回的资格事实，不能由 route/页面上下文推断——现状没有任何此类呈现，故也无越权面（但同样无“按资格禁用”的正向证明）。

**B7 图像硬门（AC-044 现状 vs 目标）**
- 现状三态：`images: "no"` 短路不检测；`images: "yes"` 强制需求；缺省按描述扫现存图片文件。能力判定 `modelImageCapability` 只有 `registry.find(...).input.includes("image")` 才给 `yes|no`，其余 **9 类分支全部 `unknown`**（含非 pi cli、CLI executor 前缀、无 registry）。
- `planDispatchFrontmatter` 的 gate（L1851-1866）只在 `capability === "no"` 时拒绝；注释明写 “unknown fails open by design”。auto-route（L1838-1848）只在“未显式 pin + 需要图 + role 能力 `no` + vision 角色能力 `yes`”时改 **model**，不动 `type:`（D-004）——这条边界是对的，不能把它改成“改 type 冒充 vision”。
- 与目标（AC-044）的差：目标要求“需图任务类型为 vision 且有效能力满足才可派发，无能力 Worker 启动 0”。今天 `vision` + `unknown` 会启动；`coding` + `images: yes` + 能力 `unknown` 也会启动（且 type 仍是 coding，`roleForTaskType` 也只决定 role）。**unknown 只是现状，不是能力证据**。
- 派发事实的独立证明：`writeDispatchTaskMd` 写 `type:`/`phase:`/`images:`/`model:`/`model-reason:`/`card_path`/`card_sha256`/`envelope_producer`/`decision:`/`read_scope`/`write_scope`，`dispatchTask` 写队列行，`trace.log` 追加 `[DECISION] dp1 state=…`；UI 呈现的是队列行/`readTaskProgress`（`trace.log`）与 `echo` 字符串——**都是 claim，不是能力验证**。要证明“能力满足”，需要独立一步（registry `input` 的实际读 + 派发前断言），不能由 `echo`/`type:` 反推。

**B8 sign-key 职责边界（AC-038/039/050/051）**
- 窗口：`parseDecideArgs` 只允许 `show | sign [--allow-empty] [--key] | dp list|show|export | monitor`，`sign` 无结论位参；写前用 `sign --key <k> --dry-run --json` 做只读预检，写只发一次 `sign --key <k> --json`；`parseDecideSignOutcome` 要求 `signed_via` 或 `path` 才算签收，否则报“未签收 + 原因”。不转发 `--auto`/`--project`（避免覆盖项目 `signoff: disable`）。
- 四处 finalize 错配的归属（沿用 RQ17 A2/A3/A4，本文只做归属判断）：
  1. **执行放行**：`advance_phase.py:41` 的 `^(continue|narrow|revoke)$` 与 `:339-343` —— done 硬门，属“哪些结论算成功”的执行判据（必须由 finalize + 证据决定，且不能变成第二份 validator）。
  2. **旧权限/状态写入**：`mw.py:2233 _DP_SIGN_CONCLUSIONS`、`:3485` 拒绝、`:3611 _dp_apply` 写 `by=f"signoff:{conclusion}"` 的 authority-change —— 属 `dp apply` 旧权限配置功能（会改状态/档案闭集），**不是**显示问题。
  3. **旧权限配置闭集**：`decide_archive.py:70-81,528-542` 的 `_CHANGE_BY`/`_CONCLUSIONS` —— 同上，写侧闭集，需与 1/4 同步而不是各自扩词。
  4. **历史显示**：`decision_history.py:916-930,1021-1030,3571` —— `<finalize>` 落在闭集外被置 `None` + `unknown conclusion` 警告，属**只读投影显示**；修正它不改历史字节，也不构成运行入口。
- 因此：`finalize` 只能接到“签收有效性判据（finalize + 对应证据 + logical_id/snapshot 绑定）”上；直接接进旧 promote/demote/revoke 执行器就是扩大职责（AC-039 禁止），保留旧 DP 运行别名同理禁止（AC-001/002）。
- 仪表盘的 sign 呈现：`renderReceiptFacts` 只显示“签收文件：已验证/未验证+原因”，`file_verified` 来自后端 `validate_signoff`；这是正确的“文件≠phase done”措辞基础，但没有显示 conclusion 词表与 logical_id，故“这份文件签的是哪次判断”在 UI 不可见。

### C. 两个合法方案（至少两种，均可独立于本次授权落地设计）

**方案 A：纯协议驱动表单 + 既有投影（最小改动）**
- 做法：`/api/dps` 继续直出注册表行；表单/字段表/校验结果全部由该协议渲染；退役只在 Python 注册表删除（`/api/dps` 自然不再返回），UI 零改动。
- pros：单一事实源（今日 `fieldTable` 已如此）；无第二份 UI 合同；契约锁已在 Python（`test_decision_dashboard_playground.py` 明写 `/api/dps` 暴露已注册 DP 的 typed 字段）。
- cons：①无法表达 dp 级语义（note/reason 分列、四选项、followup）；②`DESIGN_FIELDS`/dp3/dp25 字面分支仍在，退役后静默放宽校验；③无法呈现“retired / 不可发起”，AC-002/013 的正向可见性缺失；④`dp-select` 会随注册表变成 8 项，但“旧编号=明确拒绝”仍只有未知 id 错误。
- 候选接口（不改动，仅定位）：`decision_dashboard.js:renderDpOptions/renderSelectedDp/fieldTable`、`decision_monitor.py` 的 `/api/dps` 投影。

**方案 B′（推荐）：协议驱动表单 + 注册表声明的“UI 语义块”，由显式业务组件消费同一投影**
- 做法：注册表每行加一个可选 `ui` 块（不新增业务材料字段）：`ui.options[]`（id+label+语义）、`ui.material_sections[]`（分组，替代 `DESIGN_FIELDS`）、`ui.slots {note, reason, followup}`、`ui.status`（`active|retired` + `successor`）；`/api/dps` 与 `decide-registry.generated.ts` 同步携带；仪表盘保留通用表单渲染器消费 `material_sections`，另加 3 个显式组件（gate 面板 / sign 面板 / followup 状态条）消费同一 `ui` 块与既有 workbench 投影；`MATERIAL_LABELS` 改为 `ui` 块内的 label 表，`DESIGN_FIELDS`/dp3 分支/`deriveDp3Criteria` 删除并由 `ui.options` 通用派生（dp3 的“候选唯一来源”改成“选项组声明唯一来源”，语义保留）。
- pros：①“可提交选项集合”与“退役集合”可由协议机械核对（AC-001/002/003）；②gate 的 note/reason/followup 有了唯一定义位，组件只渲染不解释（AC-007/049）；③旧编号退役后 `status=retired` 可在历史行徽标 + 下拉禁用（AC-013 可读 + AC-002 不可发起）；④删除字面分支后不再有“静默放宽校验”；⑤全部值仍走 `textContent`（现有 `el()` 纪律），note/理由不经过任何 HTML 拼接。
- cons：①`ui` 块是新的跨语言契约，需要生成链与字节锁（`decide_registry.json` + `gen_decide_registry_ts.py` + `test_decide_registry_*`）；②组件与通用表单并存，需要一条“同一投影只读”契约测试防漂移；③`DYNAMIC_CHOICES_MAX=5` 与 dp-route 七目标的冲突（RQ13 C4）仍需单独解决，不能靠 UI 绕过。
- 候选文件/接口（仅定位，未授权修改）：`packages/multi-workers/decision_points.py`（注册表 `ui` 块）、`decide_registry.json`、`scripts/gen_decide_registry_ts.py`、`shared/decide-registry.generated.ts`、`pm/decision-tool.ts`（dp 枚举改为生成）、`pm/ui-bridge.ts`（`DECIDE_CONCLUSIONS` 改为读注册表 success 集合；`planDispatchFrontmatter` 图像门改为 vision 需 `yes`）、`decision_dashboard.js`（`renderDpOptions`/`renderSelectedDp`/`fieldTable`/`localCaseIssues` 改造 + `components/*`）、`decision_dashboard.html`（gate/sign/followup 容器）、`decision_monitor.py`（`/api/dps` 携带 `ui`）、`decision_playground.py`（校验与 `ui` 同源）。

**不推荐方案 C（把结论写进签收文件供门禁/UI 读，如 `signoff_ok: true`）**：自述字段不是判断证据，等于把门禁降为布尔（RQ17 方案 C 已拒绝）。
**不推荐方案 D（用 `signoff: disable` 或隐藏按钮绕过）**：项目级 disable 会同时豁免所有 key，且掩盖而非解决 AC-039。

### D. 候选断言（正反 / 秘密注入 / 历史字节不变 / 后继未发起与失败 / 未知能力）

> 全部为**设计期断言骨架（L0 可静态核对 → L1 需隔离生产路径）**，不是通过声明。

| AC | 正向 | 反向/失败 | 秘密与注入 | 历史/边界 |
|---|---|---|---|---|
| 001/002/003 | `/api/dps` 与生成枚举与 `ask_decision` schema 三处 id 集合相等且=八名；下拉/工具枚举只出八项 | 请求旧 id → 明确拒绝（区分 retired/unknown），模型请求数 0、业务执行数 0、新有效决策 0 | 拒绝文案不回显请求体；id 值只按文本渲染 | 历史行仍可读旧 id；`ui_submission_options ∩ retired = ∅` 由协议机械核 |
| 007 | gate 面板渲染四选项 + PM note + 模型理由两块（分列、只读徽标区分来源） | 非法/缺失 note、未知选项值 → 阻塞且 0 放行；steer/need_fix 不显示为已放行 | note/reason 含 `<img onerror>`/`</script>` 时只作文本（`textContent`），不得 innerHTML | 旧 dp15 记录只读解释，不把 continue/narrow/revoke 当目标选项 |
| 012/013 | 不可用/材料非法/无有效裁决 → 具体原因 + 阻塞徽标；历史 legacy 行可见且只读 | 不默认放行、不偷换入口、不补造 decision_id；legacy 行无“发起”按钮 | 失败审计只记 code/reason，不落请求正文 | 一次 `load_history` 前后 archive/sign-final sha256 不变；`processing_state=legacy` 与 `retired` 两标记互不替代 |
| 014 | producer→writer→consumer→projection 四段字段可在隔离项目复现（dp/decision_id/stage/outcome/signoff） | 任一环缺失 → 显示“未记录”，不推断执行 | 投影侧 redact；页面无 `innerHTML`/`eval`/`new Function`（本文静态核：dashboard js/html 均 0 命中） | 跨语言段只到 HTTP 载荷（见 B5 边界） |
| 038/039 | 仅 finalize + 证据 + logical_id/snapshot 绑定显示为已签收；continue/user-confirm 显示 0 文件 + “不代表完成” | 换一份同 key 旧 finalize → 判据不通过；`signoff: disable` → 显示跳过原因而非通过 | 签收材料含 `sk-`/Bearer 时 UI 不显示明文（只显示 redact 计数/摘要） | 历史显示层可解释 finalize（只读），不得回写历史字节；不把 finalize 接进 promote/demote/revoke 执行器 |
| 040/041 | route 面板只列其余七入口 + 依据；固定节点直调无“额外路由”步骤 | 复合问题未拆 → 拒绝；role 越权（PM 调 Worker 专属/反之）→ `role-forbidden`，执行 0 | 路由依据按文本渲染 | route 选择不产生业务放行（决策记录里 route 行无 executed/settled 业务动作） |
| 042/044 | dp-auto 选项 ⊆ PM 已准备候选；dp-w-type 面板恰 4 值 | 未准备的新方案不出现；vision+能力 `unknown`/`no` → **Worker 启动 0**；`coding`+`images: yes`+unknown → 同样 0（不得回退冒充） | 能力证据来自 registry `input` 实际读取，不来自 `echo`/`type:`/UI 文案 | `DISPATCHABLE_TYPES`（6）不被菜单（4）裁剪；rag-research/decide_prepare 类不因 UI 迁移消失 |
| 049/050 | gate 选 steer/need_fix 后 followup 状态条列四态：未发起 / 调用失败 / 返回选择 / 实际整改，各自有独立事实 | 后继未发起或失败 → 不因 gate 选择推断完成；重复请求 → 去重 0 | followup reason 文本渲染 | before/after 快照保留来源与时间非递减；settled≠done；不以 consumed/选择代 executed |
| 051/052/053 | `null`（未记录）与 `[]`（明确无）分开渲染；三数组缺项不能变 null | dp25 数组非数组 → 材料拒绝；同事项重放 → 不新增同事项审批；实质变化 → 旧批准不放行 | 秘密明文出现次数 0（材料/投影/页面三处） | QG pass/fix/reopen 与“后续实际处理”分列；QG 通过不显示为签收/stage 关闭 |

### E. 与既有研究的关系（不重复、不覆盖）

- RQ17 显式遗留“未读 TS 侧/UI 消费者如何呈现 `signoff.conclusion` 与警告通道”；本文补上该段的**静态**结论：UI 只显示 `signoff.file_verified`/`file_reason`，不显示 conclusion 词表与 logical_id；`DECIDE_CONCLUSIONS` 是窗口侧唯一的旧词表呈现点。RQ17 的“另三处词表”性质（执行/写侧）本文不改判。
- RQ13 显式遗留“未核 dashboard/playground/case UI 可提交面是否另有旧 id 枚举”；本文补上：有，且分三类（`/api/dps` 全量下拉、`DESIGN_FIELDS` 四 id、dp3/dp25 字面分支），另有工具面手写 25 条枚举。
- 本文不宣称“全仓 caller inventory 完整”：`decision_monitor.py`/`decision_playground.py`/`decision_points.py`/`decision-tool.ts` 未全文读。

## 残留与未验证

1. 未运行任何测试/CLI/服务/浏览器；所有 UI 行为均为读码推断，未做真实 DOM 渲染或 HTTP 往返。
2. 未读 Python 侧 `decision_monitor.py`（路由、token、投影组装）、`decision_playground.py`（validate/submit/scaffold/case 的 typed 校验与预算）、`decision_points.py` 全文 —— 因此“`/api/dps` 是否已按退役过滤”“typed 校验与注册表是否同源”“case 固定表是否按旧 id 硬编码”三项**未验证**。
3. 未读 `pm/decision-tool.ts` 全文（按 RQ13 行号引用 `ASK_DECISION_DP_IDS`）；未核 `ask_decision` 的 dp 枚举是否还有第二处生成/校验。
4. 未核安装/部署镜像：`packages/multi-workers` 的 dashboard 资源是否与已安装 bundle 字节一致（source 相同不等于安装内存身份）；未读 `.mw` 活配置。
5. 未核图像能力的真实 registry 数据（`models.generated.ts` 的 `input` 字段）与派发前实际分辨率；本文只断言“未知分支存在且 fail open”，不断言任何具体模型能力值。
6. gate 四选项/note 的**精确 schema 与 Python 状态转换**未设计、未授权；本文只给呈现层候选位，不冻结字段名。
7. 未核 `decision_history.py` 的 retired/警告通道细节（引用 RQ17 行号）；未核 monitor 的 8AC 与 dropdown 旧交付债是否与本项重叠（spec §4 明示保留）。
8. 缺陷先声明：`DESIGN_FIELDS[dp] || []` 在退役后静默放宽校验这一点是**读码推断**，未构造用例实测。

## 上下文来源

- 任务书：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq20-design-ui-chain/task.md`（含 `tasks/RQ20-design-ui-submission-chain.md` 卡片，`card_sha256: 22c3a3d9…`）。
- 目标锚点：`.agenticdoc/goal.md:5`；`.agenticdoc/mw-dp-consolidation/spec.md`（§1.1 L20-36、§1.2 L38-62、§1.5 L78-88、§1.6 L98-110、§3 AC-001～053、§4 L181-）。
- 全文读主源码：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（5289 行）、`packages/multi-workers/decision_dashboard.js`（3371 行）、`packages/multi-workers/decision_dashboard.html`（10635 B）。
- 定点读：`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:52-251`（类型/角色/图像能力三态）。
- 同 key 既有取证（全文读，仅作归属引用，不重复其结论）：`evidence/research/design-signoff-observation-20261026.md`（RQ17）、`evidence/research/design-entry-contracts-20261026.md`（RQ13）。
- 本文唯一证据文件：`.agenticdoc/mw-dp-consolidation/evidence/research/design-ui-submission-chain-20261026.md`（key 内路径 `evidence/research/design-ui-submission-chain-20261026.md`）。
- 未读（按任务书禁读）：活配置 `.mw/decide.json`/`.mw/decide-points.json`、任何 gate/ledger/签收文件、凭证、其他 key 运行材料、图片。
