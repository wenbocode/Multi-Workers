# RQ-1: 新增派发角色 `vision` + 任务类型 `design` 的完整改动面（两侧镜像）

TL;DR
- Python 侧**单点**：角色清单只有 `mw_common.py:138 DISPATCH_ROLES` + `mw_common.py:139 TASK_TYPE_TO_ROLE`；`mw.py` 的模型命令/校验/错误文本 4 处全部**动态**读 `DISPATCH_ROLES`（无硬编码 4 角色列表），加一项即自动传播到 argparse choices、错误文本、show、doctor 渲染。
- TS 侧类型有 **3 个独立硬编码点**（`shared/dispatch-models.ts:58/74`、`worker/worker-mode.ts:52-83`）+ **3 处硬编码文案**（`pm/ui-bridge.ts:1146/1554/1993`）。
- 「不改就红」（好）：`test_dispatch_models.py:154`、`test_autopilot_dispatch.py:32`、`test_autopilot_l0.py:246`、`test_mwpp_collection_parity.py:62`。会「静默失效」：`agent-team-loop.test.ts:5145` 的子串断言、`agent-team-loop-checkpoint-wiring.test.ts:61` 的 10-key 快照（只遍历自身键）。
- `enforceConductorType` **全仓不存在**；等价物是 `worker/worker-mode.ts:442 function dispatchRefusal(meta)`（内部调 `isRegisteredType`，`worker-mode.ts:88`）。
- 白名单 AC-005 已定为 `["read","write","edit","bash","find","grep","ls"]`（同 `coding`），两侧逐元素同序。

## 决策问题
1. 新增角色 `vision`（`.mw/dispatch.yml` 的 `models.vision`）与类型 `design`（→ role `vision`）时，Python 与 TS 两侧各有哪些消费点必须同步？
2. 双侧 parity/golden 测试哪些会自动红、哪些需人工同步、哪些语料要重冻？
3. `design` 型 worker 的工具白名单挂点在哪，顺序是否被逐元素锁死？
4. 给出 design.md 可直接用的机器可判定 VC 断言与未确认数据缺口。

## 调研方法与出处
只读静态阅读（未运行任何测试、未改任何文件）：`packages/multi-workers/{mw_common.py,mw.py,launcher.py,autopilot/dispatch.py,test_*.py,README.md,UPDATE.md,skills/}`、`packages/coding-agent/src/extensions/agent-team-loop/{shared/dispatch-models.ts,pm/ui-bridge.ts,worker/worker-mode.ts,rag/{block,config,tools}.ts,shared/mw-runner.ts}`、`packages/coding-agent/test/{extensions,suite}/*`、`packages/*/dist/**`（仅定位镜像位置）、`.agenticdoc/mw-vision-role/spec.md`。所有锚点为真实 `file:line`。

## 发现

### 1. Python 侧消费方清单
定义（唯一事实来源）：`mw_common.py:138 DISPATCH_ROLES = ("main","coding","review","research")`；`mw_common.py:139-151 TASK_TYPE_TO_ROLE`（13 键，含 `rag-research→research`，**无 `design`**）。

`DISPATCH_ROLES` 消费者（全部动态引用，加 `"vision"` 即生效，无需改这 6 处）
- `mw_common.py:241-242` `load_dispatch_config` 未知角色报错 + `', '.join(DISPATCH_ROLES)`。→ 加 role 前 `dispatch.yml` 含 `vision` 会让**整文件失效**（`{}, err`，静默回落 window-model）。
- `mw.py:3145-3148` `cmd_model set` 角色校验+错误文本；`mw.py:3195-3198` `clear` 同类 + `or 'all'`；`mw.py:3219` `show` 逐角色遍历（`:3226` 附近用 `task_type=role` 预览，`vision` 非类型名 → 预览走 `coding` 回落，因 `config_models={}` 仅语义偏差）；`mw.py:5129-5130` argparse `choices=DISPATCH_ROLES`+help（CLI 最早拦截，`mw model set visionx` 的 `invalid choice ... (choose from ...)` 自动含 5 角色 → 直接满足 AC-002）；`mw.py:5136` clear help。

