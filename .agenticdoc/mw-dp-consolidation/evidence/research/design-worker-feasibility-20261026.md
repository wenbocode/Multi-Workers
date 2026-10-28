# RQ16 Worker 可达性三项 / 自主真终态 / vision 派发取证（25 分钟只读）

事实 / 目标 / 建议分开。本文件是静态源码观察与设计候选，不是运行验收、设计批准、AC/QG/签收结论。

## 结论

### 事实（源码可核，未运行）

F1. Worker 主动判断当前任务可达性的**唯一在册业务入口**是 `ask_decision(dp3)`：Worker 分支用本任务卡 `type:` 解析发起角色后注册共享工具（`index.ts:92-93`、`decision-tool.ts:715`）；dp3 不在 PM-only 集合（`decision-tool.ts:214`，`:1228` 仅对 dp2/dp25 返回 `role-forbidden`）。材料契约是问题原文 + 四背景 + 2..5 候选（`decision-tool.ts:221-229`），返回是 `handling` 选择，`acted=false` 回执（`worker-mode.ts:4209-4222`）。

F2. 结束时的**自动** dp3 路径不能替 Worker 做可达性判断：`attemptDp3Clarification` 只在结算 `exitCode===2` 时触发（`worker-mode.ts:4431`），且本进程没有 agent 自备材料，`decideDp3WorkerClarify` 直接按 `input-incomplete` 本地降级、零 spawn、不调 provider（`worker-mode.ts:5678`）。这是既有事实，不是服务故障。每次 run 最多自动应答一次（`worker-mode.ts:4149`）。

F3. 终态映射只有三条：`exit 0/2/1 → done/needs-clarification/failed`（`worker-mode.ts:3097`），另有模型耗尽 `exit 3 + model_exhausted`；四值终态集在两侧一致（`status-model.ts:1593`、`mw_common.py:175`），`needs-clarification` 在队列侧不算 done（`launcher.py:981,992`）。**没有**“Worker 判断本任务不可达并给真实结论”的独立终态：`needs-clarification` 今天语义是“产物/恢复契约/claim 未结算”，会把“边界内不可完成”与“产物不合格”混在一起。

F4. 有界补证的三项要素今天都不存在机器载体：无补证结束判据字段、无补证预算计量（只有墙钟/空闲/检查点：`worker-mode.ts:396,402,436,447,452`）、补证来源无白名单（read_scope/write_face 只管读写面，`:3422`）。落地证据只有 `[WRITE_FILE]` 台账 + 检查点 landing 信号（`:593`、`computeRisk:512`）。

F5. vision 是三层分离现状：语义类型（`dispatch-card.ts:224` 词表内 `vision`）、模型角色（`dispatch-models.ts:81`/`mw_common.py:144,157` → `vision` 桶）、CLI 路由（`dispatch.py:128` 走 pi/timi，`conductor_dispatchable=True`）。图像能力硬门有三处：PM 派发时 `modelImageCapability` 只对确定 `no` 拒绝、`unknown` 放行（`ui-bridge.ts:1807,1853`、`dispatch-models.ts:228`）；`mw model set vision` 写配置时拒 `no`、`unknown` 仍写（`mw.py:8721-8745`）；Worker 启动 `images: yes` 且模型无 `image` 输入即拒绝（`worker-mode.ts:3144-3175`）。

F6. vision 派发的两个真实缺口：①PM 自动路由只换 `model:` 不换 `type:`（`ui-bridge.ts:1838-1852`），于是“按 vision 角色派发”并未发生，Worker 仍按原类型拿工具集；②Worker 侧硬门只看 `images:` 头（`worker-mode.ts:768`），PM 侧 `images: no` 短路后即便正文引图也不会再探测（`ui-bridge.ts:1807`）；③`vision` Worker 的决策发起角色按 `initiatorRoleFromWorkerTask` 落为 `unknown`（`decision-tool.ts:715` 只认 coding/research/review），不属于任何工具/写面越权，但角色分层不完整。

F7. 写面已是“角色分类 + 双载体”模型：writeless 角色默认面 = 本 taskDir + `<key>/evidence/**`，writable 角色默认面 = 工作树，声明载体 `write_face:` 权威（`worker-mode.ts:3422` 及后续 bash/write/edit 同判），`worker_file` 是 writeless 角色唯一写通道，64 KiB 上限、basename/evidence 两面（`worker-file-tool.ts:60,96,101`）。补证产物因此**不需要**新写面，只需在既有 evidence 面内落文件。

F8. `dp-w-type` 目标四候选与既有类型的真实关系：可派发集合今天更大（`dispatch-models.ts:78`：coding/review/research/rag-research/vision/decide_prepare，另有 `verifier/reviewer/repair/phase-writer/roadmap-writer/codex` 在词表与工具表中，`dispatch-card.ts:224`、`worker-mode.ts:111-153`）。四候选不能当“现有类型白名单”使用，也不得凭只读菜单删类型。

### 建议（候选，未批准）

