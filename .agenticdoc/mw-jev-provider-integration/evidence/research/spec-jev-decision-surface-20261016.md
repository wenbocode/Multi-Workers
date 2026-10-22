# spec: jev 决策面调研（RQ-3）——jev 进入 mw 调度/回退/反馈链的接入点

> 写面说明：本文件原定路径为 `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-decision-surface-20261016.md`，但本 worker 的运行期 write_scope 只授了 `.agenticdoc/mw-console-storm-hardening/**`，对 mw-jev-provider-integration key 目录的写入被守卫拒绝（denied: other key dir）。全文按原规格完成，落在本 key 的 evidence 镜像处；settle 时请由 PM 或持 mw-jev-provider-integration 写面的窗口原样移动到目标路径（内容无需改动，验收命令即可通过）。

- key: mw-jev-provider-integration · type: research · SPEC 相位
- 日期: 2026-10-16 · 调研只读，未改任何源码/配置；`mw-model-fallback-cli/**` 仅只读引用（active，他窗持有）
- 上下文: goal.md 第 2 条「框架需要决策的时候正确调用及有效反馈」= 模型在 conductor/launcher 的选型、回退、错误反馈三条链上行为正确

---

## Q1 选型链

**配置文件与 schema**
- 唯一配置文件是仓库根 `.mw/dispatch.yml`（不在 packages/ 下；`mw_common.dispatch_config_path` = `<project_root>/.mw/dispatch.yml`，mw_common.py:217-218）。当前实例：`models: {coding: timi/deepseek-v4.1-flash, main: timi/glm-5.3-flashx, research: timi/glm-5.3-flashx, review: timi/gpt-6.1-sol}` + 顶层 `fallback_models: {review: [timi/glm-5.3]}`（.mw/dispatch.yml:1-6）。
- schema 两层：顶层 `models`（role → 单行 `prefix/model` 字符串）+ 顶层 `fallback_models`（task type → 1..4 有序列表，见 Q2）。两键**刻意独立读取**（mw_common.py:231-236 注释）。
- role 白名单 `DISPATCH_ROLES = ("main", "coding", "review", "research", "vision")`（mw_common.py:143）；`main` 是 PM 窗口自身，其余 role 映射 worker 任务类型：`TASK_TYPE_TO_ROLE`（mw_common.py:144-156）＝ coding/phase-writer/repair/roadmap-writer→coding，review/verifier/reviewer→review，research/rag-research→research，vision→vision；未知 type 落 coding。TS 侧镜像 `DISPATCH_ROLE_BY_TYPE`（dispatch-models.ts:56-69）。
- 读取器 `load_dispatch_config`（mw_common.py:224-261）：缺文件=({},{})，坏文件返回 ({},"message") **fail-soft 不阻断派发**，launcher 降级到窗口模型/每 CLI 默认并告警一次（launcher.py:172-180）；校验只查 role 白名单与非空字符串，**不校验前缀合法性**（前缀校验在写入 CLI 与 TS 派发层，见下）。

**模型字符串 → provider+model 解析**
- 值域是 `prefix/model-id`。前缀命名空间 `MODEL_PREFIX_TO_PI_PROVIDER`（mw_common.py:127-133）：timi→pi provider "timi"、claude→anthropic、codex→openai-codex、deepseek→deepseek、zai→zai-coding-cn；CLI transport 前缀 `codex_cli/claude_cli`（mw_common.py:135-138）。TS 侧镜像 `PROVIDER_ID_TO_PREFIX`（dispatch-models.ts:29-36）——**两侧必须同步**（mw_common.py:122-123、dispatch-models.ts:25-26 注释红线）。
- 每 spawn 解析链 `resolve_dispatch_model`（mw_common.py:300-324）：task.md 显式 `model:`（原样返回，source=task）> dispatch.yml `models.<role>`（需过 `model_value_compatible` mw_common.py:282-298：provider 前缀仅适用 pi 条目、`*_cli` 前缀须匹配 cli、未知前缀跳过落下一层）> 当前窗口模型 `.mw/window-model`（`read_window_model` mw_common.py:263-271；由非 worker pi 窗口在 session_start/model_select 写入，dispatch-models.ts:100-110、314-330）> `""`（每 CLI 硬编码默认）。
- spawn 落地：launcher `_resolve_entry_model`（launcher.py:166-192）→ `_effective_entry`（launcher.py:243-278）：provider 前缀**重写 entry.provider**（跨 provider 继承主窗口模型），`*_cli` 前缀必须匹配条目 cli，bare id 保留原路由 → `_build_command`（launcher.py:1764-1811）：pi+timi 默认 `--model glm-5.3`（:1778）；direct provider（anthropic/openai-codex/deepseek/zai-coding-cn）显式 `--provider --model`，缺 model 直接 RuntimeError（:1780-1786）；codex exec 默认 `gpt-5.6-sol`（:1801）。