`TASK_TYPE_TO_ROLE` 消费者（加 `"design": "vision"` 后自动生效）
- `mw_common.py:305` `resolve_dispatch_model`（role 分桶，AC-003 命中处）；`mw_common.py:911` `render_rag_block` role；`mw.py:1877` `rag audit` role 归属；`launcher.py:172` `_model_override_note` 的 role；`autopilot/dispatch.py:196` RAG meta 回落（此处回落值是 `task_type` 本身而非 `"coding"`，与其余三处口径不同，对 `design` 无影响）。

其他强耦合点
- `autopilot/dispatch.py:52-53` `_CODING_TOOLS`/`_REVIEW_TOOLS`；`:71 REGISTRY`；`:142`/`:446` `REGISTRY.get`（`:456-458` 是 `conductor_dispatchable=False` 拒绝路径，`rag-research` 专用）；`:140 tool_set`/`:146 registry_snapshot`（parity 取数口）。
- `mw_common.py:340 RAG_RESEARCH_ROLES = frozenset(("spec","design","research","rag-research"))`、`:344 RAG_RESEARCH_PHASES`、`:873` 判定。**命名撞车**：这里已有一个 RAG role 叫 `design`；新类型 `design`→role `vision` 后，`type: design` 任务的 RAG role 查表键变为 `vision`，不再命中 `design` 项（改前无 `type: design`，无回归；但 target.yml 若已写 `rag.roles.design` 将不再作用于该类型）。
- `mw_common.py:1256-1275 _doctor_dispatch`（AC-010 新 issue 挂点）、`:2123-2128` summary suggestions、`:2298-2308` 文本行渲染。
- 文档面（非代码但属改动面）：`README.md:95`（4 角色清单）、`README.md:125`（`type: coding|review|research`）、`UPDATE.md:68`（role 列表）、`skills/mw-rag/SKILL.md:16`。

判定：不加 `vision` 进 `DISPATCH_ROLES` → AC-001 失败（argparse `choices`，`mw.py:5129`），且 `dispatch.yml` 出现 `vision` 即 `load_dispatch_config` 报错（`mw_common.py:241`）→ doctor 仅 suggestion、模型静默回落（**静默失效**）。不加 `design` 进 `TASK_TYPE_TO_ROLE` → `resolve_dispatch_model` 回落 `coding`（`mw_common.py:305`），派发用不到 `vision`（**静默失效**，无报错）。

### 2. TS 侧消费方清单
- `shared/dispatch-models.ts:58-68 DISPATCH_ROLE_BY_TYPE`（镜像 `TASK_TYPE_TO_ROLE`，无 `design`）；`:74 DISPATCHABLE_TYPES = ["coding","review","research","rag-research"] as const`；`:77-79 roleForTaskType`（未知→`coding`）；`:117 readRoleModel(cwd, role)`；`:166 validateModelValue`（能力门禁姊妹检查，fail-open 契约）。
- `pm/ui-bridge.ts:982-998 resolveDispatchType`：`:991-994` 用 `DISPATCHABLE_TYPES.includes`，失败文案 `Invalid type '...'. Must be one of: ${DISPATCHABLE_TYPES.join(", ")}.`；消费点 `:1194`（`dispatch_worker` 工具）、`:1594`（`/worker`）。role 消费点 `:1036`（`planDispatchFrontmatter` 选 role/读配置）、`:1272` 与 `:1648`（回显 `role:`）。
- 硬编码文案（**不改就静默失效**）：`pm/ui-bridge.ts:1146`（`dispatch_worker` 的 `type` 参数描述写死 `'coding' | 'review' | 'research'`，连 `rag-research` 都没列）、`:1554`（`/worker` USAGE）、`:1993`（`/mw model set` USAGE `roles: main, coding, review, research`）。
- `worker/worker-mode.ts:52-83 TOOL_ALLOWLISTS`（10 键）；`:88-90 isRegisteredType`；`:92-94 toolsForType`；`:101-104 activeToolsForType`；`:442-448 dispatchRefusal`（`isRegisteredType` 唯一消费点）；`:753 applyRagTools`。
- `worker/worker-mode.ts:584` `emitRagRequiredMissing` 用 `roleForTaskType`；`:719` `registerRagTools({role: roleForTaskType(meta.type)})`；`rag/block.ts:68` `roleForTaskType`；`rag/config.ts:588 RESEARCH_ROLES`（`mw_common.py:340` 的 TS 镜像，含 `"design"`）；`rag/tools.ts:387-405`（`rag-research` 专用，与 `design` 无关）。
- `shared/mw-runner.ts:380-385 DoctorJson.dispatch`（AC-010 的 TS 类型面；`models?: Record<string,string>` 无需改，除非加字段）。
- 构建产物（**不要手改**，`mw build` 重生成）：`packages/coding-agent/dist/extensions/agent-team-loop/{shared/dispatch-models.js,worker/worker-mode.js}` 与 `packages/multi-workers/dist/extensions/agent-team-loop.js:14217 DISPATCHABLE_TYPES / :16517 TOOL_ALLOWLISTS`。

