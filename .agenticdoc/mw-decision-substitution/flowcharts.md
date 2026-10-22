# 流程图 — mw-decision-substitution

> Key: `mw-decision-substitution` · 更新 2026-10-21 · 相位 EXECUTE（实现/验证完成，差人签收）
> HTML 版（目录 + 可渲染图 + 折叠源码）：同目录 `flowcharts.html`，浏览器直接打开。

四张图：目标、**代码实现逻辑**、验证流程、落地流程。
第 6 节保留"构建过程"（PM 视角的波次编排），与第 2 节的运行期代码逻辑区分开。

---

## 1. 目标

```mermaid
flowchart TB
    subgraph GOAL["目标（key: mw-decision-substitution）"]
        G["把 <b>中低风险人工决策</b> 从人手里移到 jev<br/>高风险/P0 仍归人"]
    end

    G --> A["决策点可枚举<br/>24 dp 进注册表<br/>tier / mode / risk_source"]
    G --> B["输入可结构化<br/>state 由确定性代码组装<br/>不是 LLM 编"]
    G --> C["答案可验收<br/>封闭键集合 + 七类失败码"]
    G --> D["决策可追溯<br/>jsonl 哈希链 + 签收门禁"]
    G --> E["人能介入<br/>per-dp 开关 / 置信阈值 / 签收"]

    A --> A1["mw decide dp list/show/check/verify"]
    B --> B1["state.context 五槽位<br/>注册表生成 TS 字段清单"]
    C --> C1["mw decide book new/check<br/>先验后发，失败零 HTTP"]
    D --> D1["decide_archive 4 类行<br/>advance_phase decision_signoff"]
    E --> E1["per-dp min_confidence / max_questions / timeout_s"]

    A1 --> OUT["产出：<br/>唯一传输 timi-decisions / jev-latest<br/>24/24 dp live 可用<br/>3 dp 真实接线（dp1/dp2/dp3）"]
    B1 --> OUT
    C1 --> OUT
    D1 --> OUT
    E1 --> OUT

    OUT --> NS["不做（已裁定）<br/>per-dp model / transport<br/>P0 全自动<br/>向后兼容旧 state"]
```

要点：

- **四个 dp 有真实调用方**：dp1 triage（`ui-bridge.ts:1730`）、dp2 checkpoint（`pm-orchestrator.ts:2602`）、
  dp3 worker 澄清（`worker-mode.ts:3903`）、dp25 签收结论（`mw decide sign`，W9/W11）。其余 21 个
  "已注册、可验证、未接线"——`wired` 与 `executor` 是两个维度（Python executor 只回显，真实动作在 TS/CLI 侧）。
- **签收不再是人的阻塞点**：`.mw/decide.json` 的 `signoff` 缺省 `auto` → 由 jev 出 `continue|narrow|revoke`；
  不可用或低置信才回落到 agent LLM 推断；`disable` 表示永不签收、`done` 门禁不阻塞。
- **state 不由 LLM 组装**：TS 生产者 + Python `_state_builder`，jev 只回答题面。
- **不做向后兼容**：state 字段改名后旧 state 直接 `input-incomplete`。

---

## 2. 实现流程（代码运行逻辑）

### 2.1 一次决策调用的端到端链路（流程图形式，兼容性优先）