S1. 三项业务 -> 技术映射（不新增同步等待通道）：`继续` = 不产生终态、不写入 `## Questions`、按原目标/预算继续；`终止真实结论` = 一次终态写盘，结论块含 完成/未完成/阻断原因/证据 path:line，终态沿用 `exit 2 needs-clarification` 或在设计批准后新增独立“本任务不可达”终态值；`继续补证` = 追加一次有界补证单元，结束判据必须先于补证写入产物。禁止把 `终止` 解释为 `done`、key 取消或目标收窄（与 `dp3-worker-initiated-discussion.md` 定稿一致）。

S2. 补证单元的最小机器字段（候选）：`unknown`（一句具体未知）、`sources`（可达 path/命令，落在既有 read_scope 与工具白名单内）、`budget`（本单元允许的工具调用数或分钟，来自既有墙钟余量，不新增全局限额）、`stop`（可判定的结束判据，机器可核：文件存在/命令退出码/断言表）。缺 `stop` 或来源越权 -> 不放行补证，直接按条件不足终止。不设固定次数/时长常量。

S3. 两个方案对比（至少两案）：
- 方案 A（推荐）：**终态前一次性自评**。复用现成的一次性 turn 机制（`selfCheckSent` `worker-mode.ts:3771`、`settleOrSelfCheck:4502`、检查点 steer 文本 `:367`），要求 Worker 在申报终止/补证前写出结论块；框架只做机器校验（块存在、字段齐、来源在面内、预算未超），不替它判断“是否可达”。
- 方案 B：**结算分支机器判据**。扩展 `attemptDp3Clarification` 的触发面（`worker-mode.ts:4431`），把 `exitCode===2` 的缺口分类成“产物缺口 / 可达性缺口”，可达性缺口才允许注入一次补证 steer。优点是零新增 agent turn，缺点是把不可达与产物不合格继续混在 `needs-clarification`，且结论块的“真实结论”仍需产物承载。
- 取舍：A 的语义最接近“Worker 自主至真终态”，B 的改动面最小。可组合：B 做触发分流，A 做结论块与补证字段。共同硬约束：服务不可用/材料非法不是三项之一（保持 `unavailable`/`input-incomplete` -> 人路径，`worker-mode.ts:5678`、`:4156` 的 fail-soft 结构不变）。

S4. watchdog/deadline 兼容：补证单元必须落在既有预算内（墙钟 `resolveBudgetMs:409`、空闲 `402`、工具空闲 `436`、deadline steer `452`），不得因“补证”重置计时或提预算；检查点 `computeRisk` 的 `landed/artifactPresent` 信号（`:512,593`）可直接作为补证进展证据，不新增第二套台账。

S5. vision 派发建议：`dp-w-type` 输出 `vision` 时必须同时满足“任务需读图”（现 `detectImageNeed`/`images:` 三态，`dispatch-models.ts:259`、`ui-bridge.ts:1807`）与“有效模型 `images=yes`”；需图但只能得到 `unknown` 时按既有 fail-open 记录可核证据，需图且确定 `no` 时启动数为 0，且**不得**回落为 coding 类型冒充（类型与模型选择分开记录）。PM 自动路由应作为“模型路由事实”，不能替代类型选择：类型仍由 `dp-w-type` 决策给出。

S6. 精确候选写面（仅本 RQ 范围）：
- Worker 结论/补证产物：本 taskDir 的 `progress.md|report.md|report-<slug>.md` 与 `<key>/evidence/**`（现面，`worker-file-tool.ts:96-110`）。
- 机器判据/台账：仅 trace.log 追加行（`[DECISION]`/`[CHECKPOINT]` 既有锚），不新增第二个决策账本。
- 明确不写：`pm-state.md`、`_workers*`、`_index.parallel`、其他 key、`packages/**`、`.git/**`、活 registry/配置/ledger。

S7. 与 PM/协议的接口需求（需求，不是实现）：①PM 需能区分“本任务不可达终止”与“产物不合格 NC”，否则后续派发会误判；②PM 吸收终态时不得把 Worker 的 `终止` 当 key 收窄或目标完成；③补证预算/结束判据若需跨进程可见，只经既有 `run.json`/trace 事实暴露，worker 不取得 PM 专属工具（`decision-tool.ts:214`）。

S8. AC 可观测点建议（L0 静态/命令面；L1 隔离 faux 测试；L2 真实生产路径证据）：
- AC-004/046/047：L0 检查三选项在 registry/提示词/工具材料中可区分且无“等待 PM”选项；L1 用 faux 构造满足/不满足/未知三例，断言结束判据缺失时补证放行数为 0；L2 一次真实 run 的 trace 行 + 产物。
- AC-044：L0 断言需图任务在模型 `images=no` 时派发被拒且类型记录不是 coding；L1 三态（yes/no/unknown）对照；L2 一次 vision 派发的 `[MODEL]`/`images:`/工具集证据。
- AC-027/041/052：L0 断言 Worker 侧无 PM-only DP、写面同判；L1 越权写/角色越权请求各 1 例；L2 claim/独占面检查记录。
- AC-050/051：L0 断言结论/补证产物与交付段标题契约一致；L1 null/[] 区分与 executed/settled 不代 done；L2 同 key/task/decision_id 关联可核。