**conductor 的位置**：autopilot/conductor.py 的派发决策**不直接读 dispatch.yml models**——它写 task.md/队列行时 `model: ""`（conductor.py:6500；dispatch.py:962-963、1529），模型选择统一收敛在 launcher 解析链；conductor 的 L2/L3 verifier/reviewer 派发同样走 type→role 桶（dispatch.py:1346、1503）。

**非法/不可用模型 id 的失败形态（分层）**
1. CLI 写入层：`mw model set` 校验 role 白名单、`prefix/model` 形状、`KNOWN_MODEL_PREFIXES`（mw.py:3506-3521），拒绝即非零退出不写文件；vision role 另有 images 探针（mw.py:3523-3552）。
2. PM 派发层（TS）：`validateModelValue`（dispatch-models.ts:167-200）对 pi 任务按 pi model registry 校验**生效值**（显式请求或 role 默认，`planDispatchFrontmatter` ui-bridge.ts:1278-1283）：registry 中该 provider 有 id 而找不到此 id → **拒绝派发**（防 pi 把它当 custom id 静默使用，README.md:185）；未知前缀拒绝；registry 缺该 provider / 非 pi cli / CLI 前缀 → fail-open（:186-192）。调用点 ui-bridge.ts:1305、`/mw model set` 预检 ui-bridge.ts:3340。
3. launcher 层：显式 task.md `model:` 与条目 cli 不兼容 → `_effective_entry` RuntimeError 进 worker.log（launcher.py:255-270）；显式值偏离 role 默认时 launcher.log 记 `model-override` 证据行（launcher.py:216-240）。
4. worker 运行层：模型层错误 → exit 3 降级链（见 Q3）。
5. doctor：`dispatch:` 行（role=值 images=…; window model …）+ `dispatch_fallback:` 行（错误显 ERROR），mw_common.py:4460-4496。

**jev 现状结论（决策面硬依赖）**：`jev-latest` 已在 `packages/ai/src/providers/data/timi.json:1`（anthropic-messages、provider=timi、reasoning=true、input=["text"]、200K ctx）；但 `packages/ai/src/models.generated.ts` grep `jev` **零命中** → timi provider 在 registry 有其它 id，`validateModelValue` 会走 not-found 分支（dispatch-models.ts:193-199）→ **`timi/jev-latest` 作为 role 默认或显式 model 都会在 PM 派发层被拒**。jev 进入任何决策面前置依赖 = 模型进生成产物 registry（RQ-2 调研范围）。

## Q2 回退链（f551f1c90）

- 配置面：`.mw/dispatch.yml` **顶层** `fallback_models`，键是 **worker 任务类型**（`FALLBACK_TASK_TYPES` = TASK_TYPE_TO_ROLE 键集，mw_common.py:341），不是 per-role；未命中精确键回退到 role 桶（`fallback_models_for_task_type` mw_common.py:468-475）。值＝1..4 个 `prefix/model`（`FALLBACK_MAX_MODELS=4` mw_common.py:340），`*_cli` transport 前缀拒收（mw_common.py:414-419）；`main` 无 worker fallback（mw_common.py:334-339）。归一化小写+去重保首（mw_common.py:427-431）。
- 校验单一事实源 `validate_fallback_models`（mw_common.py:365-438）：所有错误带机器可读前缀 `invalid-config: `（mw_common.py:358）；`load_fallback_models`（mw_common.py:440-466）fail-soft 同 `models`：坏块＝「无备用链」，绝不阻断派发。
- 触发判据：worker 首个 error run 即 `exit 3` + `run.json.model_exhausted:true`（进程即重试单元，worker-mode.ts:2573-2578、3798-3821）；launcher `_try_model_redispatch`（launcher.py:777-880）两级收敛：
  1. **同模型进程重试**：trace.log `[MODEL_RETRY]` 计数 < `PI_WORKER_MODEL_ERR_MAX`（默认 2，0=直切；launcher.py:475-479、685-713）→ 同 `--model` 重 spawn，写 `[MODEL_RETRY] model=<m> attempt=<k>`（launcher.py:822-841）。
  2. **备用链**：按配置顺序取下一候选；候选 route/凭据预校验失败 → `[MODEL_FALLBACK-SKIP] … reason=…` 续试下一个（launcher.py:749-775、845-860）；选中 → `[MODEL_FALLBACK] from=<m> to=<n> attempt=<k>` 重 spawn（launcher.py:861-873）。
  3. 两级耗尽 → 既有 `failed` 终态，Exit Reason 透传 `model unavailable:` 链（launcher.py:873-880）。
