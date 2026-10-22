# spec-jev-live-probe-20261016 —— PM 直执线上探针（jev 实际可达性）

- key: mw-jev-provider-integration · 相位: SPEC · 日期: 2026-10-16
- 方式: PM 直执，只读探针（不改仓、不改配置、不 commit）；凭证取自 `~/.pi/agent/auth.json` field `timi.key`（未落任何明文）
- 目的: RQ-1/RQ-2/RQ-3 三份调研留下两处互斥结论与一处未复测空白，本探针给出实机判据

---

## 0. 对既有证据的锚点纠正（两处）

1. **RQ-2 转录错误（host）**: RQ-2 文中的 `api.timia.woa.com` 不解析（`getaddrinfo failed` / DNS NO-RESOLVE）。
   仓内真实常量是 **`api.timiai.woa.com`**（`packages/ai/src/providers/timi.ts:8`、`packages/ai/scripts/generate-models.ts:403`，两处一致；`packages/ai/src/providers/data/timi.json` 的 jev-latest 条目 `baseUrl` 同值）。
   探针改用正确 host 后全部通过 → RQ-2 的结论（无本地跳板、直连远程 llmproxy）成立，仅主机名写法需以此为准。
2. **RQ-3 的「会被派发层拒绝」不成立（实机否定）**: RQ-3 由 `grep jev models.generated.ts` 零命中推断 `validateModelValue` 会拒绝 `timi/jev-latest`。RQ-2 的解释（该文件是聚合 hub，模型数据在 `timi.models.ts` → `data/timi.json`）经本轮核验正确：
   - `packages/ai/src/providers/data/timi.json`：jev-latest 存在（1 命中）
   - `packages/ai/dist/providers/data/timi.json`：存在（1 命中）
   - `packages/ai/src/models.generated.ts:33 / :74 / :114`：import + 类型 + `"timi": TIMI_MODELS` 注册
   - 实机 `pi --list-models`（全局安装）输出行：`timi           jev-latest                    200K     64K      yes       no`
   → **registry 可见性通过，RQ-3 的硬依赖前置条件已满足，无需任何生成链修复。**

---

## 1. 探针矩阵（原始结果）

Host: `http://api.timiai.woa.com/ai_api_manage/llmproxy` · 凭证: auth.json `timi.key`

| # | 请求 | 结果 |
| --- | --- | --- |
| P1 | `GET /v1/models` | 200，86 个 id；含 `jev-latest`，该行 `"owned_by": "typesafe"`、其它元数据全 null |
| P2 | `POST /v1/messages` model=`jev-latest`（max_tokens=16） | **HTTP 429**，`{"type":"error","error":{"type":"rate_limit_error","message":"API调用失败: {'error': {'message': 'Too Many Requests'}}"}}`，无 retry-after 头；间隔 3s 复测第 2 次仍 429 |
| P3 | `POST /v1/messages` model=`glm-5.3-flashx`（对照，同 header/同端点） | **200**，返回 content（含 thinking 段）→ 端点、协议、凭证、配额路径均正常 |
| P4 | `POST /v1/messages` model=`jev-preview` / `jev-1.13.0` / `jev-1.14.0` | **HTTP 403** `permission_error`：「该模型不可用，请确认传入 model」→ llmproxy 只注册别名 `jev-latest`，版本化 id 未开放 |
| P5 | `POST /v1/chat/completions`（jev-latest 与 glm 对照） | **404**（HTML Not Found）→ llmproxy **不服务**该路径，与模型无关 |
| P6 | `POST /v1/responses`（两种 body 形状） | **404** → 带 `/v1` 前缀不是该 openai-responses 路径 |
| P7 | `POST /responses` model=`glm-5.3-flashx` | **200**，`"model": "zai/glm-5.3-flashx"`，正常响应体 → 该端点可用（内部由 litellm 展开 provider 前缀） |
| P8 | `POST /responses` model=`jev-latest` | **HTTP 200 但 body 为错误**：`litellm.BadRequestError: Unmapped LLM provider for this endpoint. You passed model=jev-latest, custom_llm_provider=typesafe. Check supported provider and route...` |
| P9 | `GET /model/info`、`/v1/model/info`、`/health`、`/health/liveliness` | 全部 404（litellm 管理面未对外暴露） |