```mermaid
flowchart TB
    subgraph P1["① TS 生产者"]
        A1["dp1 ui-bridge.ts:1730<br/>dp2 pm-orchestrator.ts:2602<br/>dp3 worker-mode.ts:3903"]
    end
    subgraph P2["② triage-client.ts"]
        B1["buildTriageState<br/>组装现场字段"]
        B2["validateStructuredState<br/>对照注册表生成物"]
        B3["canonicalize + 2000B 绑定<br/>超限先砍可选 / 劈半"]
        B4["refused 零 spawn"]
    end
    subgraph P3["③ mw.py + decision_points.py"]
        C1["cmd_decide / _decide_run<br/>state 走 stdin"]
        C2["decide_for 步骤 1-3<br/>unknown id / enabled / mode"]
        C3["步骤 4-4b<br/>transport 配置 + resolve_policy"]
        C4["步骤 5-6<br/>build_state + required + _fit_state"]
        C5["escalate<br/>disabled / unavailable / input-incomplete / input-oversize"]
    end
    subgraph P4["④ decision.py + backend"]
        E1["DecisionClient.decide<br/>三闸：字节 / 32k / 64k"]
        E2["TimiDecisionsBackend<br/>POST /v1/decisions"]
        E3["jev-latest<br/>model + state + questions 三键"]
        E4["available=false<br/>budget-exhausted 等"]
    end
    subgraph P5["⑤ 判定与归档"]
        F1["步骤 7-8<br/>unavailable / low-confidence"]
        F2["步骤 9<br/>suggest 或 intent=answer"]
        F3["步骤 10-11<br/>executor 成功 / over-authority"]
        F4["decide_archive.append_decide<br/>jsonl 哈希链 + policy 回显"]
    end
    subgraph P6["⑥ 回传与消费"]
        G1["JSON 出参 stdout<br/>parse + applyAuthorityKeys"]
        G2["TriageResult"]
        G3["dp1 处置<br/>dp2 仅收窄<br/>dp3 sendUserMessage 前缀 steer"]
    end

    A1 --> B1 --> B2
    B2 -->|"缺/多字段"| B4
    B2 -->|"通过"| B3 --> C1
    C1 --> C2
    C2 -->|"unknown id"| C5
    C2 -->|"disabled"| C5
    C2 -->|"通过"| C3
    C3 -->|"未配置"| C5
    C3 -->|"已配置"| C4
    C4 -->|"字段缺失 / 超 2000B"| C5
    C4 -->|"通过"| E1
    E1 -->|"闸门拦下"| E4
    E1 -->|"通过"| E2 --> E3
    E3 -->|"200 + answers"| F1
    E4 --> F1
    C5 --> F4
    F1 -->|"不可用 / 低置信"| F4
    F1 -->|"可用"| F2
    F2 -->|"suggest / answer"| F4
    F2 -->|"auto + act"| F3
    F3 --> F4
    F4 --> G1 --> G2 --> G3
```

### 2.2 `decide_for` 的判定树（11 步，含短路点）

```mermaid
flowchart TB
    S["decide_for dp_id<br/>decision_points.py:2191"] --> S1{"dp_id 在注册表?"}
    S1 -->|"否"| E2["DecisionInputError<br/>CLI exit 2"]
    S1 -->|"是"| S2{"enabled?"}
    S2 -->|"false"| R1["escalate disabled<br/>在 build_state / 网络之前返回"]
    S2 -->|"true"| S3["mode 校验<br/>config 优先，注册表兜底"]
    S3 --> S4{"transport 已配置?"}
    S4 -->|"否"| R2["escalate unavailable"]
    S4 -->|"是"| S4B["resolve_policy + _apply_per_dp_budget<br/>row > .mw/decide.json > builtin"]
    S4B --> S5["build_state trigger<br/>_state_builder 加 schema_version / decision_point"]
    S5 --> S5A{"required_state_fields 齐?"}
    S5A -->|"缺"| R3["escalate input-incomplete<br/>只报字段名，不报值"]
    S5A -->|"齐"| S6["_fit_state<br/>先 fit_context 再丢可选字段"]
    S6 --> S6A{"仍超 2000B?"}
    S6A -->|"是"| R4["escalate input-oversize"]
    S6A -->|"否"| S7["DecisionClient.decide"]
    S7 --> S7A{"available?"}
    S7A -->|"false"| R5["escalate unavailable<br/>reason: disabled/timeout/rate-limited/..."]
    S7A -->|"true"| S8{"答案可用且置信达标?"}
    S8 -->|"空 / 缺 qid / 非法值 / 低于 floor"| R6["escalate low-confidence"]
    S8 -->|"可用"| S9{"mode=suggest 或 intent=answer?"}
    S9 -->|"是"| A1["acted=false<br/>归档建议，不执行"]
    S9 -->|"否"| A2{"executor 存在且成功?"}
    A2 -->|"否"| R7["escalate over-authority"]
    A2 -->|"是"| A3["acted=true + actual_action"]
    R1 --> ARC["归档：decide 行 + 哈希链 + policy 回显"]
    R2 --> ARC
    R3 --> ARC
    R4 --> ARC
    R5 --> ARC
    R6 --> ARC
    R7 --> ARC
    A1 --> ARC
    A3 --> ARC
    ARC --> OUT["DecisionOutcome<br/>status / answered_by / confidence / detail"]
```

