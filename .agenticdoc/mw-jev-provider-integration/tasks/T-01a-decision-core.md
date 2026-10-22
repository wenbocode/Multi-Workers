# T-01a — 决策客户端核心（decision.py）

- key: mw-jev-provider-integration · type: coding · W1 · timeout: 45

## 上下文

goal.md 第 2 条「框架需要决策的时候能正确调用并有效反馈」。本 key 把 Jev 作为**决策服务**接入 mw（不是聊天模型）。本任务实现**客户端核心**：契约、校验、预算、重试、fail-soft、证据行；后端实现由 T-01b 并行负责（**协议已冻结，见下**）。

必读锚点：
- `.agenticdoc/mw-jev-provider-integration/design.md`：D-001（文件划分与 CLI 锚点）、D-002（后端抽象）、D-003（**契约**：请求/响应字段与 `reason` 取值集合）、D-004（预算默认值与 8 类错误处置）、D-005（证据行与降级呈现）。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-mw-python-patterns-20261016.md`：Q2 配置 fail-soft 与 **P-003 原子写**（`console_run.py:191-195`）、Q5 测试骨架、Q6 编码卫生。
- `.agenticdoc/mw-jev-provider-integration/evidence/research/design-transport-b2-contract-20261016.md`：Q3 错误类别清单（客户端需识别的类别）。
- 现有代码先例：`packages/multi-workers/console_run.py:191-195`（原子写）、`packages/multi-workers/mw_common.py:224-252`（fail-soft 读契约）、`packages/multi-workers/launcher.py:2019-2032`（best-effort 追加一行）。

## 冻结协议（不得擅改）

```python
class DecisionBackend(Protocol):
    name: str                 # "llm-transitional" | "llmproxy-anthropic" | "direct-systemone" | "fake"
    confidence_source: str    # "model-self-report" | "api"
    def decide(self, state: object, questions: dict, cfg: "DecisionConfig") -> "BackendOutcome": ...

@dataclass
class BackendOutcome:
    available: bool
    reason: str | None        # entry-unavailable | rate-limited | upstream-error | bad-response | timeout | unsupported-question-type | disabled
    retryable: bool
    answers: dict | None      # {qid: {"value": <any>, "confidence": float | None}}
    latency_ms: int
    detail: str = ""          # 人读 ≤200 字符，禁含凭据
```

客户端 `DecisionClient.decide(state, questions) -> dict` 负责：参数校验（非法 → `DecisionInputError`）、预算、重试退避、响应归一、证据行落盘。**后端只做单次请求与类别判定**；重试与总预算归客户端。

## 要求

1. 新增 `packages/multi-workers/decision.py`，包含：`DecisionConfig`（从 `.mw/decide.json` 读取，fail-soft：缺文件=未配置、坏文件=错误串）、`DecisionInputError`、`BackendOutcome`、`DecisionBackend` 协议、`DecisionClient`、`FakeBackend`（可编程结果，供测试与调用方注入）。
2. 契约严格照 design D-003：成功响应含 `available/transport/model/confidence_source/attempts/latency_ms/answers/reason`；`reason` 取值只能用冻结集合；`confidence_source` 由后端声明传播，**不得**把 `model-self-report` 呈现成 `api`。
3. 预算默认值：`timeout_s=20`、`max_retries=2`、`max_questions=8`、`max_state_bytes=16384`、`max_tokens=1024`；全部可配；超预算立刻返回 `budget-exhausted` 语义（用冻结 reason 集合中最近者，缺则**报告并请 PM 裁决**，不要自造值）。
4. fail-soft：除 `DecisionInputError`（参数非法，供 CLI 映射 exit 2）外，**任何异常都不得外泄**——包括后端抛异常、JSON 不可解析、文件不可写，一律归一为 `available=false` + 正确 `reason`。
5. 重试：仅对 `retryable=True` 的结果重试，次数 ≤ `max_retries`，指数退避（base 2s，可配），总耗时受 `timeout_s` 约束。
6. 问题类型：wave 1 支持 `choice`（`choices` 列表）、`score`（有界整数 min/max）、`noul`（布尔）；`box` 不在 B2 能力内（B2 返回 `unsupported-question-type`，由 T-01b 实现）。校验规则：未知类型、缺必填字段、超出 `max_questions` → `DecisionInputError`。
7. 证据行：每次调用（含失败）向 `.agenticdoc/_autopilot/triage-decisions.jsonl` best-effort 追加一行 JSON，字段 = design D-005 第 1 条全集（`dp/transport/model/attempts/latency_ms/available/reason/answers/confidence/confidence_source`）；写失败只吞掉，绝不抛。
8. **凭据绝不进入任何输出/日志/证据**。
9. 测试 `packages/multi-workers/test_decide.py`（pytest，hermetic：`tmp_path` + `monkeypatch`，utf-8 显式编码）：契约字段完整性、四型问题校验、fail-soft 矩阵（后端异常/坏 JSON/超时/不可用）、预算（问题数、state 字节、重试上限）、重试次数与退避（可用 fake 时钟或极短退避）、证据行落盘与 `confidence_source` 传播。
10. **不要**创建或修改 `decision_backends.py`（T-01b 拥有）；客户端通过协议引用后端。

## 写入允许面

- `packages/multi-workers/decision.py`
- `packages/multi-workers/test_decide.py`

## 写入禁止面

- 其它一切源码/配置/文档（尤其 `decision_backends.py`、`mw.py`、`mw_common.py`）；禁止 `git add`/`commit`；禁止写入其它 key 目录

## 验收命令

```bash
cd packages/multi-workers && python -m pytest -q test_decide.py
```

## 改动历史

- 新建任务（无既存改动）。

## 交付格式

- 上述两个文件 + `report.md`（结论 / 证据 / 残留与未验证 / 上下文来源 四段）。
- 输出卫生（硬性）：每条命令 stdout ≤30 行；**前 10 次写调用内必须落出 decision.py 初版**（先骨架后补全，不要长时间只读不写）。
