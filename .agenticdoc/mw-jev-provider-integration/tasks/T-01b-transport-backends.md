# T-01b — 传输后端与诊断探针（decision_backends.py）

- key: mw-jev-provider-integration · type: coding · W1 · timeout: 45

## 上下文

goal.md 第 2 条。本任务实现决策客户端的**传输后端**与**诊断探针**逻辑：B2（当下可用，默认）、B1（受 D-1 阻塞）、B3（保留）。客户端核心由 T-01a 并行实现；**协议已冻结，见下**，两边独立按签名写、不互相读代码。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/design.md`：D-002（三后端表 + **B2 请求模板 + 解析规则 + 禁止字段**）、D-004（错误类别处置）、D-005（降级呈现）。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-transport-b2-contract-20261016.md`：**Q1/Q2/Q3/Q6 是 B2 的实测契约**（`tools`+`tool_choice` 强制工具调用可用、`response_format` 被 400 拒、`/responses` 不推荐、8 类错误、解析必须只认 `tool_use` 块）。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/spec-jev-live-probe-20261016.md`：llmproxy 现状（决策形状路径全 404、`/v1/messages`+jev 429、`/responses` unmapped）——B1 的 `entry-unavailable` 与 probe 矩阵的事实依据。
- 现有代码先例：`packages/ai/src/providers/timi.ts:8`（baseUrl 默认值 `http://api.timiai.woa.com/ai_api_manage/llmproxy`）、`packages/ai/src/utils/provider-retry.ts:23-35`（可重试状态码）。

## 冻结协议（不得擅改）

```python
class DecisionBackend(Protocol):
    name: str                 # "llm-transitional" | "llmproxy-anthropic" | "direct-systemone"
    confidence_source: str    # "model-self-report" | "api"
    def decide(self, state: object, questions: dict, cfg: "DecisionConfig") -> "BackendOutcome": ...

@dataclass
class BackendOutcome:
    available: bool
    reason: str | None        # entry-unavailable | rate-limited | upstream-error | bad-response | timeout | unsupported-question-type | disabled
    retryable: bool
    answers: dict | None      # {qid: {"value": <any>, "confidence": float | None}}
    latency_ms: int
    detail: str = ""
```

- 后端**单次请求**，不做重试（重试归客户端）；`decision.py` 的类型由 T-01a 提供，本任务**只从它 import**（若尚未就绪，按上述签名写并在 report 标注"待 T-01a 合并后联调"）。

## 要求

1. 新增 `packages/multi-workers/decision_backends.py`：
   - `LLMTransitionalBackend`（B2，`confidence_source="model-self-report"`）：POST `{base}/v1/messages`，`Authorization: Bearer <TIMI_API_KEY>`，`anthropic-version: 2023-06-01`；body 照 design D-002 模板（`tools` + `tool_choice` 强制 `submit_decision`，属性名 = question id）；**禁带** `response_format`/`state`/`questions`/`store`；解析只看 `type=="tool_use"` 块（忽略 thinking/text）；`choice→enum`、`score→integer(min/max)`、`noul→boolean`；`box` → `unsupported-question-type`（不可重试）。
   - `LLMProxyAnthropicBackend`（B1，`confidence_source="api"`）：**当前必须返回 `entry-unavailable`**（不发起请求或仅按配置探测），并在 detail 里写明依据（决策入口未暴露）；保留可配置 endpoint/编码位以便 D-1 解除后实现。
   - `DirectSystemOneBackend`（B3，`confidence_source="api"`）：官方 `POST /v1/systemone` 形状（`state`+`questions`→`answers`），凭据 `TYPESAFE_API_KEY` **未交付**：未配置凭据时返回 `entry-unavailable`。
   - `probe_matrix(cfg) -> list[dict]`：对候选端点/请求形状逐一探测并返回 `{target, method, path, status, verdict}`（不打印/不落 key）；至少覆盖：`/v1/messages`（B2 模型 + jev）、`/responses`（B2 模型 + jev）、`/v1/chat/completions`、`/v1/systemone` 等（见上面证据里的现状矩阵）。
2. 凭据解析顺序与环境一致：env `TIMI_API_KEY` → `~/.pi/agent/auth.json` 的 `timi.key`；**绝不打印、绝不写盘、绝不进错误文本**（错误文本按 ≤200 字符截断）。
3. 错误分类严格照 design D-004 的 8 类：400/403/404（可能是 HTML，先看 content-type）→ 不可重试；429/5xx/超时/连接错 → 可重试；**HTTP 200 但 body 含 `error` 字段或 `litellm.*Error` 文本** → 必须解析 body 判定；成功体非 JSON → 协议错误；强制 `tool_choice` 下无 `tool_use` 块 → 先 text 回退（解析 text 块 JSON），再失败 `bad-response`。
4. 超时由 `cfg.timeout_s` 控制（单次请求级）。
5. 测试 `packages/multi-workers/test_decide_backends.py`（pytest，hermetic）：用 `monkeypatch` 替掉 HTTP 调用，覆盖——成功 tool_use 解析（含 thinking/text 干扰块）、200-含-error 体、429→`rate-limited` 可重试、403→不可重试、404-HTML→不可重试、缺 tool_use 的 text 回退、`box`→`unsupported-question-type`、B1/B3 的 `entry-unavailable`、probe 矩阵形状。**不得**在测试里发真实网络请求。
6. 真实链路冒烟（可选，1 次）：允许你自己跑一次 `LLMTransitionalBackend.decide` 真实调用作为证据（`max_tokens ≤ 128`），结果摘要（≤30 行、无 key）写进 report；若网络不可用，如实记录，不要反复试。

## 写入允许面

- `packages/multi-workers/decision_backends.py`
- `packages/multi-workers/test_decide_backends.py`

## 写入禁止面

- 其它一切源码/配置/文档（尤其 `decision.py`、`mw.py`、`mw_common.py`）；禁止 `git add`/`commit`；禁止写入其它 key 目录；**禁止把任何 API key 写入文件或 stdout**

## 验收命令

```bash
cd packages/multi-workers && python -m pytest -q test_decide_backends.py
```

## 改动历史

- 新建任务（无既存改动）。

## 交付格式

- 上述两个文件 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；实测脚本落盘临时文件再跑；**前 10 次写调用内必须落出 decision_backends.py 初版**。
