# Spec: mw-vision-role

> Key: mw-vision-role
> 创建时间: 2026-09-26T16:45:00Z
> 状态: draft

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: 无 `status:` 行，三段有实内容 → 按存量项目视为已确立）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的**任务派发与模型路由**这一环——为 PM 派发面补上"按任务类型选择具备视觉输入能力的模型"这一能力，使 UI/界面设计类任务能在同一套 worker 编排下执行。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器；协调仍走文件（`_workers.parallel` / `_index.parallel` / task.md），能力门禁必须落在既有派发/启动路径上。
  - GC-2: 不修改 pi 核心；本 key 只动 mw（Python）+ agent-team-loop 扩展（TS）。
  - GC-3: 工具白名单按任务类型；新类型的白名单两侧（TS `TOOL_ALLOWLISTS` + Python `autopilot/dispatch.py` REGISTRY）必须逐元素一致。
  - GC-4: 调度配置两侧镜像（`mw_common.py` ↔ `shared/dispatch-models.ts`）必须同步，parity 测试锁死。
  - GC-5: 不新增 provider 凭证面；本 key 只使用既有 `timi` / `zai-coding-cn` 直连路由。
- 冲突：无。
- 预期收益：本 key 达成后对项目目标的具体贡献（可观察、可验证；done 时在 achieved.md 对照判定）
  - UI/界面设计类任务可以由 PM 以 `type: vision` 派发，worker 使用视觉模型，`read` 一张截图/mockup 时不再被替换为 `[Current model does not support images...]`——判定方式：真实派发一个 `images: yes` 且 `type: vision` 的 worker，其 trace 中出现图片内容块（非降级提示行）。
  - 派发面在"任务需要看图但模型看不了"时**拒绝**而非静默降级——判定方式：AC-006 的拒绝用例。
  - 该能力不改变既有纯文本任务的产物（AC-009 逐字节）。

## §1 功能概述

### 1.1 目标

当前 mw 的派发模型配置只有 4 个语义角色（`main` / `coding` / `review` / `research`），而 `.mw/dispatch.yml` 里这 4 个角色的值全部是纯文本模型（`timi/deepseek-v4.1-flash`、`timi/glm-5.3`）。pi 的 `read` 工具对 `input` 不含 `image` 的模型会把图片内容替换为一行降级提示（`packages/coding-agent/src/core/tools/read.ts:87-91`），因此做 UI/界面设计时 worker **拿不到任何视觉信息**，且失败是静默的。

本需求交付六件事：
1. 新增派发角色 `vision`（`.mw/dispatch.yml` 的 `models.vision`），承载"具备视觉输入能力的模型"这一语义；
2. 新增派发任务类型 `vision`（与角色同名：`type: vision` → 角色 `vision`），并给它一套明确的工具白名单；
3. 新增**能力门禁**：任务声明需要图片输入（或描述里引用了图片文件）而解析出的模型不支持图片输入时，派发被拒绝；无法判定能力时 fail-open（绝不发明失败）；
4. **配置期感知**：`mw model set vision <值>` 必须知道该模型能否看图（纯文本模型直接拒绝），`mw model show` / `mw doctor` 每个角色都显示 `images` 能力列。判据来自既有 `pi --list-models` 输出的 `images` 列（本机实测：`shutil.which("pi")` 有解、`pi --list-models <pattern>` rc=0、耗时约 1.2s、六列表格含 `images` 列），探针不可用时 fail-open（unknown/skip）；
5. **PM 知情面**：`vision` 类型与 `vision` 角色必须出现在 PM 会读到的文本面（`dispatch_worker` 工具描述的类型清单、`/worker` 与 `/mw model set` 的 USAGE），否则 PM 不知道该能力存在（现状 `pm/ui-bridge.ts:1146` 连 `rag-research` 都没列）；
6. **派发期自动调用**：无显式 `model:` 的任务被检测出需要图片、且其类型角色的模型看不了图、而 `vision` 角色已配置且能看图时，**自动改用 `vision` 模型**派发并留下机读来源证据（`auto-route`），而不是只在看不了图时报错。