### 2.3 客户端三层容量闸与传输（`decision.py:797`）

```mermaid
flowchart TB
    C0["DecisionClient.decide"] --> C1["_validate_input<br/>state 三形态 + questions 类型"]
    C1 --> C2{".mw/decide.json 已配置?"}
    C2 -->|"否"| CE["available=false<br/>reason=disabled"]
    C2 -->|"是"| C3{"max_state_bytes > 0 且超限?"}
    C3 -->|"是"| CB["budget-exhausted<br/>带实际字节数"]
    C3 -->|"否"| C4{"state + 最长单题 > 32768 tokens?"}
    C4 -->|"是"| CB
    C4 -->|"否"| C5{"整份请求 > 65536 tokens?"}
    C5 -->|"是"| CB
    C5 -->|"否"| C6["_resolve_backend<br/>transport=timi-decisions"]
    C6 --> C7{"有 backend?"}
    C7 -->|"否"| CE2["available=false<br/>reason=entry-unavailable"]
    C7 -->|"是"| C8["循环直到 timeout_s 截止<br/>不做模型回退、不换传输"]
    C8 --> C9{"HTTP 2xx?"}
    C9 -->|"否"| C10["reason=rate-limited / upstream-error"]
    C9 -->|"是"| C11{"响应体带 error?"}
    C11 -->|"是"| C10
    C11 -->|"否"| C12["回填 model / confidence_source<br/>answers + latency_ms"]
    C10 --> C13["available=false + attempts"]
    C12 --> CO["response dict"]
    C13 --> CO
```

`_estimate_tokens` 是保守估计：非 ASCII 1 token/字符，ASCII 4 字符/token。

### 2.4 state 由谁生产（确定性代码，不经过 LLM）

| dp | 生产者锚点 | 触发器 | state 关键字段 |
| --- | --- | --- | --- |
| dp1 triage | `pm/ui-bridge.ts:446` / `:503 dispatchTaskExcerpt` / `:564` | 派发前风险分类 | `scope.file_extensions`、`progress.elapsed_minutes`、`risk_source`、`context.task_excerpt` |
| dp2 checkpoint | `pm/pm-orchestrator.ts:2161/2201/2209` | CHECKPOINT mid/high risk | `change_summary`、`context.artifact_status`、阈值来自生效 policy |
| dp3 worker 澄清 | `worker/worker-mode.ts:5057/5075 buildDp3State` | worker 提出澄清问题 | `ambiguity.question`、`local_candidates`、`context.change_summary` + `context.candidate_snippets` |
| 任意 dp | `decision_points.py:402 _state_builder` | `decide run` | `{schema_version: 2, decision_point}` + `trigger.data` setdefault + `key/task_key/questions_version` |
| 任意 dp | `decision_context.py:197 fit_context` | 发送前 | `state.context` 五槽，单源槽位表与截断规则 |

TS 侧还有一道开发期护栏：`ui-bridge.ts:461 assertStateMatchesRegistry` 对照
`shared/decide-registry.generated.ts`（由 `scripts/gen_decide_registry_ts.py` 从
`decide_registry.json` 生成，`--check` 零漂移）。缺字段或多字段都 throw——防止
"配置要求 A、代码发 B"。

