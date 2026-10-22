# RQ-D3 — 过渡后端（B2）可用性与结构化输出契约 + systemone schema 细节

- key: mw-jev-provider-integration · type: research · DESIGN 相位调研
- timeout: 50

## 上下文

本 key 的决策客户端需要一个**当下可用**的传输后端（B2 = 过渡后端：走 timiai 统一鉴权的现有模型产出结构化决策答案），以及一个被 D-1 阻塞的正式后端（B1 = jev）。设计需要 B2 的真实请求/响应契约与错误形态，以免把实现建在猜测上。

goal.md 第 2 条（框架需要决策的时候正确调用并有效反馈）。已知锚点：`packages/ai/src/providers/timi.ts:8`（`baseUrl = process.env.TIMI_BASE_URL ?? "http://api.timiai.woa.com/ai_api_manage/llmproxy"`）、`packages/ai/src/api/anthropic-messages.ts:556-566`（SDK maxRetries:0 + retryProviderRequest）、`packages/ai/src/utils/provider-retry.ts:24-32`（可重试状态码）。探针事实（已由 PM 实测）：`/v1/messages` 与 `/responses` 可用；`/v1/chat/completions` 与 `/v1/responses` 一律 404；两者都要 `Authorization: Bearer <TIMI_API_KEY>`（key 在 `~/.pi/agent/auth.json` 的 `timi.key`）。

## 审计目标（调研问题）

- Q1 `/v1/messages` + `glm-5.3-flashx` 的实际请求/响应契约：可用字段（`system`/`max_tokens`/`temperature`/`tools`/`tool_choice` 是否被接受）、响应块结构（`thinking` 段与 `text` 段、`stop_reason`、`usage`）、非流式与流式差异。**允许发起最多 3 次真实调用**（每次 `max_tokens ≤ 64`），把请求体与响应体（脱敏、截断 ≤400 字符）记为证据。
- Q2 强制结构化 JSON 的可用路径：该端点上 `tools` + `tool_choice`（强制工具调用）是否可用、`response_format` 之类的字段是否被接受、纯提示词约束的可靠性；给出推荐做法与依据（实测优先，其次仓内既有实现 `packages/ai/src/api/timi-responses.ts`）。
- Q3 错误形态归一：429 / 5xx / 超时 / 非 JSON 响应在该端点上的实际返回体与状态码；仓内既有归一处理位置（`provider-retry.ts` / `utils/retry.ts`）；给出"客户端应识别的错误类别清单"。
- Q4 `/responses` 作为备选承载：实测其请求/响应形状（含 `zai/glm-5.3-flashx` 这类内部 model 回填现象）与 `/v1/messages` 的取舍（哪个更适合承载 `state`+`questions` 的结构化问答）。
- Q5 systemone 官方 schema 细节：`choice` / `score` / `noul` / `box` 四种 question 的字段定义、`answers` 的响应形状、`confidence` 语义与取值范围、官方错误码。用 `curl.exe -s -L https://docs.typesafe.ai/<path>.md` 取纯文本（Mintlify 支持 `<path>.md`），逐条摘录并给 URL。
- Q6 结论：给出 B2 的**最小可行请求模板**（含 system 提示、问题编码方式、JSON 输出约定、解析与校验规则）与**置信度获取方式的局限**（模型自报 ≠ 校准），以及 B1（jev）一旦可用时的接口对齐点。

## 唯一证据文件

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-transport-b2-contract-20261016.md`（新建，全文中文，每条结论附证据：实测记录或 文件:行号 或 URL）

## 写入允许面

- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-transport-b2-contract-20261016.md`

## 写入禁止面

- 一切源码/配置；禁止 git add/commit；禁止写入其它 key 目录；**禁止把 API key 写入任何文件或 stdout**（输出里只允许出现 `key_present=True/False`）

## 验收命令

```bash
python -c "import pathlib; t=pathlib.Path(r'H:\git\Multi-Workers\.agenticdoc\mw-jev-provider-integration\evidence\research\design-transport-b2-contract-20261016.md').read_text(encoding='utf-8'); print('bytes:',len(t)); print('Q-answered:', sum(1 for q in ['Q1','Q2','Q3','Q4','Q5','Q6'] if q in t)); print('key_leak:', 'sk-' in t or len([1 for line in t.splitlines() if 'timi.key' in line and len(line)>80])>0)"
```

## 交付格式

- 证据文件：六问逐条结论（实测记录原文脱敏截断）+ 「B2 最小可行请求模板」+ 「错误类别清单」+ 「置信度局限声明」。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；实测脚本落盘到临时文件再跑，不要内联多行。