本需求**只做视觉输入（看图）**，不做图片生成。

### 1.2 技术栈 / 语言

- Python 3（`packages/multi-workers/`：`mw.py` / `mw_common.py` / `autopilot/dispatch.py` / `launcher.py`）
- TypeScript（`packages/coding-agent/src/extensions/agent-team-loop/`：`shared/dispatch-models.ts`、`pm/ui-bridge.ts`、`worker/worker-mode.ts`）

### 1.3 核心用户场景

1. 场景 A（PM 配置视觉角色）：用户在 PM 窗口执行 `mw model set vision timi/deepseek-v4-flash-vision-exp`，配置写入 `.mw/dispatch.yml`。
2. 场景 B（PM 派发 UI 设计任务）：PM 以 `type: vision` 派发任务，task.md 引用 `docs/mockup-login.png`；launcher 解析出 `timi/deepseek-v4-flash-vision-exp`（来源 `config:vision`），worker 用 `read` 拿到真实图片内容块并据此产出 UI 代码。
3. 场景 C（门禁拦截）：PM 以 `type: vision` 派发一个引用图片的任务，但 `dispatch.yml` 的 `vision`（或显式 `model:`）指向纯文本模型 → 派发被拒绝，PM 拿到含修复串的错误消息，队列不新增条目。
4. 场景 D（兜底）：模型值无法在 registry 判定（`codex_cli/...`、registry 不可用）→ 不阻塞派发，但 worker 侧仍有兜底检查（模型确实看不了图时以机读行 + 非零退出结束，而不是跑完一个瞎猜的活）。
5. 场景 E（自动路由）：PM 派发一个 `type: coding` 任务、描述里引用 `docs/ui/login.png`、且没写 `model:`；`coding` 角色是纯文本模型而 `vision` 角色支持图片 → 派发自动使用 `vision` 模型，task.md/trace 留 `auto-route` 来源行；若 `vision` 也没配，则拒绝（场景 C）。
6. 场景 F（配置期拦截）：用户执行 `mw model set vision timi/glm-5.3`（纯文本）→ 命令非零退出并提示该模型 `images=no`，`.mw/dispatch.yml` 一字未改；加 `--force` 时跳过探针判定并写入（AC-013）。

### 1.4 范围说明（不做什么）

- 不包含：图片**生成**（`packages/ai` 的 `IMAGE_MODELS` / `openrouter-images` 接入、任何 image-gen 工具）。
- 不包含：给 PM 主窗口自动切模型（`settings.json` 有 `defaultModel` 时 `applyMainModelConfig` 本就跳过；本 key 不改变该语义）。
- 不包含：新增 provider、新增凭证、改动 `providers.json`。
- 不包含：`claude/*`（anthropic 直连）前缀的可用性修复（本机无 anthropic 凭证，属独立问题）。
- 不包含：为视觉任务调优 watchdog/预算参数。
- 不包含：给 `pi --list-models` 增加 `--json` 输出（本 key 的 Python 探针解析现有六列表格；表格解析被证明不稳定时另开 key 加 JSON 面）。
- 不包含：修复既有 `model-reason:` 只有写者没有读者、`timeout:` / `rag_*_budget*` 只有读者没有写者的空转问题（仅记录，见 RQ-3 F1）。
- 不包含：conductor（Python）侧的自动路由与能力门禁（无 registry；conductor **可以**派发 `type: vision`（AC-019），但不做内容检测/自动改道，能力判定依赖 AC-006 的 TS 侧拒绝 + AC-011 兜底）。

## §2 业务约束

### 2.1 平台 / 环境