### 2.5 两条入口分叉：直接 run 与决策本 run

```mermaid
flowchart TB
    I{"入口"} -->|"mw decide run --dp X --json<br/>state 来自 stdin"| P1["decide_for<br/>同 2.2"]
    I -->|"mw decide run --book B"| B1["load_book + check_book<br/>七类失败码 + 封闭键集合"]
    B1 -->|"任一不符"| B2["exit 2<br/>零 HTTP、零归档"]
    B1 -->|"通过"| B3["从 book 提取 state<br/>校验 questions_version"]
    B3 --> P1
    P1 --> AR["归档行<br/>带 book_path + file_sha256"]
```

决策本骨架由配置生成，不由人/LLM 猜：

```
decide_registry.json  ──▶  mw decide book new <dp>  ──▶  骨架（键与顺序 == required_state_fields）
                                                          │
                                        人或 decision worker 填值（只写输入，不写预期答案）
                                                          ▼
                                             mw decide book check --book B
```

七类失败码：`book-schema` / `book-state` / `book-placeholder` / `book-context` /
`book-evidence` / `book-budget` / `book-secret`。

### 2.6 `decision` worker 类型的门禁（运行时）

```mermaid
flowchart TB
    D0["dispatch_worker type=decision<br/>autopilot/dispatch.py REGISTRY"] --> D1{"卡片四项齐?<br/>dp / 证据来源 / 分支后果 / allow-send"}
    D1 -->|"缺"| D2["missing-item:NAME<br/>拒绝派发，零 spawn"]
    D1 -->|"齐"| D3{"dp 定义了 required_state_fields?"}
    D3 -->|"否"| D4["dp-required-state-fields-missing"]
    D3 -->|"是"| D5["写面收窄到 key/evidence/books/**<br/>卡片更宽则记 narrowed_by"]
    D5 --> D6["worker 启动：只读工具 + 窄 bash<br/>book new -> 填值 -> book check"]
    D6 --> D7{"allow-send?"}
    D7 -->|"no（缺省）"| D8["禁 --book<br/>book-send-refused，发送权归 PM"]
    D7 -->|"yes"| D9["worker 可 --book 发送"]
    D8 --> D10["PM 复核 book check 后自行发送"]
```

离线预判：`mw dispatch check --card FILE [--dp ID] [--book FILE] [--json]`
（exit 0 干净 / 2 拒绝 / 1 用法错误），判据与 `dispatch()` 拒绝时完全相同。

---

### 2.7 签收链路（`mw decide sign --key <任意 key>`，W9/W11）

```mermaid
flowchart TB
    S0["mw decide sign<br/>无 --conclusion 即自动"] --> S1{".mw/decide.json 的 signoff"}
    S1 -->|"disable"| S2["不写文件<br/>done 门禁签收规则豁免"]
    S1 -->|"auto（缺省）"| S3{"decide 已配置<br/>且 dp25 生效 enabled?"}
    S3 -->|"是"| S4["decide_for dp25-signoff-conclusion<br/>intent=answer<br/>state = collect 事实"]
    S4 --> S5{"available 且<br/>置信 >= 生效 min_confidence?"}
    S5 -->|"是"| S6["结论 = jev 答案<br/>signed_via: auto-decide"]
    S5 -->|"否"| S7["回落 LLM 推断<br/>--auto --conclusion X<br/>signed_via: auto-llm<br/>decide_fallback: reason"]
    S3 -->|"否"| S7
    S6 --> S8["render + write_signoff<br/>auto-* 允许 agent 会话"]
    S7 --> S8
    S8 --> S9["append authority-change 行<br/>by=signoff:conclusion，note 记 signed_via"]
    S9 --> S10["advance_phase done 门禁<br/>counted_rows / rows_sha256 / verdict"]
    S2 --> S11["done 门禁通过<br/>输出 signoff=disable note"]
```

判据（写进 `dp25` 的 `instructions`）：

