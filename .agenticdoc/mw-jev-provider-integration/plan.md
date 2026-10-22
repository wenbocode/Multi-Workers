# Plan: mw-jev-provider-integration

## §0 并行性分析（先于拆分）

| 维度 | 结论 |
| --- | --- |
| 任务可并行性 | 高：Python 新文件（decision*.py）与 TS 接入面（ui-bridge/pm-orchestrator）互不交叠；同一个 Python 模块内部才需串行 |
| 冻结面（拆分前提） | **后端协议**（见 §1 的 `DecisionBackend` / `BackendOutcome`）与**CLI/JSON 契约**（design D-003）在拆分前冻结；两份实现各自按签名写，不互相读代码 |
| 共享热文件 | `mw.py`（+cmd_decide 与一行注册；`_goal_gate_install` 段属他 key）、`mw_common.py`（+doctor 行）、`CHANGELOG.md`（追加自己段落）、`ui-bridge.ts`（`:1257`/`:2491` 段；`:3302-3391` 属他 key）、`pm-orchestrator.ts`（+1 kind + 文案） |
| 冲突对策 | 每束只写自己的文件/段落；`mw.py` 与 `mw_common.py` 的改动集中在单个任务（T-02）内一次完成，避免多束同时改同一文件；提交遇混合文件走索引级重建 |
| 并行度 | W1 两束并行（Python 核心 / Python 后端），W2、W3、W4 各一束（有依赖）；同一台机器最多 2 个 coding worker 同时跑 |

## §1 冻结接口（拆分前提，实现不得擅改）

```python
# packages/multi-workers/decision.py  —— 后端协议（decision_backends.py 实现，测试注入 fake）
class DecisionBackend(Protocol):
    name: str                 # "llm-transitional" | "llmproxy-anthropic" | "direct-systemone" | "fake"
    confidence_source: str    # "model-self-report" | "api"
    def decide(self, state: object, questions: dict, cfg: DecisionConfig) -> "BackendOutcome": ...

@dataclass
class BackendOutcome:
    available: bool
    reason: str | None        # entry-unavailable | rate-limited | upstream-error | bad-response | timeout | unsupported-question-type | disabled
    retryable: bool           # 类别级提示；是否重试由客户端决定
    answers: dict | None      # {qid: {"value": <any>, "confidence": float | None}}
    latency_ms: int
    detail: str = ""          # 人读，≤200 字符，禁含凭据
```

- 客户端 `DecisionClient.decide(state, questions) -> dict` 负责：参数校验（非法→抛 `DecisionInputError`，CLI 映射 exit 2）、预算（`timeout_s`/`max_retries`/`max_questions`/`max_state_bytes`）、重试与退避、响应归一（含 `available/transport/model/confidence_source/attempts/latency_ms/answers/reason`）、证据行落盘。
- 后端只做**单次**请求与**类别判定**；重试与总预算归客户端。
- 问题类型映射（wave 1）：`choice`（enum）、`score`（有界整数）、`noul`（bool）→ B2 可承载；`box` → B2 返回 `unsupported-question-type`（B1 预留）。

## §2 波次与任务

### W1（并行 2 束）

| 任务 | 目标 | 产物（写入允许面） | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **T-01a** 客户端核心 | 校验/预算/重试/fail-soft/证据行/归一 + fake 后端 | `packages/multi-workers/decision.py`、`packages/multi-workers/test_decide.py` | 无 | pytest 全绿；fail-soft 矩阵 + 预算用例覆盖 |
| **T-01b** 传输后端 | B2（实测契约）/B1（阻塞态）/B3（保留）/probe 逻辑 | `packages/multi-workers/decision_backends.py`、`packages/multi-workers/test_decide_backends.py` | 无（按冻结签名） | pytest 全绿；B2 解析/错误分类有 fake-HTTP 用例；probe 结果可落证据 |

### W2

| 任务 | 目标 | 产物 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **T-02** CLI/配置/doctor | `mw decide <run\|probe\|show>` + `.mw/decide.json` 读写（fail-soft + 原子写）+ doctor `triage:` 行（zero-perturbation） | `packages/multi-workers/mw.py`（仅 `cmd_decide` + 两处注册）、`packages/multi-workers/mw_common.py`（doctor 行）、`packages/multi-workers/test_decide_cli.py` | T-01a/T-01b | `mw decide run/probe/show` 可用；doctor 未配置时输出逐字节不变；pytest 全绿 |

### W3