- Windows 开发机 + Node/Python 双栈；`mw serve` 是常驻进程，Python 侧改动需重启才生效（改完必须 `/mw restart` 再验收）。
- 视觉候选模型只来自本机有凭证的 provider：`timi`、`zai-coding-cn`（`~/.pi/agent/auth.json` 的实际 key 集合）。
- 工作目录隔离：本 key 的 key 目录 `.agenticdoc/mw-vision-role/`；仓库内多窗口并行，禁止跨文件大范围改写。

### 2.2 性能指标

- 派发期能力门禁与自动路由的判定必须是**纯本地注册表查询**，不得发起网络请求：单次派发额外耗时 < 20ms（registry 已加载在内存）。
- 门禁/auto-detect 不得给未声明图片需求的任务增加任何 I/O（AC-009 的零字节约束同时是性能约束）。
- Python 侧探针（仅 `mw model set` / `mw model show` / `mw doctor` 使用）必须是**一次性子进程**：单次超时预算 ≤ 5s，超时/不可用即 fail-open（输出 unknown/skip，绝不阻塞命令），同进程内同一 key 结果可记忆化。

### 2.3 安全约束

- 不新增凭证读取路径；worker env 的凭证隔离语义（`_stripped_env`）不变。
- 门禁错误消息中不得回显任何凭证值（只回显角色名、模型值、模型 id）。

### 2.4 集成依赖