- `continue`：N≥1 可用行 + 链闭合 + 每行 `timi-decisions/jev-latest/api`
- `narrow`：能力降级但仍要保留部分授权
- `revoke`：链断、engine 不符、或没有任何可用行

防自我背书：dp25 自己的档案行不计入签收事实；`signed_via` 只写 `auto-decide|auto-llm|cli|tui`。

---

## 3. 验证流程

```mermaid
flowchart TB
    L1["L1 单元<br/>pytest: decision 相关 226 passed<br/>vitest: 6 suite 152 passed / 早前 163"]
    L1 --> L2["L2 镜像锁<br/>frozen allowlist 快照 / 角色映射双向<br/>gen_decide_registry_ts --check 零漂移<br/>triage-client STATE_TOP_LEVEL_KEYS"]
    L2 --> L3["L3 配置契约<br/>dp check 24/24 干净<br/>dp verify 24 ok / 0 fail<br/>book check 封闭键集合"]
    L3 --> L4["L4 真机<br/>dp verify --live 24/24 available<br/>jev-latest 766-1361ms<br/>三案例：noul 0.31 / choice 0.30 / score 0.55"]
    L4 --> L5["L5 质量门 QG<br/>4 份报告 → 三轮全 PASS"]

    L5 --> G1{"advance_phase check_gate"}
    G1 -->|"spec/design/plan/tasks/execute/verify"| OK1["PASS"]
    G1 -->|"done"| G2["decision_signoff 检查<br/>evidence/review/sign-final.md"]
    G2 -->|"缺文件"| BLOCK["BLOCKED<br/>需人在 agent 会话外签收"]
    G2 -->|"有 conclusion: continue"| DONE["可推 DONE"]

    NOTE["本机环境边界（非本 key 引入）<br/>tsgo 全局不可用：worker/output-sections.ts 被另一 live 窗口改到半途<br/>pytest 3180 passed / 9 failed：GBK 子进程解码 3 + 历史卡片被清理 2 + 其他会话在飞 4"]
```

| 层 | 命令 | 通过标准 |
| --- | --- | --- |
| L1 | `python -m pytest -q`（packages/multi-workers）/ `npx vitest --run test/suite/...` | 新增全绿，无新增失败 |
| L2 | `python scripts/gen_decide_registry_ts.py --check`；parity / frozen 快照测试 | rc=0，零漂移 |
| L3 | `mw decide dp check` / `mw decide dp verify` / `mw decide book check` | 0 error / 0 warning |
| L4 | `mw decide dp verify --live`、真实 worker 派发 | 24/24 `available=true`，model=jev-latest |
| L5 | QG review（4 份证据报告） | 三轮 PASS |
| 门禁 | `advance_phase check_gate(key, "done")` | 仅差 `sign-final.md` |

---

## 4. 落地流程

```mermaid
flowchart TB
    B0["代码就绪<br/>packages/multi-workers + coding-agent"] --> B1["构建<br/>mw build --allow-dirty --install<br/>bundle → ~/.pi/agent/extensions/agent-team-loop.js"]
    B1 --> B2["重启服务<br/>/mw restart<br/>（当前 serve 跑 stale code）"]
    B2 --> B3["重载扩展<br/>/reload<br/>（当前进程仍是旧 bundle）"]
    B3 --> USE

    subgraph USE["使用面（配置驱动三件套）"]
        U0["① 选 dp<br/>mw decide dp list / show dp3"]
        U1["② 生成决策本骨架<br/>mw decide book new dp3-worker-clarify"]
        U2["③ 填值（人 / decision worker）<br/>键 == required_state_fields<br/>只写输入，不写预期答案"]
        U3["④ 验收<br/>mw decide book check --book B"]
        U4["⑤ 发送<br/>mw decide run --book B 或 --book + decision worker 派发"]
        U0 --> U1 --> U2 --> U3 --> U4
        U3 -->|"任一失败码"| U2
    end

    USE --> S1["签收（唯一 done 阻塞）<br/>mw decide sign --conclusion continue<br/>写 evidence/review/sign-final.md + authority-change 行"]
    S1 --> S2["推 DONE<br/>advance_phase → done<br/>_project_log 摘要行"]
    S2 --> S3{"用户放话"}
    S3 -->|"提交"| S4["feat(multi-workers) / feat(coding-agent) / feat(ai) + docs<br/>mw-heartbeat-attempt-reset 随同"]
    S3 -->|"重建 dist"| S5["dist/** 重建（当前 bundle 早于 W5b-W8）"]

    S1 -.->|"不签 / narrow / revoke"| S6["回到 dp 配置或设计<br/>降级、收窄或撤销该 dp"]
```