- 状态以文件为事实源：链进度从 trace.log 的 `[MODEL_FALLBACK]`/`[MODEL_RETRY]` 推导（`_model_fallback_history` launcher.py:668-683、`_model_retry_history` launcher.py:715-741），serve 重启续跑不重置；注入面 `inject_fallback_env`（launcher.py:556-580）：`PI_WORKER_FALLBACK_MODELS`（csv 链）、`PI_WORKER_FALLBACK_INDEX`、`PI_WORKER_TRIED_MODELS`；`_fallback_chain` 剔除主模型（provider+id 去重，launcher.py:520-540）。重派是进程级重播种，不调用 setModel、不写全局设置（README.md:176）。
- 配置入口：`mw model set-fallback/clear-fallback`（mw.py:3602-3680，mw-model-fallback-cli 交付）；写经同一校验器（mw.py:3615-3627），`_model_write` 读改写保留其它顶层键（mw.py:3464-3492）；`/mw model set-fallback` 窗口转发 ui-bridge.ts:3367-3388。
- **新模型「正确调用」需配的键**：(a) `mw model set <role> <prefix/model>`（或任务级 task.md `model:`+`model-reason:`）；(b) 作为备选：`mw model set-fallback <task-type> <chain>`；(c) 仅当引入**新前缀**：两侧前缀映射 + `FALLBACK_PREFIX_TO_ROUTE`（mw_common.py:347-356）+ providers.json 路由/凭据（见 Q6）。jev 沿用 `timi/` 前缀则只需 (a)(b) 两条配置值。

## Q3 反馈链

- worker 感知：`assistantBoundaryInfo`（worker-mode.ts:4081-4090）——assistant 消息 `stopReason==="error"` + `errorMessage` 即错误边界（pi AI 层把 provider 的 4xx/5xx/流中断归一成该形状；**jev 走 anthropic-messages 协议即自动满足**）。error 边界不喂活动钟（worker-mode.ts:4066-4075）。
- 出口：`agent_settled` 的 model-error 分支（worker-mode.ts:3835-3857）先于一切 phase/success 分支：写 `[MODEL_ERR] <iso> model=<p/m> run=1 err=<≤200>` trace 行（文本单行≤200 由 `truncateModelErrText` 收敛，worker-mode.ts:4053-4060）→ `modelExhaustedExit`（worker-mode.ts:3798-3821）：run.json `model_exhausted:true` + output.md `## Exit Reason` = `model unavailable: tried=<m>(<n>),... last=<err>`（`formatModelUnavailableReason` worker-mode.ts:4092-4097）+ exit 3。
- 挂起型改判：无在飞工具的 idle 击杀，若已见错误边界或 agent 起跑后从未成功产出 assistant → 判模型可用性问题走 exit 3 进降级链（`[IDLE_KILL] … last_model_error=yes|no`，worker-mode.ts:3520-3537）；有在飞工具的真挂死保持 exit 1。
- PM 面：`isModelErrorTerminal`（pm-orchestrator.ts:708-715）双证据 OR（run.json flag / Exit Reason 前缀 `MODEL_UNAVAILABLE_PREFIX` :680）；每 key 连续 K=2 个模型错误终态（`MODEL_ERROR_STREAK_K` :684）→ `recordModelErrorTerminal`（:731-748）经单一 dispatch-alarm 通道写 autopilot ledger（`recordDispatchAlarm` :623-641，phase=dispatch-alarm），文案 `describeDispatchAlarm("model-error")`（:601-604）。终端 readback 无条件把 output.md 全文（含 Exit Reason）经 `deliverWorkerResult`/`deliverPmAlert` 注入 PM 会话并 `triggerTurn:true` 唤醒空闲 PM（pm-orchestrator.ts:1698-1731；ui-bridge.ts:188-196）；派发拒绝类告警同样 record+deliver（pm-orchestrator.ts:1974-1976）。**感知不拦截重派**（PERCEPTION ONLY，:733-737）——降级决策完全在 launcher。
- 「有效反馈」机制清单：trace 三种机器行（[MODEL_ERR]/[MODEL_RETRY]/[MODEL_FALLBACK(-SKIP)]）＋ run.json flag ＋ output.md Exit Reason ＋ autopilot ledger model-error 告警行 ＋ PM 窗口 triggerTurn 注入 ＋ doctor dispatch_fallback/credentials 行 ＋ launcher.log（spawn 失败原因/状态冲突 stderr→launcher.log，launcher.py:602-621）。
- **新模型需满足的假设**：错误必须经 pi provider adapter 以 error 边界暴露（stopReason=error+errorMessage）；anthropic-messages 协议解析已内建（jev-latest 即该 api）。即使错误被吞成挂起，idle 看门狗改判兜底（Q3 挂起型）；错误文本长度由 worker 收敛，无需 provider 保证。