- pi 模型目录（`packages/ai`）中 `timi` provider 的 11 个 `input=["text","image"]` 模型，以及 `zai-coding-cn` 的 `glm-4.6v` / `glm-5.3-flash`。
- pi 的 `read` 工具视觉分支（`core/tools/read.ts`）与其降级提示行为。
- 既有派发链：task.md `model:` > `.mw/dispatch.yml` role > `.mw/window-model` > per-cli 默认（`mw_common.resolve_dispatch_model`）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-26T17:00:00Z，编号永不回收（用户 spec 评审通过；待确认 1/4/6/7 于此同日拍定）

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 `.mw/dispatch.yml` 已存在且未配置 `models.vision` 时，执行 `mw model set vision timi/gpt-5.6-sol` 退出码为 0，`load_dispatch_config()` 返回的 `models` 含键 `vision` 且值等于 `timi/gpt-5.6-sol`（不再报 unknown role）。 |
| AC-002 | 执行 `mw model set visionx timi/gpt-5.6-sol` 退出码非 0，且错误文本中枚举的有效角色恰好为 5 个（main, coding, review, research, vision）。 |
| AC-003 | 在 `dispatch.yml models.vision=timi/deepseek-v4-flash-vision-exp`、task.md 无 `model:` 头时，`resolve_dispatch_model(cli="pi", task_type="vision", entry_model="", config_models={...}, window_model=...)` 返回 `("timi/deepseek-v4-flash-vision-exp", "config:vision")`；task.md 带 `model: timi/glm-5.3` 时返回 `("timi/glm-5.3", "task")`。 |
| AC-004 | `resolveDispatchType("pi", "vision")` 返回 `{ok:true, type:"vision"}`；`roleForTaskType("vision")` 返回 `"vision"`；Python `TASK_TYPE_TO_ROLE["vision"] == "vision"`；两侧映射表（5 角色 + 含 `vision` 的类型集）逐项相等，parity 测试对该类型通过。 |
| AC-005 | `type: vision` 的工具白名单在 TS `TOOL_ALLOWLISTS` 与 Python `autopilot/dispatch.py` REGISTRY 中逐元素相等（同序），且等于 `["read","write","edit","bash","find","grep","ls"]`；既有 L0 parity 测试对该类型通过。 |
| AC-006 | 任务声明 `images: yes`（或描述中引用至少一个**存在**的 `.png/.jpg/.jpeg/.webp/.gif/.bmp` 文件）、且解析出的模型（显式 `model:` > `dispatch.yml` 角色）在 registry 中存在但 `input` 不含 `image` 时，派发被拒绝：返回消息含子串 `images`、`mw model set vision` 与豁免写法 `images: no`；任务目录未创建、`_workers.parallel` 行数在调用前后相等。 |
| AC-007 | 同 AC-006 条件下模型 `input` 含 `image`（如 `timi/deepseek-v4-flash-vision-exp`）时派发成功：`_workers.parallel` 新增 1 行，生成的 task.md 含 `^images: yes$`，且头部满足 `type < phase < images < model` 严格顺序。 |
| AC-008 | 模型值无法在 registry 中判定（`codex_cli/`、`claude_cli/` 前缀，或 registry 为 `undefined`，或 `cli !== "pi"`）时，`images: yes` 不导致派发失败：返回 ok，`_workers.parallel` 新增 1 行（与 `validateModelValue` 的 fail-open 契约一致）。 |
| AC-009 | 任务未声明 `images:` 头且描述未引用任何存在的图片文件时，产物与改造前逐字节一致：TS 侧 `planDispatchFrontmatter` 无 phase/model 时输出 `"type: coding\n"`；Python 侧 `render_task_md(images=None)` 与 `images=""` 与 git-HEAD 冻结渲染器同参输出三者逐字节相等；两侧均不出现 `images:` 行。 |
| AC-010 | `mw doctor` 的 dispatch 段对 `vision` 角色给出能力判定：已配置且探针判定该模型 `images=no` → 一条 **suggestion**（消息含 `mw model set vision`）且 `dispatch:` 行内该角色标注 `images=no`；支持图片 → ok 行；`pi` 探针不可用（不在 PATH / 超时 / 输出不可解析）→ skip 行（非 issue、非 error）；三种情形 doctor 退出码均为 0。[REVISED @ 2026-09-26: issue→suggestion；doctor 退出码由 `summary.healthy` 决定（`mw_common.py:2186`/`mw.py:532`），落 issues 必致退出码 1，与"三情形退出码 0"互斥；dispatch 配置问题在既有实现中一律走 suggestions（`mw_common.py:2123-2127`）] |
| AC-011 | worker 侧兜底：task.md 声明 `images: yes` 且运行模型 `ctx.model.input` 不含 `image` 时，worker 不执行任务主体：`worker.log` 出现机读行 `[IMAGE-CAP]` 且含该模型 id，output.md 落盘，进程退出码非零；检查挂 `session_start`（`worker/worker-mode.ts:668`）、复用 `dispatchRefusal` 的落盘三件套（`:626-638`）；同一次运行中未声明 `images:` 的任务正常执行。 |
| AC-012 | `packages/coding-agent` 与 `packages/multi-workers` 的相关测试与 `npm run check` 在改动后全绿；新增/修改的测试文件按仓库规则实际运行过（非仅 `--write` 假绿）。 |
| AC-013 | 配置期拒绝：`mw model set vision <value>` 经探针判定该模型 `images=no` 时退出码非 0、消息含 `images` 与替代建议，且 `.mw/dispatch.yml` 内容一字未改；判定支持图片时退出码 0 且 `load_dispatch_config()` 返回 `models.vision == <value>`；探针不可用时退出码 0 并输出一行 skip 提示（fail-open）；`mw model set vision <value> --force` 跳过探针判定直接写入（退出码 0，stdout 含已强制提示），且 `--force` 仅对 `vision` 角色生效（对其他角色传入时报错或忽略并回显）。 |
| AC-014 | PM 知情面：以下四处文本均含 `type: vision` 与角色 `vision`（grep 断言）：`dispatch_worker` 的 `type` 参数描述（`pm/ui-bridge.ts:1146`，且从该描述解析出的类型 token 集合必须等于 `DISPATCHABLE_TYPES ∪ {"codex"}`）、`/worker` USAGE（`:1554`）、`/mw model set` USAGE（`:1993`，其角色集合等于 `mw_common.DISPATCH_ROLES`）、`PARALLEL_PROTOCOL`（`pm/pm-orchestrator.ts:650-658`，含 `type: vision` 与"引用图片"语义）；`DISPATCHABLE_TYPES` 含 `vision`。 |
| AC-015 | 能力可见：`mw model show` 的每个角色行与 `mw doctor` 的 `dispatch:` 行（Python 渲染 `mw_common.py:2300-2308` 与 TS 渲染 `pm/ui-bridge.ts:1758-1765`）均含 `images=yes` / `images=no` / `images=unknown` 之一（探针不可用或角色未配置时为 `unknown`/skip，不报错），三条命令退出码均为 0。 |
| AC-016 | 自动路由（TS 派发面）：无显式 `model:`、检测到图片需求、该任务类型的角色模型不支持图片、且 `vision` 角色已配置且 registry 判定支持图片时，实际派发模型取 `vision` 角色值（来源记 `auto-route`），派发成功且 task.md 或 trace 出现机读来源证据行；`vision` 未配置或其模型不支持图片时按 AC-006 拒绝；显式 `model:` 存在时一律不改写（走 AC-006/AC-007）。 |
| AC-017 | 自动路由按能力生效而非按类型：对 `vision` 与 `review` 两个类型各跑一次 AC-016 用例，两者结论相同（同一参数化断言，`review` 角色模型为纯文本时同样被路由到 `vision`）。 |
| AC-018 | [OBSOLETE @ 2026-09-26] 原意：PM 窗口模型不支持图片而用户附加图片时输出一行提示。作废理由（RQ-5 D/E）：PM 粘贴只把路径写盘并插入编辑器（`modes/interactive/interactive-mode.ts:2822-2824`）**不产生 ImageContent 附件**，不存在"静默丢图"的钩子点；既有 `read.ts:87-91` 降级提示已覆盖该场景。该需求改由 AC-014 的 `PARALLEL_PROTOCOL` 规则承担（"图片任务用 `type: vision`"）。 |
| AC-019 | conductor 允许派发：`autopilot/dispatch.py` 的 `REGISTRY` 中 `vision` 条目 `conductor_dispatchable is True`，`dispatch(task_type="vision", ...)` 不返回 `not-conductor-dispatchable`；未知类型仍返回 `unknown-type`；`test_autopilot_dispatch.py` 的 REGISTRY 键集/白名单断言与 `test_mwpp_collection_parity.py` 的冻结语料已同步更新（重冻有据，不是放宽断言）。 |