判定：`enforceConductorType` 全仓 0 命中；`dispatchRefusal`（`worker-mode.ts:442`）是等价物且只对 `origin: conductor` 生效（`:443`）。不加 `design` 进 `DISPATCHABLE_TYPES` → `resolveDispatchType` `ok:false`（`:992`），PM 无法派发（**显式红**）。不加 `design` 进 `DISPATCH_ROLE_BY_TYPE` → `roleForTaskType("design")→"coding"`，派发读错角色（**静默走错**；因 `DISPATCHABLE_TYPES` 已放行，无拦截）。不加 `design` 进 `TOOL_ALLOWLISTS` → conductor-origin 任务 fail-closed 退出（`:444`），非 conductor 任务回落 `fallback`（**静默拿到全量工具**）。

### 3. 双侧 parity / golden 现状
- `test_dispatch_models.py:142-152 _TS_ROLE_BY_TYPE`：**Python 内字面量**；`:154-155 test_role_map_matches_ts_mirror` 断言 `mw_common.TASK_TYPE_TO_ROLE == 该字面量`（逐键精确相等）。→ Python 加 `design→vision` 而不同步字面量**必红**。**关键缺口**：该字面量**不读 TS 源码**，TS 单边新增不会被捕获；`agent-team-loop.test.ts:5275` 也只点名 `DISPATCH_ROLE_BY_TYPE.review` → role-map 只锁 Python 半边，**TS 单边漂移无人拦**。
- `test_dispatch_models.py:160-166 _TS_MIRROR`：prefix map，与角色/类型无关，本 key 不动。
- `autopilot/dispatch.py:71 REGISTRY` ↔ `test_autopilot_l0.py:215-230 _parse_ts_allowlists`（正则解析 TS `TOOL_ALLOWLISTS` 源文本）+ `:233 test_vc023_registry_parity`：逐类型**逐元素同序**相等（`:240-242`），键集 `:246 expected_ts_keys = set(py_reg) | {"coding","review","research","fallback"}` **精确相等**（多一个 TS 键即红）。→ 只有两侧同时加 `design` 才绿；单边加**必红**（想要的锁）。
- `test_autopilot_dispatch.py:32-35`：`set(dispatch.REGISTRY) == {roadmap-writer,phase-writer,verifier,reviewer,repair,rag-research}` **精确键集** → Python REGISTRY 加 `design` **必红**，属需同步的镜像（同 `rag-research` 先例：PM 当时接受「+1 字典项」）。
- `test_mwpp_collection_parity.py:34-59 _EXPECTED_ALLOWLISTS`（10 键冻结语料，2026-09-23）+ `:62 test_vc008_allowlist_snapshot_unchanged`：`set(parsed)==set(_EXPECTED)` 且逐键**同序**相等 → TS 表加 `design` **必红**，**需重冻语料**。
- `agent-team-loop-checkpoint-wiring.test.ts:61-84 ALLOWLIST_SNAPSHOT` + `:311-324`：测试**只遍历快照自身键**（`:313`），**无键集相等断言** → 只加生产 `TOOL_ALLOWLISTS["design"]` 而不同步快照**不会红**；`:322` 的 `types=${Object.keys(...).length}` 会停在 10（**静默失效的快照**，需人工补）。
- `agent-team-loop.test.ts:5143-5145`：`type:"deploy"` 拒绝文案断言 `toContain("coding, review, research")`——对当前 `"coding, review, research, rag-research"` 是**子串命中**；把 `"design"` 插在 `research` 前**必红**，追加末尾则继续绿。`:5162-5163` 只断言 `Invalid type 'deploy'`（不受影响）。→ `DISPATCHABLE_TYPES` 的**插入位置**被该测试间接约束。
- `agent-team-loop.test.ts:5273-5278`：只点名 `verifier`/`unknown-type`/`review`/`resolveDispatchType("pi","research")`，**不锁全集**，加 `design` 不红。`test/suite/rag-research-doc.test.ts:106-113` 断言 `toolsForType("rag-research")` 11 项 + `toContain("rag-research")`，加 `design` 不影响。