签收命令（必须人在 agent 会话外执行）：

```bash
python packages/multi-workers/mw.py decide sign \
  --project .agenticdoc/mw-decision-substitution \
  --conclusion continue \
  --reason "<理由>"
```

---

## 5. 当前状态

| 环节 | 状态 |
| --- | --- |
| 实现（T-01..T-12 / FIX-A..R / W1..W8） | 完成 |
| 验证 L1-L5 | 完成 |
| 门禁 spec/design/plan/tasks/execute/verify | PASS |
| 门禁 done（`decision_signoff`） | **PASS**：`mw decide sign` → dp25 → jev 答 `narrow`（confidence=0.7 api），`signed_via: auto-decide`，无 `decide_fallback` |
| 构建 + 重启 + 重载 | 待用户（bundle 早于 W5b-W8） |
| 提交 | 待用户放话 |

---

## 6. 附录：构建过程（PM 视角的波次编排，非运行期代码逻辑）

```mermaid
flowchart TB
    SPEC["SPEC<br/>5 束 research 并行<br/>spec rev3 AC-001..022"] --> DES["DESIGN<br/>6 束 research 并行<br/>D-001..063"]
    DES --> PLAN["PLAN<br/>W1..W8 波次表<br/>每波自带测试"]

    PLAN --> R1{"第一轮：底座"}
    R1 --> T1["T-01..T-12<br/>注册表 / 档案链 / dp1·dp2·dp3 / 签收命令"]
    T1 --> FIX["FIX-A..R<br/>类型 / 传输收敛 / 签收门 / 冻结镜像"]

    FIX --> R2{"第二轮：配置驱动"}
    R2 --> W1W2["W1 ∥ W2<br/>state 三形态 + token 双闸 ∥ Python 字段改名"]
    R2 --> W3["W3<br/>TS 字段改名 + 校验镜像"]
    W1W2 --> W4W5["W4 ∥ W5b<br/>配置自描述 + dp verify ∥ per-dp 三旋钮"]
    W3 --> W4W5
    W4W5 --> W6W7["W6 ∥ W7<br/>context 槽位 + 生成 TS 清单 ∥ 决策本 new/check"]
    W6W7 --> W8["W8<br/>decision worker 类型<br/>卡片四项判据 + allow-send 门 + 写面收窄"]

    W8 --> PM["PM 收口（串行）<br/>镜像锁 5 处 / 槽位口径统一 / mw dispatch check 注册 / CHANGELOG / pm-state"]

    PM --> RULE1["规矩 1：关闭态先同构<br/>dp 全关 → run.json / output.md / trace.log 逐字节等于基线"]
    PM --> RULE2["规矩 2：契约先行<br/>改契约必须回 design 改 D-xxx"]
    PM --> RULE3["规矩 3：写面互斥<br/>同波同文件只一个 worker"]
```

关键坑（已入 `.agenticdoc/_pitfalls.md`）：

- 卡片 `write_face:` 必须**一行一个路径**（顿号并列只解析第一条）。
- worker 整文件读 `mw.py`（1 万行）/ `worker-mode.ts`（5 千行）会 4 GB 堆 OOM。
- 派发卡片必须带 ≥1 个 `path:line` 种子锚点，否则 envelope 拒绝。
- 卡片 `###` 子标题会被提升成 `##`，吞掉后续标题。