## §4 风险与未决项

- 风险 1（契约空转，P-005 类）：`images:` 头只做解析、没有写侧 → 门禁永不触发而单测全绿。规避：AC-006/AC-007/AC-009 同时约束写侧与读侧，并要求一条"由真实派发路径产生该头的用例"。
- 风险 2（能力判定与最终模型不一致）：派发面（TS，有 registry）判定的模型可能不是 launcher 最终用的模型（window-model / per-cli 默认回退）。规避：AC-011 的 worker 侧兜底。
- 风险 3（auto-detect 误报）：任务描述里出现 `.png` 字样但实际不需要看图（如"生成的 png"）→ 误拒绝。规避：`images: no` 显式豁免优先级最高；错误消息给出显式豁免写法。
- 风险 4（模板/镜像漂移）：新增角色与类型要同时改 Python 与 TS 两侧；漏一侧会被 parity 测试锁住，但需确认 parity 语料（`test_dispatch_models.py` 的 `_TS_MIRROR`、`autopilot` L0 表）是否需要重冻。
- 风险 5（探针脆弱）：Python 探针靠解析 `pi --list-models` 的六列表格（列间是 2 空格填充；搜索参数是**模糊**过滤，同名前缀会多行）。规避：按 provider + model 两列**精确相等**取值；解析失败/超时一律 unknown + skip（fail-open）；探针只用于 `model set/show/doctor` 三个一次性命令，不进入派发热路径。
- 风险 6（动态目录）：`zai/glm-4.6v` 不在内建静态目录（`packages/ai/src/providers/data/zai-coding-cn.json` 只有 7 个模型），仅在 `~/.pi/agent/models-store.json` 动态出现，且 `--list-models` 与 `registry.find` 同源（`core/model-registry.ts:56` → `core/model-runtime.ts:392`）。本 key 的选定值 `timi/deepseek-v4-flash-vision-exp` **在静态目录内**（timi 的 models-store 为空），不受此风险影响；仅当切换到 `glm-4.6v` 时适用。规避：门禁在找不到条目时 fail-open（AC-008），文档里写明"动态目录冷时门禁不设防"。
- 风险 7（`-exp` 模型下架）：选定值带 `-exp` 后缀（实验性、`thinking=no`）。规避（已按用户知情采纳）：AC-013 的探针在模型消失/解析失败时给出 unknown + skip 非阻塞提示；AC-015 的 `mw model show` 列永久可见（人巡检可用）；不把该模型写进任何默认值或硬编码回退——一旦下架，行为退化为 fail-open（不误拒，也不再拦截）。
- 待确认 1：[已定 @ 2026-09-26，用户拍定] 任务类型名 = **`vision`**（与角色同名：`type: vision` → 角色 `vision`），白名单同 `coding`：`["read","write","edit","bash","find","grep","ls"]`。既往推荐 `design` 已废弃（RQ-1 VC-6 的命名顾虑被用户否决：同名更直观）。
- 待确认 2：门禁触发的声明形式 —— [AI 推荐，已按默认落 AC] 显式 `images: yes|no` 头 + **仅 TS 派发面**对存在图片文件的 auto-detect；`images: no` 最高优先级；拒绝消息给豁免写法。auto-detect 的 token 规则：匹配扩展名、`*?[]` 跳过、含 `://` 跳过、路径必须存在（RQ-3 F3）。
- 待确认 3：worker 侧兜底（AC-011）是否保留 —— [AI 推荐，已按默认落 AC] 保留。理由已由 RQ-2 实证：TS 派发面只校验 `requested || configured`，`window` 回退（`mw_common.py:309`）与 per-cli 默认（`launcher.py:476`）两层判不到。
- 待确认 4：[已定 @ 2026-09-26，用户拍定] `vision` 角色的实际模型值 = **`timi/deepseek-v4-flash-vision-exp`**（images=yes、200K/64K、`thinking=no`、**在静态目录内**）。本 key 不硬编码该值（由 `mw model set vision ...` 写入用户配置）；文档/测试采用此值作为夹具。备选（未采用，供后续更换）：`timi/gpt-5.6-sol`（RQ-4 独立推荐首选，images=yes + thinking=yes）> `zai/glm-5.3-flash`（1M）> `zai/glm-4.6v`（128K，动态目录）。
- 待确认 5：[已作废 @ 2026-09-26] AC-018 原设计（PM 附加图片时提示）—— RQ-5 实证：PM 粘贴只把路径写盘并插入编辑器（`interactive-mode.ts:2822-2824`）不产生 ImageContent 附件，无钩子点；既有 `read.ts:87-91` 降级提示已覆盖。该需求改由 AC-014 的 `PARALLEL_PROTOCOL` 规则承担。
- 待确认 6：[已定 @ 2026-09-26，用户拍定] `mw model set vision <纯文本模型>` **拒绝**（非零退出），并提供 `--force` 逃生口（新 flag；现状 `mw model set` 无任何 flag → 需新增 argparse 参数并写进 `/mw model set` USAGE）；对其他角色不新增限制（`--force` 对其他角色无效或不接受）。
- 待确认 7：[已定 @ 2026-09-26，用户拍定] `vision` **允许** conductor autopilot 自动派发（`conductor_dispatchable=True`，AC-019）。实证含义：conductor 的派发点全是各阶段字面量（`conductor.py:550/937/975/1007/1605/1746`），**无内容检测入口**，因此"允许"= 这些调用点可以传 `type: vision`，但 conductor 不会自己从 roadmap 文本发现 UI 子任务（需人/roadmap 显式指定）；Python 侧仍无能力门禁与自动路由（由 AC-006 的 TS 侧拒绝 + AC-011 兜底）。
- 待确认 8：`vision` 在 `DISPATCH_ROLES` 元组中的位置 —— [AI 推荐] 追加到末尾（`("main","coding","review","research","vision")`），避免动摇既有顺序断言；`DISPATCHABLE_TYPES` 中 `vision` 追加到末尾（`agent-team-loop.test.ts:5145` 的子串断言会被中间插入打破）。