## 证据

（全部为本次静态读取；`worker-mode.ts` 全文 5517 行按 700/1160/2966/3846/4900 起分五段读完，`dispatch-models.ts`、`worker-file-tool.ts`、`task-dispatcher.ts`、`index.ts` 全文，`dispatch-card.ts`/`decision-tool.ts`/`ui-bridge.ts`/`mw_common.py`/`dispatch.py`/`mw.py` 定点读。）

- `packages/coding-agent/src/extensions/agent-team-loop/index.ts:92-102` Worker/PM 共用一个决策工具，角色结构性固定。
- `.../pm/decision-tool.ts:214` PM-only = dp2/dp25；`:221-229` dp3 材料与 2..5 候选；`:715` Worker 角色仅 coding/research/review，其余 `unknown`；`:1228` 角色拒绝点。
- `.../worker/worker-mode.ts:4149` 每次 run 一次自动 dp3；`:4156` 结算插入点；`:4209-4222` `handling` 只回执不执行；`:4431` 触发条件 `exitCode===2`；`:4388` exit 码折叠；`:3097` 状态映射。
- `.../worker/worker-mode.ts:5678` 缺材料 -> `input-incomplete`（本地、零 spawn）；邻近 `escalate` 家族即失败词表。
- `.../worker/worker-mode.ts:111-153` 工具白名单（`:143` vision = coding 集）；`:155` 未注册类型判定；`:1238` conductor 派发拒绝；`:3144-3175` 图像能力运行时兜底；`:768` `images:` 头解析。
- `.../worker/worker-mode.ts:396,402,436,447,452,512,593` 预算/空闲/检查点/风险/landing 信号；`:3422` 写面角色分类；`:3771,4502` 一次性自检与结算函数。
- `.../worker/worker-file-tool.ts:60,96,101` 64 KiB 与共享写面判定、evidence 域。
- `.../shared/dispatch-models.ts:78,81,228,259` 可派发集合、类型->角色、三态图像能力、图像需求探测。
- `.../shared/dispatch-card.ts:224,253` 类型词表（含未在四候选内的既有类型）。
- `.../pm/ui-bridge.ts:1807,1838-1852,1853` 图像需求/自动路由只换模型/能力硬门。
- `.../pm/task-dispatcher.ts`（全文）派发时唯一写 task.md 前的 write-face 门与 profile 注入，无类型/能力判断。
- `packages/multi-workers/autopilot/dispatch.py:75,128` `DispatchType` 与 vision 注册项（conductor 可派发）。
- `packages/multi-workers/mw_common.py:143-157` 角色桶与 `vision`；`:1893,1917` 图像能力快照；`:175` 终态集。
- `packages/multi-workers/mw.py:8721-8745` `mw model set vision` 的 `no` 拒绝 / `unknown` 放行 / `--force`。
- `packages/multi-workers/launcher.py:981,992` `needs-clarification` 不落 done。
- `.agenticdoc/mw-dp-consolidation/evidence/dp3-worker-initiated-discussion.md` 三项固定业务选项定稿（非本轮新裁决）。

## 残留与未验证

- 未运行任何命令级验证（无测试/build/install），未读活 registry（`.mw/decide-points.json`、`decide_registry.json` 运行态）、活 gate/ledger/凭证，未做 provider 或已安装服务探针；未看图片（本任务 `images: no`）。
- 未全文读 `pm/pm-orchestrator.ts`、`pm/decision-tool.ts`（仅定点 60~80 行）、`ui-bridge.ts`（仅 1760-1880）、`dispatch-card.ts`（仅类型段）、`mw_common.py`/`dispatch.py`/`mw.py`（定点段），因此 PM 侧对 `needs-clarification` 的吸收策略、dp2 steer 与 dp3 的交互路径未核。
- 未验证当前安装进程加载的 bundle 版本；源码事实不等于运行事实。
- 未决定：是否新增独立终态值（涉及 Python `_TERMINAL_STATUSES` 三处镜像与 monitor/QG 消费者，`mw_common.py:175,2150,2958`）、补证预算由 wall 余量导出还是独立计数、`vision` 是否加入 `DecisionToolRole`。
- 方案 A/B 的取舍、字段名、AC/VC 编号分配均未批准；本文件不构成设计锁定或实现授权。

## 上下文来源

- `.agenticdoc/goal.md:5`（项目目标锚点）、`.agenticdoc/mw-dp-consolidation/spec.md`（§1.1/§1.2 dp-w-type、dp-w-check-task、§3 AC-004/027/041/044-047/050-052）。
- 派发卡：`.agenticdoc/mw-dp-consolidation/tasks/RQ16-design-worker-feasibility.md`（`card_sha256: bf18e948…`）。
- 上列源码路径与行号（本次只读）；`evidence/dp3-worker-initiated-discussion.md` 为三项固定选项的已确认业务来源。
- 声明：未读其他 RQ 的原报告与 PM 文档，未修改任何源码、registry、配置、gate、ledger 或他 key 文件。