结论：**自动红（好事，单边漂移被拦）** `test_autopilot_l0.py:233`。**自动红（需同步的镜像/语料）** `test_dispatch_models.py:142-155`、`test_autopilot_dispatch.py:32`、`test_mwpp_collection_parity.py:34-62`（**需重冻**）。**不会红、需人工同步（静默失效风险）** `agent-team-loop-checkpoint-wiring.test.ts:61`、`agent-team-loop.test.ts:5145`、`pm/ui-bridge.ts` 三处文案。**role-map 的 TS 半边无锁**，`design` 必须**同时**改 `shared/dispatch-models.ts:58` 与 `mw_common.py:139`（建议 design.md 补 TS 侧断言 `roleForTaskType("design")==="vision"`）。

### 4. `design` 工具白名单建议
建议同 `coding`（UI 设计要读代码/看图、最终落 UI 代码）→ 精确 `["read","write","edit","bash","find","grep","ls"]`（与 AC-005 一致）。
- TS：`worker/worker-mode.ts:52-83` 在 `research`（`:55`）后插入 `design: ["read","write","edit","bash","find","grep","ls"],`；因含 `"write"`，`activeToolsForType`（`:101-104`）**不追加** `worker_file`（同 coding）。
- Python：`autopilot/dispatch.py:71 REGISTRY` 追加 `"design": DispatchType("design", _CODING_TOOLS, "pi", "timi", False)`（复用 `:52 _CODING_TOOLS`，与 TS 逐元素同序）；若不希望 conductor 派发则加第 7 个位置参数 `conductor_dispatchable=False`（同 `:98 rag-research` 形状）。
- 顺序锁：`test_autopilot_l0.py:240-242` 与 `test_mwpp_collection_parity.py:62` 都做**逐元素同序**比较；`test_autopilot_dispatch.py:36-46` 对每类型做 tuple 精确相等 → 白名单**元素顺序**被逐元素锁死，键的**插入顺序**不锁。

### 5. VC 候选（机器可判定，供 design.md VC 表）
1. 当 `mw_common.DISPATCH_ROLES` 被读取时，必须等于 `("main","coding","review","research","vision")`。
2. 当 `mw_common.TASK_TYPE_TO_ROLE` 被读取时，`["design"]` 必须等于 `"vision"`。
3. 当 `shared/dispatch-models.ts` 被读取时，`roleForTaskType("design")` 必须等于 `"vision"`，且 `DISPATCH_ROLE_BY_TYPE` 键集必须与 `mw_common.TASK_TYPE_TO_ROLE` 键集相等。
4. 当 `dispatch.REGISTRY["design"].tools` 被读取时，必须等于 `("read","write","edit","bash","find","grep","ls")`，且与 `TOOL_ALLOWLISTS["design"]` 逐元素同序相等。
5. 当 `resolveDispatchType("pi","design")` 被调用时，必须等于 `{ok:true, type:"design"}`。
6. 当 `resolveDispatchType("pi","vision")` 被调用时，`ok` 必须等于 `false`（角色名不得被当作类型名接受）。
7. 当 `toolsForType("design")` 与 `activeToolsForType("design")` 被调用时，两者必须相等（含 write → 不加 `worker_file`）。

