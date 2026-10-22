# spec-jev-catalog-wiring-20261016

> **落盘位置说明（PM 请读）**：任务卡 write_face 指定 `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-catalog-wiring-20261016.md`，但运行期写面守卫以任务头 write_scope（mw-console-storm-hardening）执行，对该路径返回 `[TOOL_ERR] denied: other key dir`（block 已发生在 worker_file 层，符合 mw-write-surface v1 越界后果）。本文件为同内容落盘于本 key 的 evidence 树；PM 可用一条 copy 命令移到契约路径后删除本文件。

RQ-2（mw-jev-provider-integration / research，执行体 jev-rq2-catalog-wiring）：仓内目录与接线调研。只读，未改动任何源码/配置。

## 0. 方法

- 逐文件核读生成链（generate-models.ts / models.generated.ts / timi.models.ts / data/timi.json / dist）、运行时注册（providers/all.ts / timi.ts / model-runtime.ts）、mw 侧模型面（dispatch-models.ts / mw.py cmd_model / mw_common 探针）、路由面（providers.json / launcher.py / mw.py serve / proxy_multi.py）、错误面（provider-retry.ts / utils/retry.ts / agent-session.ts / worker-mode.ts）。
- 历史证据：`.agenticdoc/mw-timi-models-add/mini-spec.md`（batch 2：jev-latest 等 4 模型入库 + 429/unmapped 实测）、`.agenticdoc/mw-provider-routing/design.md`（直连/代理路由语义）。
- 输出卫生：全程每命令 stdout ≤30 行。

## Q1 models.generated.ts 生成链与 jev「缺席」