## Q4 mw-model-fallback-cli spec 范围（只读 `.agenticdoc/mw-model-fallback-cli/spec.md`）

- 它做什么：把 `fallback_models` 配置面纳入与 role 默认模型同级的 CLI 通道——`mw model set-fallback/clear-fallback`（AC-001/002：逗号链按输入顺序写入、validator 单一事实源拒绝非法值）、拒绝无副作用（AC-003）、读改写保留 + 清空删键（AC-004）、`show`/`doctor` 展示兼容（AC-005）、pi 窗口 `/mw model` 薄转发（AC-006）、文档对齐（AC-007）。它**不做**降级策略/预算语义（属 mw-model-error-perception）、per-phase/per-key fallback、main 角色 fallback（spec.md §4）。
- jev 应**复用**：全部 CLI 写入口与校验器——jev 值就是 `prefix/model` 字符串，`set`/`set-fallback` 零改动可用；doctor 展示与 `dispatch_fallback` 兼容面复用。
- 边界划分（避免两 key 改同一文件冲突）：fallback-cli 拥有 `mw.py` 的 `cmd_model/_model_write/_dispatch_extra_keys`（mw.py:3441-3680）与 ui-bridge `/mw model` 转发段（ui-bridge.ts:3302-3391）。jev key 的决策面接入只允许：**A 路线（timi/ 前缀）零代码**，只有配置值；**B 路线（新前缀）触碰共享文件 `mw_common.py`（KNOWN_MODEL_PREFIXES 集合）与 `dispatch-models.ts`（镜像 map）**——这两个文件不在 fallback-cli 的修改面内（其实现面：Python 测试 + TS 3 例转发测试），无直接冲突；但它 active 中，任何对 `mw.py` cmd_model 一带的改动都必须等它 settle 后再做。

## Q5 决策时刻盘点