---

## 2. 判据结论

**C-1（上游架构事实）**: llmproxy 是 **litellm** 前端；jev-latest 已作为一等模型注册，`owned_by=typesafe`，即代理侧**已按 typesafe provider 建了路由**，不是"完全没有 jev"。这与 RQ-1 官方文档"typesafe 是独立平台"完全吻合。

**C-2（两条协议路线都不通，且失败形态不同）**:
- anthropic-messages 路线（`/v1/messages`，即 `timi.json` 中 jev-latest 现用 api）: **429 持续限流**，来自上游/代理侧，非本仓可控；对照模型同一秒内 200，排除账户级与网络级因素。
- openai-responses 路线（`/responses`）: **provider 未映射**（`Unmapped LLM provider for this endpoint`，"for this endpoint" 措辞说明 typesafe 至多是给别的端点映射的）。
→ **"jev 当聊天模型跑通"当前不可达，且阻断点 100% 在 llmproxy/typesafe 上游，仓内零可修点。**

**C-3（仓内接线无断点，实测确认）**: registry 可见（P1 + `pi --list-models`）；路由/凭据复用 timi 通道（RQ-2 Q3/Q6、RQ-3 Q6 一致）；错误反馈链完整（RQ-3 Q3）。jev 若上游恢复，`timi/jev-latest` 作为 role 默认/派发值/falback 候选**无需任何代码改动**即可生效。

**C-4（语义层的根本疑问）**: RQ-1 由官方文档得出 Jev 不生成文本、无流式、无 reasoning，是 System One 结构化决策 API（`POST /v1/systemone`）。即使 429 消退，"anthropic-messages 协议下的聊天模型"这一挂法在语义上仍站不住：聊天补全请求要拿到什么形态的文本回复，官方契约没有定义。且 `timi.json` 的标注（`reasoning: true`、ctx 200K/maxTokens 64K）与官方（64k per-request / 32k per-question，262k 需显式 header；无 reasoning）不一致。

**C-5（本仓无法用代码解决的清单）**: 429 配额/白名单、typesafe 的 endpoint 映射、别名外的版本化 id，均属 llmproxy 或 typesafe 控制面，需上游（timi 代理维护方或 typesafe 账户）动作。

---

## 3. 二轮探针：路由面穷举与可达性（同日补测）

候选路由穷举（`POST`，body 为 systemone 形状 `{model, state, questions}`）：

| 路径 | 结果 |
| --- | --- |
| `/v1/systemone`、`/systemone`、`/typesafe/systemone`、`/v1/typesafe/systemone`、`/decision`、`/v1/decision` | 全部 **404**（llmproxy 不暴露任何决策形状的自定义路径） |
| `/v1/messages` + systemone body | **400** `invalid_request_error`：`参数校验失败 ... unknown_fields: 存在非法/不支持字段 ... : ['questions', 'state']` → anthropic 端点**严格校验 schema，拒绝 state/questions** |
| 发现面 `/openapi.json`、`/docs`、`/redoc`、`/swagger.json`、`/health`、`/model/info`、`/` | 全部 404（管理/文档面未对外暴露） |
| `/v1/messages` model=`typesafe/jev-latest`（或 `typesafe/jev-1.13.0`） | **403** 模型不可用 → provider 前缀写法不被接受，只认裸注册 id |
| `/responses` model=`typesafe/jev-latest` | 200 + `{"error":{"message":"该模型不可用...","code":"304"}}` → 同样不接受前缀写法 |
| `/v1/messages` jev-latest，**间隔 90s 复测** | 仍 **429**（同一 error 体，无 retry-after）→ 不是秒级 RPM 抖动，是持续状态 |