### 6. 数据缺口（未确认 + 如何确认）
- `vision` 在 `DISPATCH_ROLES` 中的**位置**：未确认（`test:5145` 约束的是 `DISPATCHABLE_TYPES`，不是 `DISPATCH_ROLES`）。确认方式：PM 决策后以 VC-1 精确元组锁定。
- `design` 是否 conductor-dispatchable：未确认（spec 未写）。确认方式：决定后按 `test_autopilot_dispatch.py:56-58` 同型断言锁定。
- `RAG_RESEARCH_ROLES` 的 `"design"`（`mw_common.py:340`）与新 role `vision` 撞车是否影响真实 target.yml：未确认。确认方式：查项目 `.agenticdoc/target.yml` 的 `rag.roles` 是否有 `design:` 键。
- `rag/block.ts:68`/`mw_common.py:911` 在 `design` 类型下的 RAG 块是否逐字节不变：未确认（依赖 target.yml RAG 配置）。确认方式：AC-009 的零字节用例。
- `pm/ui-bridge.ts:1146/1554/1993` 三处文案是否有测试断言：未确认（grep 未见）。确认方式：补 design 文案测试或在 design.md 记为「无测试锁」。
- `dist/` 产物与 `npm-shrinkwrap.json` 是否需重生成：未确认。确认方式：TS 改动后跑 `mw build` + `packages/multi-workers/UPDATE.md` 的 bundle staleness 检查。

## 结论 → 决策映射
- 改动面最小集（6 处，缺一即红或静默失效）：`mw_common.py:138`、`mw_common.py:139`、`autopilot/dispatch.py:71`、`shared/dispatch-models.ts:58`、`shared/dispatch-models.ts:74`、`worker/worker-mode.ts:52`。
- 镜像测试同步集（4 处，红了说明锁在起作用，逐条人工确认后更新）：`test_dispatch_models.py:142`、`test_autopilot_dispatch.py:32`、`test_mwpp_collection_parity.py:36`（重冻）、`agent-team-loop-checkpoint-wiring.test.ts:61`（补键，否则静默失效）。
- 文案同步集（3 处 TS，无测试锁，需人工）：`pm/ui-bridge.ts:1146/1554/1993`；文档面 `README.md:95/125`、`UPDATE.md:68`。
- 门禁挂点：沿用 `shared/dispatch-models.ts:166 validateModelValue` 的 fail-open 契约与错误消息风格（RC-2/RQ-2 细化）。
- 风险提示给 design.md：role-map 的 TS 半边当前**无 parity 测试**；`DISPATCHABLE_TYPES` 插入位置受 `test:5145` 子串约束；`RAG_RESEARCH_ROLES` 的 `"design"` 与新 role `vision` 的命名撞车需说明。

[VERIFY] `mw_common.py:138` 当前为 `DISPATCH_ROLES = ("main", "coding", "review", "research")`（4 项），且 `mw.py` 的 model 命令 4 处均动态 `join(DISPATCH_ROLES)`，无硬编码角色列表
[VERIFY] `worker/worker-mode.ts:52-83` 的 `TOOL_ALLOWLISTS` 与 `autopilot/dispatch.py:71 REGISTRY` 的键集当前精确相等（10 TS 键 = 6 REGISTRY 键 + coding/review/research/fallback），由 `test_autopilot_l0.py:246` 锁死
[VERIFY] `agent-team-loop-checkpoint-wiring.test.ts:313` 只遍历 `ALLOWLIST_SNAPSHOT` 自身键，无 `set(parsed)==set(production)` 键集断言 → 生产新增类型不自动红
[VERIFY] `test_mwpp_collection_parity.py:36` 与 `test_dispatch_models.py:142` 是两份冻结字面量（前者 TS 10-key 白名单，后者 Python role-map），新增 `design`/`vision` 必然需人工重冻/更新