| 任务 | 目标 | 产物 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **T-03** DP-1 接入（TS） | `planDispatchFrontmatter` 同步调用（硬超时）+ 回执拼接 + `triage-suggestion` notice kind + 结构化 JSONL + 降级默认静默 | `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`、`.../pm/pm-orchestrator.ts`、`packages/coding-agent/test/suite/...`（新增用例） | T-02 | TS 用例通过；`enabled=false` 与"决策不可用"两条路径行为与未接入逐分支等价；异常不外泄 |

### W4

| 任务 | 目标 | 产物 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **T-04** 验证与文档 | 端到端验证（含真实 B2 冒烟与 probe 证据）、等价性复核、README/CHANGELOG、verify 文档 | `evidence/runs/verify-mw-jev-provider-integration-20261016.md`、`packages/multi-workers/README.md`、`packages/multi-workers/CHANGELOG.md`、`packages/coding-agent/CHANGELOG.md` | T-03 | AC-001..011 逐条有证据行；`./test.sh` 与包内 pytest 零新增红 |

## §3 AC → 任务映射

| AC | 承载任务 |
| --- | --- |
| AC-001 契约（CLI=API，四型问题，`confidence_source`） | T-01a、T-01b、T-02 |
| AC-002 fail-soft（exit 0 / 仅参数非法 exit 2 / 不抛） | T-01a、T-02 |
| AC-003 传输抽象（≥3 后端可切换） | T-01b、T-02 |
| AC-004 probe 诊断（429/unmapped 锚点可复现） | T-01b、T-02、T-04 |
| AC-005 凭据最小面（只 TIMI_API_KEY，无明文） | T-01a、T-01b、T-04 |
| AC-006 预算与退避 | T-01a、T-02 |
| AC-007 DP-1 默认关闭 + 旁路建议 + 关闭态等价 | T-03、T-04 |
| AC-008 有效反馈（机器行 + 既有通道呈现） | T-01a、T-03 |
| AC-009 默认零行为变化 | T-02、T-03、T-04 |
| AC-010 doctor 行 + 文档 | T-02、T-04 |
| AC-011 测试（fake 覆盖 + 真实链路以 probe 呈现） | T-01a、T-01b、T-02、T-03 |
| AC-012 上游依赖显性化 | 已在 spec/design（D-1）；T-04 复核 |

### W5（质量门，review 类型）

| 任务 | 目标 | 产物 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **T-05** 对抗评审（QG） | 审 design+实现+证据：默认关闭等价性、fail-soft 铁律、置信度硬规则、覆盖面声明、他窗写入面是否被踩、测试是否真覆盖闭合路径 | `evidence/quality-gate-report-*.md` | T-04 | blockers 清单（0 条才算过）与 majors/minors 分级；发现问题→快修任务或 PM 直执 |
| **T-05b** 对抗评审（收窄重派，替代 T-05） | 只审 4 项：敏感内容外发（state→B2）/ 测试真实性 / 默认关闭等价性 / 诚实性与凭据 + 抽查 2 条 AC | 同上（`report-qa.md` → PM 归位） | T-04 | 同上；模型固定 `timi/glm-5.3`（T-05 默认模型三次 stream-closed，见 `_pitfalls.md` P-048/P-049） |

## §4 执行顺序与并行度

```text
W1:  T-01a ──┐
     T-01b ──┴─▶ W2: T-02 ──▶ W3: T-03 ──▶ W4: T-04 ──▶ W5: T-05(review/QG)
```

- W1 两束并行（互不写同一文件）；W2 起串行（有真实依赖）。
- 每束完成后 PM 回读证据/测试结果再放下一波；失败一律先查 worker.log/trace.log（wall 型重派一次并翻倍预算，idle 型直接排查）。

## §5 风险与回退

| 风险 | 处置 |
| --- | --- |
| `mw.py`/`mw_common.py` 与他窗并发改动 | T-02 单束集中改；提交时若文件含他窗 hunk → 索引级重建 |
| B2 延迟（实测 2.5–5.4s）使 DP-1 同步调用拖慢派发 | 默认 20s 硬超时 + 失败即无建议；`points.dp1.mode` 预留 async 位（不在本波交付） |
| B1 入口未暴露（D-1） | B1 显式 `entry-unavailable`，测试锁死；不静默降级为"看起来成功" |
| TS 侧改动触发他窗冲突（ui-bridge.ts 同文件） | 只改 `:1257`/`:2491` 段落，避开 `:3302-3391`；提交走索引级重建 |
| worker 长跑/挂死 | 卡片写死 timeout；wall 型失败翻倍预算重派一次，再失败转 PM 直执 |