### 调研已落定的实现约束（RQ-1/2/3）

- 门禁唯一挂点：`pm/ui-bridge.ts` 的 `planDispatchFrontmatter`（`ui-bridge.ts:1024/1048-1051`），必须在 `fs.mkdirSync`（`:1253`）之前返回 `{ok:false}`；registry 来自 `_context?.modelRegistry`（`:1247`），判据 `Model.input`（`packages/ai/src/types.ts:792`）。`/worker` 斜杠路径同构（`:1633/:1636`）。
- 自动路由同点实现（同一 frontmatter 计划阶段改写 model 值 + 记来源），不新增第三处写盘路径。
- 拒绝消息必须给确定性修复串（`mw model set vision ...`）与豁免写法（P-009/P-016），禁止空断言式通过。
- 两侧镜像改动最小集（6 处）：`mw_common.py:138`、`mw_common.py:139`、`autopilot/dispatch.py:71`、`shared/dispatch-models.ts:58`、`shared/dispatch-models.ts:74`、`worker/worker-mode.ts:52`；镜像测试同步集 4 处（含 `test_mwpp_collection_parity.py:36` 需重冻）；文案同步集 3 处（`pm/ui-bridge.ts:1146/1554/1993`）+ 文档面（`README.md:95/125`、`UPDATE.md:68`）。
- 已知静默失效点（必须人工补）：`agent-team-loop-checkpoint-wiring.test.ts:61-84` 的白名单快照只遍历自身键；role-map 的 **TS 半边无 parity 测试** → 必须新增 `roleForTaskType("vision") === "vision"` 断言。
- auto-route 边界（RQ-5 C，[REVISED @ 2026-09-26 by RQ-D4/D5]）：**只换模型，不改 `type:` 行**。理由：`type:` 决定工具白名单，若把 `review`/`research` 任务改判为 `vision` 会从只读变可写（隐式提权）；只换模型则白名单不变（`review` 任务仍只读 + 视觉模型）。唯一阻断条件 = 显式 `model:`（走 AC-006 拒绝，符合 AC-016 锁定字面）；原注"显式 `type:` 也阻断"与 AC-017 互斥，已作废。回显与留证：`model-reason: auto-route: <role> -> vision` + 两处回显（`pm/ui-bridge.ts:1272` / `:1648`）显示 `model-source: auto-route`。顺序：解析显式 type/model → auto-route（仅换模型）→ 能力门禁 → 回显。
- 感知面最小集（RQ-5 A）：只改 `DISPATCHABLE_TYPES` = "能派但不提示"（PM 不会主动用）；`README.md` / `UPDATE.md` / `skills/mw-rag/SKILL.md` 属**人**的感知面，扩展不注入它们，不构成 AC-014 的判据。
- 运行时能力可见面（RQ-5 B）：`mw model show`（`mw.py:3219-3233`）、`mw doctor`（`mw_common.py:2300-2308` + TS `pm/ui-bridge.ts:1758-1765`）、conductor `REGISTRY`（`autopilot/dispatch.py:71`）、`applyMainModelConfig`（`shared/dispatch-models.ts:221`）四处现状**均不展示 images** → AC-015 需同时改 Python 与 TS 两侧渲染。
- 新增 `images:` 头会命中 7 处 golden/逐字节测试（`test_rag_phase.py:36-62`、`test_autopilot_readcap_injection.py:634/655`、`agent-team-loop.test.ts:5331/5334`、`agent-team-loop-checkpoint-wiring.test.ts:470`、`rag-required.test.ts:179/189/198`、`test_autopilot_dispatch.py:75/98`、`test_autopilot_conductor_exec.py:939-960`）→ `images:` 必须条件渲染，未声明时零字节。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