| # | 决策点 | 模型来源 | jev 接入所需 |
|---|---|---|---|
| 1 | PM/工具派发选模（TS `planDispatchFrontmatter`，ui-bridge.ts:1258-1339） | task.md `model:`（覆盖 role 默认需 `model-reason:`，缺理由拒派）> dispatch.yml role 默认；生效值过 registry 校验 + images 能力门 | A 路线：registry 可见（RQ-2 前置）+ 配置值；B 路线：前缀映射两侧 |
| 2 | conductor/autopilot 派发（Python） | 不选模型：task.md/队列行 model=""（conductor.py:6500；dispatch.py:962,1529），launcher 链生效 | 仅 dispatch.yml 配置值，无代码 |
| 3 | launcher spawn 解析（launcher.py:166-278、1764-1811） | resolve 链四层（Q1） | A：无；B：`_build_env` 新直连分支 + `_build_command` direct provider 列表扩名 |
| 4 | worker 同模型重试换模（launcher.py:777-880） | PI_WORKER_MODEL_ERR_MAX + fallback_models 链（trace.log 状态） | `mw model set-fallback <type> [timi/]jev-latest,…` 配置值 |
| 5 | 挂起判级 idle→模型问题 vs 通用挂死（worker-mode.ts:3520-3537） | 运行时错误边界事实 | 无（协议形状假设见 Q3） |
| 6 | PM escalation（pm-orchestrator.ts:1698-1731、731-748） | run.json/Exit Reason 证据 | 无代码（K=2 告警、triggerTurn 唤醒均为既有机制） |
| 7 | 手动切换：`/mw model`（ui-bridge.ts:3302-3391）转发 `mw model set/clear/set-fallback/clear-fallback/show`（mw.py:3495-3730）；`main` 角色窗口启动应用 `applyMainModelConfig`（dispatch-models.ts:286-312，显式 --model/settings 优先） | CLI 参数 | A：直接传 `timi/jev-latest`（`/mw model set` 预检 ui-bridge.ts:3340 同样过 registry）；B：同 #1 前缀映射 |
| 8 | doctor 体检（mw_common.py:4460-4496 + route_precheck mw_common.py:1839+） | dispatch.yml + providers.json | B：FALLBACK_PREFIX_TO_ROUTE/凭据条目补齐 |

## Q6 凭据面

- 配置：`packages/multi-workers/providers.json`（缺省镜像 `_DEFAULT_CONFIG` mw_common.py:71-109）。schema（mw_common.py:10-30）：`credentials.<name>.sources`（有序，env → file `~/.pi/agent/auth.json` 的 dotted field）＋ `providers.<route>`（port/base_url_env/api_key_env/credential）。timi 凭据链＝env `TIMI_API_KEY` → `~/.pi/agent/auth.json` 字段 `timi.key`（mw_common.py:93-95）。
- jev 走 `timi/` 前缀 → 用 timi 凭据，零改动：`_build_env` 的 pi+timi 分支（launcher.py:287-303）解析凭据注入 `TIMI_API_KEY`（+`TIMI_BASE_URL` 透传），缺凭据 spawn 即失败且原因点名缺失 source（launcher.py:78）。
- per-task 凭据隔离（mw-dispatch-reliability 交付）：`_stripped_env`（launcher.py:141-163）先剥光**所有**已声明凭据 env + `EXTRA_CREDENTIAL_VARS`（OPENAI_API_KEY/OPENAI_BASE_URL/TIMI_BASE_URL，mw_common.py:60-66）+ 各路由 base_url env，再由 `_build_env` 按解析出的 provider **只回注该路由的凭据**——worker 进程只见自己需要的 key。备用链候选同样受预校验：`_fallback_candidate_available`（launcher.py:749-775）复用 `route_precheck`（mw_common.py:1839+）查 route/凭据，缺失即 `[MODEL_FALLBACK-SKIP]`，不做网络探测。
- **jev 若为独立平台/独立 key 的额外要求**：providers.json 增 `credentials.jev`（sources 声明 env/file）+ `providers.jev`（base_url_env/api_key_env/credential）；其 env 变量名进入剥离集合（声明于 providers.json 即被 `credential_env_names` 覆盖；额外裸名单进 EXTRA_CREDENTIAL_VARS）；`FALLBACK_PREFIX_TO_ROUTE` 增 jev→路由名，否则备用链永远 skip 该候选；`_build_env` 增 pi+jev 直连分支保证只回注 jev key。A 路线（timi 前缀）以上全部自动继承。

## jev 决策面接入清单

**路线 A：jev 作为 timi 模型（`timi/jev-latest`，与 timi.json 现状一致）——推荐起步**
1. 前置（硬依赖，RQ-2 范围）：jev-latest 进入 `models.generated.ts` 生成产物；否则 PM 派发与 `/mw model set` 的 registry 校验一律拒绝（dispatch-models.ts:193-199、ui-bridge.ts:3340）。
2. 配置键：`mw model set coding|research|review timi/jev-latest`；备用链 `mw model set-fallback <task-type> timi/jev-latest,…`（≤4，禁止 `*_cli` 前缀）；或任务级 task.md `model: timi/jev-latest` + `model-reason:`。
3. 代码点：无（解析/回退/反馈/凭据全链复用 timi 通道）。
4. 验证：`mw model show`（images= 应显示 no——timi.json jev-latest input=["text"]）、`mw doctor` dispatch/dispatch_fallback 行、实际派发一单观察主模型直跑与 `[MODEL_FALLBACK]` 面行为。
5. 已知风险：typesafe.ai 429 限流（历史 mini-spec 实测）在 mw 侧无专门限流器——表现为 error 边界→exit 3→同模型重试 2 次→切备用链，符合既有收敛语义。