**结论：grep 'jev' 在 models.generated.ts 零命中是结构性的，不是断点。该文件是纯聚合 hub（122 行，无内联模型数据），模型数据在 data/*.json 分片里；jev-latest 在生成源、data json、dist 三层都在。**

生成链（自上而下）：

1. 源头数组：`packages/ai/scripts/generate-models.ts:424` `const TIMI_MODELS: Model<Api>[] = [...]`，jev-latest 条目在 `generate-models.ts:724-736`（api=anthropic-messages，baseUrl=TIMI_BASE_URL，reasoning=true，input=[text]，零成本，200K/64K，TIMI_ANTHROPIC_COMPAT）。
2. 常量：`generate-models.ts:403` TIMI_BASE_URL、`:404-409` TIMI_ZERO_COST、`:410-418` TIMI_RESPONSES_COMPAT、`:419-423` TIMI_ANTHROPIC_COMPAT。
3. 汇入总表：`generate-models.ts:3099` `allModels.push(...TIMI_MODELS)`（在 compat 元数据循环之后 push，timi 的 compat 字段为字面量直填）。timi 是唯一不走 models.dev 抓取（`generate-models.ts:1566` fetch models.dev/api.json）的硬编码 provider。
4. 分组写盘：`generate-models.ts:3102-3120` 按 provider/modelId 分组去重 → `:3153-3173` staging + `data/<providerId>.json`（`:3165`）+ `.manifest.json`（`:3170-3173`）。
5. 分片 wrapper：`generate-models.ts:3203-3206` 生成 `providers/timi.models.ts`：`import values from "./data/timi.json"` + `flattenModelCatalog`（实现在 `packages/ai/src/model-catalog.ts:22-27`，把 {api→{id→model}} 摊平成 {id→model}）。
6. 聚合 hub：`packages/ai/src/models.generated.ts:33` `import { TIMI_MODELS } from "./providers/timi.models.ts"`；`:74` 类型行、`:114` 注册行 `"timi": TIMI_MODELS`。全文件 122 行只有 import + MODELS 注册表，没有任何模型字面量 → **jev 零命中是必然**。

**为什么 jev-latest「在生成产物里」其实存在**：实测 `data/timi.json` 27 个模型（anthropic-messages 21 + openai-responses 6），jev-latest 在 anthropic-messages 组；`dist/providers/data/timi.json` 同步含 jev-latest（dist 27 条，与 src 一致，非过期）。batch 2 已重跑生成（mini-spec Result：timi 23→27，AC-001 27 行通过）。

## Q2 模型可见性链路逐层

**各层数据源与 jev-latest 可见性：三层全部走同一注册表（pi-ai 内置目录），目录层可见；/mw model 层未配置任何角色默认值（可 set，非不可见）。**

- **层 1 `pi --list-models`**（任务问句中的 `/mw --list-models` 在 ui-bridge 中无此旗标；mw 侧探测用的就是 `pi --list-models`，`packages/multi-workers/mw_common.py:1766-1772`）：数据源 = `packages/coding-agent/src/cli/list-models.ts:33-35` `modelRuntime.getAvailable()` ← `packages/coding-agent/src/core/model-runtime.ts:181-187` `builtinProviderCatalog.builtinProviders()` ← `packages/ai/src/providers/all.ts` MODELS（`all.ts:2` import models.generated.ts）→ timi.models.ts → data/timi.json。getAvailable 按已配置凭证过滤；timi 凭证链 = env TIMI_API_KEY → `~/.pi/agent/auth.json` field `timi.key`（`providers/timi.ts:9` envApiKeyAuth；`packages/multi-workers/providers.json` credentials.timi）。**jev-latest：可见**（batch 2 AC-001 实测 27 行；dist 未过期）。
- **层 2 窗口模型列表（/model 选择器）**：同一 ModelRegistry/ModelRuntime（`packages/coding-agent/src/core/model-registry.ts:48-58` getAll/find 直通 runtime）。**jev-latest：可选**——mini-spec 记录 2026-10-15 11:43 窗口模型曾设为 `timi/jev-latest`（.mw/window-model 机制，`packages/coding-agent/src/extensions/agent-team-loop/shared/dispatch-models.ts:100-113` recordWindowModel 写 `.mw/window-model`，last writer wins）；当前仓内 `.mw/window-model` = `timi/deepseek-v4.1-flash`。
- **层 3 `/mw model`**：TS 侧薄封装（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3301-3384` runMwModelCommand）调 Python `mw model`（`packages/multi-workers/mw.py:3495` cmd_model）。数据源 = `.mw/dispatch.yml` 的 `models:` 角色映射（`mw.py:3684-3706` show 读 load_dispatch_config + read_window_model）+ `.mw/window-model`。set 校验：角色（mw.py:3504 DISPATCH_ROLES）、prefix/model 格式（:3511-3517）、prefix 白名单（:3519 KNOWN_MODEL_PREFIXES = `mw_common.py:139`，来自 MODEL_PREFIX_TO_PI_PROVIDER `mw_common.py:127-133`）、vision 图像探针（:3540 model_images → pi --list-models 快照解析，`mw_common.py:1709-1727,1747-1786`）。**jev-latest：未配置进任何角色**（当前 `.mw/dispatch.yml`：models = coding timi/deepseek-v4.1-flash、main/research timi/glm-5.3-flashx、review timi/gpt-6.1-sol；fallback_models.review = timi/glm-5.3），但值合法可 set。
- 派发时校验：`dispatch-models.ts:167-200` validateModelValue 对 pi 任务按注册表校验 model id，未知 timi id 在派发口即拒绝（防 buildFallbackModel 静默裸用）。
- 解析优先级：task.md `model:` > .mw/dispatch.yml 角色 > .mw/window-model > per-cli 默认（`packages/multi-workers/launcher.py:171`；`mw.py:3496-3498`；timi 无显式 model 时默认 glm-5.3，`launcher.py:1778`）。

## Q3 provider 架构与直连/代理路由判定

**结论：pi-ai 的 provider = createProvider(baseUrl + api 映射 + models)；「直连 vs 代理」判定在 providers.json 的 port 字段 + launcher._build_env 分支 + serve 的 proxy spawn 过滤。jev-latest 走 timi 直连。**

- provider 注册：`packages/ai/src/models.ts:762` createProvider；`packages/ai/src/providers/all.ts` `builtinProviders()` 静态注册全部内置 provider（含 timiProvider；`getBuiltinModel/getBuiltinModels` 直读 MODELS）。
- api 类型映射：`packages/ai/src/providers/timi.ts:14-15` anthropic-messages → anthropicMessagesApi()（请求层 `packages/ai/src/api/anthropic-messages.ts:556-566` SDK maxRetries:0 + retryProviderRequest），openai-responses → timiResponsesApi()（`packages/ai/src/api/timi-responses.ts:88-96`，timii 专属净化：删 store、清空 tool description、默认 maxRetries=8）。
- baseUrl 解析：生成时逐模型钉死 TIMI_BASE_URL（generate-models.ts:403,728）；运行时 provider 工厂再覆写 `process.env.TIMI_BASE_URL ?? "http://api.timiai.woa.com/ai_api_manage/llmproxy"`（`providers/timi.ts:8-9`）——llmproxy 是**远程**多路代理，pi 直接连它，无本地跳板。
- 本地代理位置：`packages/multi-workers/proxy_multi.py`（timi-proxy-cli LocalProxyServer，:17-27,:76 起）只服务带 port 的 CLI 路由（claude 7001 / claude-cli 7003 / deepseek 7004）。
- 判定代码：
  - `providers.json`：port 有 = 代理路由（claude/claude-cli/deepseek），无 port = 直连（timi、zai-coding-cn）。
  - `launcher.py:291-306` pi+timi 直连分支（注入 TIMI_API_KEY，TIMI_BASE_URL 透传）；`:308-324` zai 直连；`:326-333` codex 原生；`:335-356` anthropic/deepseek 直连（可选网关透传）。
  - serve 侧 proxy spawn：`mw.py:354-363` 只为「available 且带 port」的路由起 proxy_multi；纯直连凭证则跳过（mw-provider-routing design D-004、VC-008）。
- jev-latest 路由：prefix `timi`（mw_common.py:128）→ task.md `model: timi/jev-latest` → `pi --provider timi --model jev-latest`（launcher.py:1777-1778）→ 直连 llmproxy，凭证=TIMI_API_KEY。

## Q4 jev-latest 的 429 现状与重试处理

**结论：429 是 llmproxy 服务端限流（anthropic /v1/messages 协议的 jev 路由），仓内无 jev 专属限流处理；pi 侧把它当通用可重试错误逐层消化。**

- 服务端现状（历史实测，`.agenticdoc/mw-timi-models-add/mini-spec.md`）：anthropic `/v1/messages` 持续 429；openai `/responses` 返回 "Unmapped LLM provider"（llmproxy 未给 jev 配 openai 协议映射 → 判 anthropic-messages 系）。本调研只读，未复测。
- HTTP 层：anthropic-messages SDK maxRetries:0 + retryProviderRequest（anthropic-messages.ts:557-566）；429 属可重试状态码且尊重 retry-after（`packages/ai/src/utils/provider-retry.ts:24-32`、retry-after 处理 `:73-92`），但 `maxRetries = options.maxRetries ?? 0` → 默认**零 HTTP 层重试**，除非 settings `retry.provider.maxRetries` 配置（`packages/coding-agent/src/core/settings-manager.ts:841-843`；`sdk.ts:316` options 优先）。注意 timiResponsesApi 的 maxRetries=8 默认（timi-responses.ts:34）只覆盖 openai-responses 路径，**不覆盖 jev 的 anthropic-messages 路径**。
- turn 层：agent-session 自动重试——错误文本模式匹配，「429」「rate.?limit」「too many requests」可重试（`packages/ai/src/utils/retry.ts:26-38,230-239`），quota/billing 类不可重试（`:7-24`）；预算默认 enabled / maxRetries=3 / baseDelayMs=2000 指数退避（settings-manager.ts:29-34 + getRetrySettings :818-824；`agent-session.ts:2681-2711` _prepareRetry）。
- mw 层（model fallback）：worker 错误 settle → 记 [MODEL_ERR] 证据 → `modelExhaustedExit` exit 3（`packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3786-3815`，run_state.model_exhausted=true）；launcher 数 trace.log 的 `[MODEL_RETRY] model=<m> attempt=<k>`（launcher.py:478-482），同模型重试上限 PI_WORKER_MODEL_ERR_MAX 默认 2（launcher.py:473-477,685-698），耗尽后走 dispatch.yml `fallback_models` 链 `_try_model_redispatch`（launcher.py:556-565,777,652）。
- 反馈落点：exit 3 + model_exhausted 旗标 → PM 轮询可见（worker-mode.ts:3796-3798）；launcher 记录 redispatch 历史（launcher.py:668,716）。

## Q5 timi.json 维护规则

**结论：脚本生成，不手编。唯一事实源是 generate-models.ts 的 TIMI_MODELS 硬编码数组；加新模型的标准动作 = 改数组 → npm run generate-models → 重建 dist + check。**

- timi.json 为 gitignored 生成物（`git check-ignore` 通过；generate-models.ts:3246 注释 "Generated JSON model values under src/providers/data/"）。手编会在下次生成时被覆盖。
- batch 2 标准动作实录（mini-spec）：TIMI_MODELS +4 → `npm run generate-models`（data/timi.json 23→27 + 分片/聚合/manifest 重生成，staging 校验 generate-models.ts:3153-3174）→ pi-ai dist 重建 → `npm run check` → CHANGELOG [Unreleased]。
- 遗留问题：jev-latest 的 reasoning=true / input=text / 200K/64K 是 429 期间的保守默认，未经真实响应复核（mini-spec 探针说明）；新 id 未进 dispatch.yml 角色/fallback 默认；`.mw/dispatch.yml` 按 mini-spec 决议不动。

## Q6 新 provider 标准面（对照 docs/custom-provider.md、docs/models.md）

**前提核实：仓内无 "typesafe" 平台任何引用（全仓 grep 仅命中 vendored pip 的无关注释 "THIS IS NOT A TYPESAFE BRANCH"，urllib3 _collections.py:362）。typesafe.ai 若为独立平台，属全新接入，仓内标准面按介入深度分档：**

1. **配置面（零代码）**：`~/.pi/agent/models.json` providers 段（`packages/coding-agent/docs/models.md:3-15` 最小例、:85-105 全例）；api 四选一：openai-completions / openai-responses / anthropic-messages / google-generative-ai（models.md "Supported APIs" 表）；打开 /model 时热加载，免重启。compat 可 provider 级或 model 级（models.md:33-51）。
2. **扩展面（pi.registerProvider）**：`docs/custom-provider.md:20-100`——完整 Provider（自定义 auth/refresh/streaming，async factory 支持远程模型发现，factory 完成前启动阻塞，保证 --list-models 可见）或 legacy provider-config 形式（baseUrl/headers 覆写既有 provider 不动 models，:70-85）。
3. **内置目录面（timi 模式，需发版）**：`packages/ai/src/providers/<id>.ts` 工厂 + api 实现 → generate-models.ts 加常量与数组 → `providers/all.ts` 注册 → env-api-keys → pi-ai dist 重建。
4. **mw worker 可达性（独立平台要让 worker 用，必须加）**：providers.json credentials + providers 路由（port 或无 port 直连）；`mw_common.py:127-133` MODEL_PREFIX_TO_PI_PROVIDER 与 `dispatch-models.ts:29-36` PROVIDER_ID_TO_PREFIX 双侧互逆同步（mw-provider-routing design §7 VC-010）；launcher._build_env 直连分支（launcher.py:291-356 模式）；`_build_command` 直连元组（launcher.py:1782）。缺 mw 接线时仅 PM 窗口可用，派发校验会因 prefix 白名单拒绝。

## 「jev 跑通的断点清单」（按层）

| 层 | 判定 | 证据 |
| --- | --- | --- |
| 目录层 | **通过** | TIMI_MODELS 含 jev-latest（generate-models.ts:724-736）；data/timi.json anthropic-messages 组含 jev-latest（27 模型 = 21 anthropic + 6 responses）；dist 同步含 jev-latest |
| 生成层 | **通过**（models.generated.ts 零 jev 是聚合 hub 结构使然，非断点） | models.generated.ts:33,74,114 纯 import 注册；数据在 timi.models.ts → data/timi.json；batch 2 已重跑生成（mini-spec AC-001/AC-003 通过） |
| 路由层 | **通过** | timi 无 port 直连（providers.json）；launcher.py:291-306 注入 TIMI_API_KEY；launcher.py:1777-1778 命令 `pi --provider timi --model jev-latest`；prefix 合法（mw_common.py:127-139）；窗口曾成功选中 timi/jev-latest（mini-spec） |
| 调用层 | **断点（唯一）** | llmproxy 服务端：anthropic /v1/messages 对 jev 持续 429（限流），openai /responses "Unmapped LLM provider"（无 openai 协议映射）。仓内补偿有限：anthropic-messages 路径 HTTP 层默认 0 重试（provider-retry maxRetries ?? 0），turn 层 3 次指数退避只能吸收瞬时 429，持续性 429 必然走到错误 settle |
| 反馈层 | **通过，但兜底薄弱** | 错误链完整：pi 自动重试（retry.ts:26-38）→ worker [MODEL_ERR] + exit 3 + model_exhausted 旗标（worker-mode.ts:3786-3815）→ launcher [MODEL_RETRY] ×2 → fallback 链。薄弱点：dispatch.yml fallback_models 仅 review 配了链（timi/glm-5.3），coding/research 无兜底——jev 若被用作 coding/research 任务模型且 429 持续，重试耗尽即 model-exhausted 终态，无链可落 |

**一句话**：仓内接线无断点，jev-latest 从目录到派发命令全部就绪；跑不通的只有 llmproxy 服务端 429，且仓内对持续性 429 的兜底（coding/research 无 fallback 链 + anthropic-messages HTTP 层零重试）偏薄。

## 残留与未验证

- 429 是否已消退：未复测（本任务只读、不发起真实 LLM 调用）；以 mini-spec 2026-10-15 实测为最新证据。
- jev-latest 的 reasoning/input/contextWindow/maxTokens 真实参数：未验证（429 期间保守默认）。
- 「/mw --list-models」旗标：ui-bridge 无此子命令；已按 `pi --list-models`（mw 探针同源）作答，若 PM 语境另有所指需澄清。
- timiResponsesApi maxRetries=8 与 agent-session 3 次重试的叠加行为（openai-responses 路径）未实测，与本调研主链（anthropic-messages）无关。