（对着 `_arch_snapshot.md` §2 资产清单点名）

- **prefix 双侧 parity 锁**（`test_dispatch_models.py` `_TS_MIRROR` + `agent-team-loop.test.ts`）：本 key 新增角色 / 类型 / 映射，直接复用该锁保证两侧同步，不新建 parity 机制。
- **直连 provider 接入五步式**与 **`_stripped_env` 凭证隔离**：本 key 不新增 provider，只需复用既有 `timi` 直连分支（`launcher.py` timi/zai 模板），视觉模型无需任何路由改动。
- **`resolve_dispatch_model` 模型选择链**（`mw_common.py`）：新角色只是往 `DISPATCH_ROLES` / `TASK_TYPE_TO_ROLE` 加一项，链路本身（task.md > dispatch.yml role > window-model > per-cli 默认）零改动复用。
- **`validateModelValue` 派发期模型校验**（`shared/dispatch-models.ts`）：能力门禁是它的姊妹检查，复用同一 fail-open 契约（registry 缺失 / CLI 前缀 / 空值一律 ok）与同一错误消息风格。
- **`TOOL_ALLOWLISTS` + Python `autopilot/dispatch.py` REGISTRY 的 L0 parity 测试**：新类型的白名单直接挂进这两张表。
- **hermetic serve 测试模式**（`test_serve_doctor.py` 的 fake Popen + TEST_* 凭证）与 **`mw doctor` 段式输出范式**：AC-010 的 doctor 段直接沿用。
- **`mw model set/show/clear` CLI 范式**：新角色走同一 argparse 与 `.mw/dispatch.yml` 写入器。