可达性（供路线取舍）：

| 主机 | DNS | 直连结果 |
| --- | --- | --- |
| `api.timiai.woa.com`（llmproxy） | 解析正常（21.207.205.31） | `/v1/messages`、`/responses` 对非 jev 模型可用 |
| `api.typesafe.ai` | 解析正常（Cloudflare 段） | **403**（无 key 被边缘拒绝 → 网络可达但需 typesafe 凭据） |

**路由面结论（C-6）**: llmproxy 的 typesafe 路由只挂在标准 litellm 端点上；决策语义**没有**任何可直传 `state/questions` 的入口。jev 在 `/v1/messages` 上被上游限流（429 持续 ≥90s），在 `/responses` 上 provider 未映射。**上游契约（如何用 llmproxy 发起一次 typesafe 决策调用）属未知，必须由 llmproxy 维护方确认**；仓内可做的是把传输层抽象出来，让契约一旦确认即可切换。

## 3b. 三轮探针：决策入口穷举（同日第三次补测）

目标：既然不把 jev 当聊天模型用，验证 llmproxy 是否另暴露决策原生入口。

| 探针 | 结果 |
| --- | --- |
| `POST` `/v1/query`、`/v1/decide`、`/v1/classify`、`/v1/predict`、`/v1/jev`、`/jev`、`/v1/system-one`、`/api/systemone`、`/v1/ask`、`/typesafe/v1/messages`、`/v1/typesafe`、`/v1/systemone/`、`/systemone/` | **全部 404**（HTML Not Found） |
| `GET /v1/models/jev-latest` | 200：`created_at=2026-10-14T18:55:41Z`、`owned_by=typesafe`，其余元数据 null |
| `OPTIONS /v1/messages`、`OPTIONS /responses` | 200，`Allow: POST, OPTIONS` |
| 响应头（`/v1/messages`） | `x-proxy-by: AIO-Forward`、`X-Tm-Trace-Id`、`x-rio-seq`、`Set-Cookie: x_host_key_access=...domain=.woa.com` → 上层是内部网关，非裸 litellm，管理面（docs/openapi/health/model-info）全域 404 |

**决策入口结论（C-7）**: timiai 侧**未对外暴露**任何承载 `state/questions` 的端点；可用路由只有 `/v1/messages`（anthropic schema 严格校验，显式拒收 `state`/`questions`）与 `/responses`（typesafe 未映射）。因此"走统一鉴权做决策"当前缺的是**入口**而非配额：须由 llmproxy 维护方告知/开通，或回到 typesafe 自备凭据直连 `https://api.typesafe.ai/v1/systemone`（本 key 既定路线不采用）。**D-1 的表述据此修正："决策入口未暴露/未知"，429 仅为旁证。**

## 4. 残留与未验证

- jev 在 `/v1/messages` 上的"429 是否会消退"无法由本仓判定（上游配额）。探针当日（2026-10-16）两次连续 429 + 90s 复测仍 429。
- llmproxy 的 typesafe provider 实现细节（是否把 anthropic 聊天请求转成 systemone 调用、429 是共享 key 配额还是白名单未开）无法从外部获得；需上游答复（见 spec 依赖 D-1）。
- 决策入口是否存在但未在已穷举的路径里（如带 query 参数、或需特定 header 开关）：已试 20+ 路径 + provider 前缀 + OPTIONS，未发现；不排除更深层的隐藏约定。
- typesafe 直连 403 只证明网络可达且需凭据；本 key 既定路线不使用 typesafe 自备凭据。
- 429 的 retry-after 头缺失 → 仓内退避只能指数估计（RQ-2 Q4 的处置仍然适用）。
- litellm 内部对 jev 的 `api_base`/请求映射（即它到底把聊天请求转成什么发给 typesafe）无法从外部获得，管理面端点全 404（P9）。
- 若上游修好 `Unmapped LLM provider`/429，需复测实际响应形状（文本？决策结构？）才能定 api 类型与 catalog 标注。