**路线 B：jev 作为独立 provider（新前缀 `jev/`）——仅当 typesafe.ai 非 timi 代理后端时**
1. packages/ai：provider 实现/注册/模型目录（`add-llm-provider` 流程），使 registry 可见。
2. `mw_common.py`：`MODEL_PREFIX_TO_PI_PROVIDER` + `jev→<pi provider id>`（:127-133）；`FALLBACK_PREFIX_TO_ROUTE` + jev（:347-356）；按需 `EXTRA_CREDENTIAL_VARS`（:60-66）。
3. `dispatch-models.ts`：`PROVIDER_ID_TO_PREFIX` 镜像 + jev（:29-36）——两侧同步是注释锁定的红线。
4. `providers.json`：`credentials.jev` + `providers.jev`（Q6）。
5. `launcher.py`：`_build_env` pi+jev 直连分支（隔离回注只含 jev key，:280-380 模式）；`_build_command` direct provider 列表扩名（:1780-1786）。
6. 配置与验证：同路线 A 第 2/4 步。
7. **与 mw-model-fallback-cli 的分工边界**：`mw.py` cmd_model/_model_write、ui-bridge `/mw model` 转发段归 fallback-cli（active）；jev key 不改其校验逻辑，只扩 `mw_common.py`/`dispatch-models.ts` 的值域集合与 launcher/providers.json 接线——文件不相交，但若 B 路线需要动 cmd_model 的错误文案（前缀合法清单），须待其 settle 后实施。

## 残留与未验证

- `mw doctor` 的 dispatch_fallback 行为仅读码核验（mw_common.py:4460-4496），未实机运行。
- `/mw model set` 在 `ctx.modelRegistry === undefined` 时 fail-open（dispatch-models.ts:170 直接放行）——窗口内实际是否总持有 registry 未实测。
- jev-latest 经 timi llmproxy 的 429 是否呈现为标准 anthropic-messages error 边界（依赖 pi anthropic-messages adapter 对非 JSON/429 响应的归一行为），未实测（RQ-1 的 curl 调研会覆盖协议面）。
- `main` 角色（PM 窗口自身）的模型层错误反馈面不在 worker/launcher 链内（无 fallback、无 exit 3 语义），spec 明确超范围（fallback-cli spec.md §4）；PM 窗口自身错误仅 pi 交互层可见。
- conductor verifier/reviewer 派发若未来携带显式 model（dispatch.py:1346 参数存在），其 registry 校验路径与 PM 派发的 `planDispatchFrontmatter` 是否一致未逐行核验（当前 conductor 传 ""，不触发）。

## 上下文来源

- 任务卡：`.agenticdoc/mw-jev-provider-integration/tasks/RQ3-decision-surface.md`（六问与锚点）；兄弟卡 RQ1-typesafe-docs.md / RQ2-catalog-wiring.md（只读，jev-latest 现状与 429 实测背景）
- key 状态：`.agenticdoc/mw-jev-provider-integration/pm-state.md`（init）；`f551f1c90`（git show --stat，mw-model-error-perception + mw-model-fallback-cli 交付）
- 只读 spec：`.agenticdoc/mw-model-fallback-cli/spec.md`
- Python：`packages/multi-workers/mw_common.py`、`launcher.py`、`mw.py`、`autopilot/conductor.py`、`autopilot/dispatch.py`
- TypeScript：`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`、`pm/pm-orchestrator.ts`、`pm/ui-bridge.ts`、`shared/dispatch-models.ts`
- 数据/配置：`.mw/dispatch.yml`、`packages/multi-workers/providers.json`（经 mw_common._DEFAULT_CONFIG 镜像核读）、`packages/ai/src/providers/data/timi.json`、`packages/ai/src/models.generated.ts`
- 文档：`packages/multi-workers/README.md`（模型解析链 :126-158、fallback :162-177、model-reason :183-186、env 表 :381-384）