### 需规避坑点

（对着 `_pitfalls.md` 点名）

- **P-005（跨语言契约字段"只有读者没有写者"）**：直接命中——`images:` 头必须同时有写侧（TS `dispatch_worker`、Python `render_task_md`）与读侧，且端到端用例必须由真实派发路径产生该头；单测里手写 fixture 不算数。
- **P-009（失败只记一行自由文本、没有预算也没有门禁 = 无界空转）**：门禁的拒绝必须是**结构化、可机读**的（拒绝事件 + 分类），且拒绝后不得进入无界重试；错误消息要给出确定性的修复串。
- **P-006（绿灯用例的日志通道可能是关闭的）**：AC-011 的机读行必须出现在**必跑命令的原始输出**里（TS 用 `process.stdout.write("[VERIFY] ...")`，Python 需 `-s`），复验时 grep 原始输出而非只看退出码。
- **P-016（空 skip / 空断言当"通过"）**：门禁的"未声明图片需求"分支必须有**真实断言**（`_workers.parallel` 行数不变、task.md 逐字节相同），不能写成"无异常即通过"。
- **P-010（用 Python 文本模式给源码打补丁会翻转换行）**：改 `mw.py` / `mw_common.py` / TS 源文件一律用编辑器精确替换，不要用 Python 读写整文件。
- **P-017（`npm run check` 会全量 `--write`，大项目时会话超时挂起）**：验证命令按仓库规则跑，输出完整留存，不裁剪。
- **P-007（review/research 无落盘通道，长报告单点故障）**：本 key 的调研卡若需要长报告，用 `coding` 类型 + 只允许写自己的 evidence 文件（本 key 的调研卡均按此派发）。
- **P-011（claim 双写分歧）**：本 key 的 phase 变更只经 `advance_phase.py`，claim 只经 `switch_key` / `update_index.py claim`。
