# DESIGN D6 — 结构化输入落地设计（≤2KB schema · state_digest · 唯一出口 · L2 负向测试 · input-incomplete · 旧输入兼容）

- key: `mw-decision-substitution` · 相位 DESIGN · 卡片 `tasks/D6-input-redaction.md`（card_sha256 ae44a21f…）
- 调研方式：只读检索 + 本机双侧可执行验证（Python 3.14 / Node 22 实算 digest 与字节数），未改任何源码/配置/测试，未做 git 操作
- 代码基线：`packages/coding-agent/src/extensions/agent-team-loop/pm/{triage-client.ts,ui-bridge.ts}`、`packages/multi-workers/{decision.py,mw.py,mw_common.py,decision_backends.py}`
- 行号基准：2026-10-19 工作区实读（全部逐条 rg 实证，非转引）
- 上游输入：RQ-4 证据 `.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`（下称 RQ-4 证据）的 State Schema 草案与 8 条脱敏规则——本文直接引用并细化为可实现字段表，不重做。
- spec 锚点：`spec.md:156-162`（§5.4 输入契约：`:157` canonical ≤2000B + `state_digest = sha256(_encode_state(state))[:16]`、`:158` 三级敏感度、`:159` 唯一出口与 `_redact` 不覆盖 state、`:160` 必需字段缺失双门、`:161` `isinstance(state, str)` 旧分支）；`spec.md:167-176`（§6.1 decisions.jsonl，`:168` 最小字段集含 `state_digest`）。

---

## Q1 ≤2KB 结构化 state 的字段表、体积预算与截断策略

### Q1.1 可实现字段表（RQ-4 草案 → 实现规格）

序列化口径 = **canonical JSON**：递归键排序（字节升序）+ 紧凑分隔符 `,`/`:` + `ensure_ascii=False` + UTF-8 编码（与 Q2.2 的跨语言契约一致）。体积预算一律按该口径的 UTF-8 字节计。`L` = 敏感级（L0 可外发 / L1 摘要脱敏后外发；L2 结构性无承载字段，表中不出现——这是 RQ-4 证据 §3.1 的分级结论）。

| 字段 | 类型 | 必填 | L | 体积预算 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `v` | int（常量 2） | 必填 | L0 | ≤8B | schema 版本；digest 覆盖 |
| `dp` | string enum | 必填 | L0 | ≤20B | `dp1\|dp2-checkpoint\|dp3-clarify\|dp4-failure\|dp5-flaky\|dp6-qg\|dp13-release` |
| `key` | string | 必填 | L0 | ≤48B | owner key（AgenticTask key，机读 id） |
| `task_key` | string | 可选 | L0 | ≤48B | worker 任务 key |
| `phase` | string enum | 必填 | L0 | ≤16B | SPEC/DESIGN/EXECUTE/… |
| `task_type` | string enum | 必填 | L0 | ≤12B | `coding\|research\|review`（枚举同 `triage-client.ts:55-58` 的 choices） |
| `requested_type` | string enum | required_if dp=dp1 | L0 | ≤12B | 待派发类型 |
| `risk` | string enum | 必填 | L0 | ≤8B | `low\|mid\|high` |
| `risk_source` | string enum | 必填 | L0 | ≤12B | `machine\|pm-label`（判据可溯源，RQ-4 证据 Q2） |
| `authority_tier` | string enum | 必填 | L0 | ≤6B | `P0\|P1\|P2`；P0 → 构造侧短路（Q5.2） |
| `questions_version` | string | 必填 | L0 | ≤24B | 问题集版本（digest 必须覆盖，spec.md §6.1 同名字段） |
| `task_summary` | string | required_if dp∈{dp1,dp3} | L1 | ≤600B | PM 生成摘要；过 `redactSummary()`（Q3.3），禁逐字用户原话 |
| `scope.write_scope` | string[] ≤12 项 | required_if dp=dp1 | L1 | ≤384B（12×32B） | repo 相对路径 ≤3 层 |
| `scope.ext` | string[] ≤6 项 | required_if dp=dp1 | L0 | ≤36B | 扩展名集合 |
| `scope.images_required` | bool | 可选 | L0 | ≤24B | 三态检测降维（RQ-4 证据 Q1.2-A） |
| `progress.elapsed_min/budget_min` | int | required_if dp=dp2-checkpoint | L0 | 各≤8B | 分钟粒度桶（防心跳抖动使 digest 失效，RQ-4 证据 Q4） |
| `progress.phases_done/phases_total` | int | required_if dp=dp2-checkpoint | L0 | 各≤8B | |
| `progress.artifact_present` | bool | required_if dp=dp2-checkpoint | L0 | ≤20B | computeRisk 输入（`worker-mode.ts:351-368`） |
| `progress.writes/uniq_targets/repeat_top/last_land_age_min` | int/null | 可选 | L0 | 合计≤80B | |
| `failure.kind` | string enum | required_if dp∈{dp4-failure,dp5-flaky} | L0 | ≤24B | `model-error\|wall-timeout\|exit-nonzero\|needs-clarification\|lost` |
| `failure.exit` | int | required_if failure.kind=exit-nonzero | L0 | ≤8B | 与 kind 同现校验（Q5.2） |
| `failure.attempts` | int | 可选 | L0 | ≤8B | |
| `failure.summary` | string | 可选 | L1 | ≤300B | 机器单行，过 `redactSummary()` |
| `failure.test_name` | string | required_if dp=dp5-flaky | L1 | ≤64B | 仅标识符（正则 `[A-Za-z_$][\w$]*` 白名单） |
| `failure.baseline_known` | bool | required_if dp=dp5-flaky | L0 | ≤20B | 环境噪声基线（AGENTS.md 已知 89 例基线） |
| `ambiguity.kind` | string enum | required_if dp=dp3-clarify | L0 | ≤20B | `scope\|missing-dep\|rule-conflict` |
| `ambiguity.question` | string | required_if dp=dp3-clarify | L1 | ≤300B | PM 改写后问题，过 `redactSummary()` |
| `closure.*`（blockers_count/evidence_present 等） | int/bool/string[] | required_if dp∈{dp6-qg,dp13-release} | L0 | 合计≤150B | blockers 一行摘要 ≤200B/条 ≤3 条（L1，可选） |
| `history.recent_*`（5 个 int） | int | 可选 | L0 | 合计≤90B | owner key 近 20 次状态聚合 |

通用规则：(a) 数字一律 **int**，禁止 float（Q2.2 数字格式一致性的前提）；(b) 未知键构造期即拒绝（不是剥离开外发——TS 是生产者，schema 漂移应在其自家测试暴露）；(c) 体积预算含键名与 JSON 结构开销在内的最坏估计。

### Q1.2 填充到上限内的示例（实算 706B）

dp1 派发 triage 的完整示例（内容取自本 key 真实上下文；`task_summary` 为中文最坏 3B/字），canonical 序列化后 **706 字节**（本机 `python -X utf8` 实算）：

```json
{"authority_tier":"P2","dp":"dp1","history":{"recent_done":4,"recent_failed":1,"recent_lost":0,"recent_needs_clarification":0,"recent_superseded":2},"key":"mw-decision-substitution","phase":"EXECUTE","questions_version":"dp1@1","requested_type":"coding","risk":"mid","risk_source":"pm-label","scope":{"ext":["ts","py"],"images_required":false,"write_scope":["packages/coding-agent/src/extensions/agent-team-loop/pm","packages/multi-workers"]},"task_key":"ds-d7-dispatch-schema","task_summary":"决策服务结构化输入落地：triage-client 出口改为结构化 state，字段表与脱敏规则按 RQ-4 证据执行，涉及 pm/triage-client.ts 与 decision.py 校验分支","task_type":"coding","v":2}
```

该串 sha256 前 16 hex = `b8d767f1d8f3b187`（即其自身 state_digest，可复算验证）。距 2000B 上限余量 ≈65%，说明典型 dp1 state 在 600–1100B 区间，2000B 上限合理。

### Q1.3 按构造封顶：per-dp 最坏字节数（实算）

`required_if` 矩阵保证**每个 dp 只携带自己的一组区块**，不可能同时带上 scope+progress+failure+ambiguity+closure（全区块同开的病态组合实算 2625B 会超限——这正是必须按 dp 切分的原因）。各 dp 所有字段顶格（CJK 3B/字、数组满额、计数 4 位数）的最坏值，本机实算：

| dp | 最坏字节数 | 组成 |
| --- | --- | --- |
| dp1 | **1397B** | task_summary 600B + scope 满额（12 项×21 字符路径+6 ext）+ history 满额 |
| dp2-checkpoint | **580B** | progress 全字段顶格 + history 满额（无 task_summary） |
| dp3-clarify | **1363B** | task_summary 600B + ambiguity.question 300B + history 满额 |

dp4/dp5 = dp2 基座 + failure 块（≤300B summary + 64B test_name → 估算 ≤900B）；dp6/dp13 = 基座 + closure ≤150B → 估算 ≤700B（此两行是构造推算，未逐字节实算，见残留）。结论：**全部 dp 的最坏构造 ≤2000B**，上限由字段预算表在构造期保证，运行期只需断言不需裁剪正常数据。

### Q1.4 超限截断策略（两段式，绝不丢必需字段）

正常数据按 Q1.3 不可能超限；超限只剩两种来源——caller 传入了失控长文本（builder 的 cap 会先截）或 schema 演进破坏了预算表。策略：

- **构造期（第一段，防止超限发生）**：`redactSummary()` 对每个 L1 字段按预算硬截（`task_summary`→600B、`question`/`summary`→300B），码点边界截断（不得劈开代理对/JSON 转义），截后单行化。`scope.write_scope` >12 项取前 12 项。所有 cap 是 builder 内常量，不是运行时配置。
- **运行期（第二段，断言 + 确定性降级）**：`canonicalStateBytes(state)` 计字节 >2000 时，按**固定丢弃优先级**逐步丢弃/收缩可选 L1 字段，每步重新 canonical + 计字节，首个满足即停：
  1. 删 `history` 整块（纯聚合，决策价值最低）；
  2. `closure.blockers_kind` 收缩到 2 项 → 1 项；
  3. `scope.write_scope` 收缩到 6 项 → 3 项（保 `ext`）；
  4. 删 `progress` 的可选键（writes/uniq_targets/repeat_top/last_land_age_min）；
  5. 删 `failure.summary`（可选 L1）；
  6. **必需 L1 字段（task_summary / ambiguity.question）收缩到 cap 的 50%**——只缩不丢（"绝不丢必需字段"）；
  7. 仍超 → **拒发** `input-oversize`（见 Q5），绝不发出破损 state。
- 禁止对 canonical JSON 字符串做盲截（旧 `boundTriageState` 的 0.9 系数尾部截断会把 JSON 截坏，`triage-client.ts:216-222` 的做法在结构化路径上废除；字符串路径保留原样，见 Q6.1）。

### Q1.5 超限留痕

截断/拒发不进 state（不为此加字段——会自增体积且改变 digest），留痕走现有台账通道：`emitDispatchTriage` 的不可用分支写 `kind=triage-unavailable` 台账行（`ui-bridge.ts:270-274`，经 `recordDispatchAlarm`，写点 `pm/pm-orchestrator.ts:645`），detail 为 `dp=dp1 reason=input-oversize dropped=history,failure.summary`——只记**字段名与步数**（字段名是 L0），不记被删内容。是否绕过 `triage_notify_on_unavailable` 开关强制留痕，见 Q5.4 的设计建议。

---

## Q2 state_digest 跨语言一致方案

### Q2.1 方案选型：Python 侧单点计算 + 响应回传（推荐）

**谁 canonical 化：Python，且只有 Python 算 digest。** 论证：

1. digest 的两个消费方都在 Python 侧：11 字段传输证据行（`decision.py:125-136` `_EVIDENCE_FIELDS`，由 Python 单写，`triage-client.ts` 头注释 D-005 明确 TS 永不写）与 §6.1 `decisions.jsonl`（spec.md:168，`state_digest` 在最小字段集里；哈希链/档案同属 Python 写面）。
2. Python 已经持有 canonical 字节：`_encode_state`（`decision.py:402-414`）就是预算检查的计字节来源（`decision.py:653`），digest = `sha256(同一份字节).hexdigest()[:16]`，零额外序列化。
3. 回传通道现成：`mw decide run --json` 把响应 dict 原样打到 stdout（`mw.py:809-810`），在响应对象加 `state_digest` 键，TS 只透传不计算——**TS 侧零 sha256 依赖、零漂移风险**。
4. TS 侧仍需本地 canonical 字节做 2000B 预算断言（Q1.4），但只计长度、不哈希；长度相等性由 Q2.2 的参数钉死 + Q2.3 向量在两侧 CI 验证。

### Q2.2 若两侧各算一次：等价序列化参数（必须成对钉死）

| 参数 | Python 侧 | TS 侧 | 漂移风险与对策 |
| --- | --- | --- | --- |
| 键排序 | `json.dumps(..., sort_keys=True)`（递归，按码点） | 递归 `Object.keys(v).sort()`（按 UTF-16 码元） | schema 的键全是 ASCII 标识符 → 码点序=码元序，等价；值不参与排序 |
| 分隔符 | **`separators=(",", ":")`**（必须显式） | `JSON.stringify` 默认即紧凑 | **现状不等价**：`decision.py:410` 未传 separators，默认是 `(', ', ': ')`（带空格），见 Q2.4 反证 |
| 非 ASCII | `ensure_ascii=False` | `JSON.stringify` 默认原样输出 | 两者都产原始 UTF-8，等价 |
| 数字 | schema 仅允许 int/bool | 构造期拒绝 float（`Number.isInteger` 断言） | JS `1.0`→`"1"`、Python `1.0`→`"1.0"` 会漂移；int-only 从根上排除。NaN/Infinity 同理被 int-only 排除（`JSON.stringify` 转 null、Python 产 `NaN`） |
| 不可序列化对象 | 现 `default=str`（`decision.py:410`） | 不适用 | 结构化分支**去掉** `default=str`：schema 保证 JSON 原生类型，留着会掩盖两侧不同的构造 bug |
| 字符串规范化 | Python 不做 | 构造期剥孤立代理对与控制字符 | ES2019 `JSON.stringify` 把孤立代理转义为 `\uD8xx`，Python `.encode(errors="replace")`（`decision.py:411`）产出 U+FFFD → 漂移；builder 层统一归一化 |
| 编码 | `.encode("utf-8")` | `Buffer.byteLength(s, "utf8")` / TextEncoder | 等价 |

Python 侧落地：`_encode_state` 的 dict 分支（`decision.py:409-414`）改为 `json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`。str 分支（`decision.py:405-406`）逐字节不动（Q6.1）。唯一 caller 是 `decision.py:653`，全仓无其他引用、无测试钉其字节（rg 实证 0 命中），改动无涟漪。

### Q2.3 可复现测试向量（2026-10-19 本机 Python + Node 双侧实算通过）

**输入 JSON**（给定形态：键乱序、含中文、含 JSON 转义的 Windows 路径、含 int/bool/嵌套对象；解码后字符串含 `C:\Users\wenbozhou\repo`）：

```
{"task_summary": "路径剥离：C:\\Users\\wenbozhou\\repo 只留 repo 相对路径", "v": 2, "scope": {"ext": ["ts", "py"], "nested": true}, "dp": "dp1", "attempts": 3}
```

**canonical 后**（157 字节 UTF-8，键排序、紧凑分隔符、非 ASCII 原样、`\\` 为 JSON 转义保留）：

```
{"attempts":3,"dp":"dp1","scope":{"ext":["ts","py"],"nested":true},"task_summary":"路径剥离：C:\\Users\\wenbozhou\\repo 只留 repo 相对路径","v":2}
```

**期望值**：
- sha256 全长：`d428504f067a509291c57a3a73910f62e4287219a4cb52b7ee22534828663843`
- `state_digest`（[:16]）：**`d428504f067a5092`**

Python 验证：

```python
import hashlib, json
s = json.dumps(json.loads(input_text), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
assert hashlib.sha256(s.encode("utf-8")).hexdigest()[:16] == "d428504f067a5092"
```

Node 验证：

```js
import { createHash } from "node:crypto";
const canon = (v) => Array.isArray(v) ? v.map(canon)
  : (v !== null && typeof v === "object")
    ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, canon(v[k])]))
    : v;
const s = JSON.stringify(canon(JSON.parse(input_text)));
assert.strictEqual(createHash("sha256").update(s, "utf8").digest("hex").slice(0, 16), "d428504f067a5092");
```

两段代码本机实跑输出一致（`canonical_bytes=157`，digest 同上）。向量刻意覆盖四类漂移源：键排序（乱序输入）、中文（ensure_ascii）、反斜杠转义（Windows 路径）、紧凑分隔符。

### Q2.4 为什么向量必须钉死 separators（现状反证）

用同一输入跑**现状** `_encode_state` 的 dict 分支参数（`json.dumps(..., ensure_ascii=False, sort_keys=True, default=str)`，默认分隔符带空格），得 digest `a4e0ddff7ed8a2e0` ≠ 期望值 `d428504f067a5092`（本机实算）。即：不显式钉 separators，Q2.3 的向量会在 Python 侧当场失败——这正是测试向量的价值。

---

## Q3 唯一出口改造（triage-client.ts:273 前后）

### Q3.1 现状调用链（实读行号）

`planDispatchFrontmatter` 组装 state（`ui-bridge.ts:1429-1436`，其中 `:1432` 调 `buildTriageState`）→ `computeDispatchTriage`（`ui-bridge.ts:236-256`，`:244` 调 `triageDispatch`）→ `triageDispatch` 内**唯一出口** `triage-client.ts:273`：`input: JSON.stringify({ state: boundTriageState(input.state), questions: DP1_QUESTIONS })` → `runDecideMw` 把该字符串经 spawnSync stdin 交给 `mw.py decide run`（`triage-client.ts:172` `input: request.input`；argv 只带 `--project/--dp/--json`，D-003）。现状 state 是 16KB 级描述全文（`triage-client.ts:201-208` 组装、`:216-222` 尾截、`:44` 上限 16_000B）。

### Q3.2 出口前后具体改动

改造收敛在 `triage-client.ts` 单文件内，出口行 `:273` 本身几乎不动（`JSON.stringify` 直接接受对象）：

1. **新 `buildStructuredState(input)`**（放 `:201` `buildTriageState` 旁）：入参是**已提取的类型化字段**（枚举、int、相对路径数组、经 PM 生成的摘要串），不是自由文本 blob。返回判别联合：`{ ok: true, state: object } | { ok: false, missing: string[], oversize?: true }`。必需字段校验表 = Q5.1 的三 dp 集合；缺即 `ok:false`。
2. **新 `canonicalStateBytes(state)`**：Q2.2 TS 列（递归排序 + `JSON.stringify`）的唯一实现，供 Q1.4 计字节与未来测试向量复用。
3. **redact 在组装前完成**（Q3.3），出口只序列化一个"已经是干净的"对象。
4. **出口 `:273` 改为**：`input: JSON.stringify({ state: bounded.state, questions: DP1_QUESTIONS })`。注意：canonical 要求只约束 `state` 子对象（Python 侧 `json.loads` 后重排序再计字节/哈希，外层信封的键序与空白无关紧要），外层保持普通 `JSON.stringify`。
5. **体积检查在 `buildStructuredState` 内**（Q1.4 第二段），不放在 `:273` 行内——出口行保持"纯序列化"职责。
6. **失败上抛**：见 Q3.4。

### Q3.3 L2 剥离在哪一步做

**L2 不是"过滤出去"，是"从来没有入口"。** 两层防线：

- **第一层（结构性，主防线）**：`buildStructuredState` 的入参签名里没有 description 全文/代码/会话记录的位置。caller（`ui-bridge.ts:1432` 一带的改造点）从结构化产物提取字段：task.md 头（type/write_scope/card_sha256）、run.json（`shared/run-store.ts:31-53`）、trace 的 `[CHECKPOINT]` k=v 字段——摘要类字段是 PM **生成**的 ≤600B 文本，不是原文切片。schema 无 code 字段、无原话字段（RQ-4 证据 §3.1 L2 行"结构性排除"）。
- **第二层（值级脱敏，纵深防御）**：三个 L1 自由文本字段（`task_summary`/`ambiguity.question`/`failure.summary`）进对象前统一过 `redactSummary()`，规则复刻 RQ-4 证据 §3.2 并前置 Python 同款三类凭据模式（`decision.py:356-362` 的 env 后缀集合、`(?i)bearer\s+\S+`、`\bsk-[A-Za-z0-9._-]{6,}`；env 值字面量 longest-first 替换的实现参照 `decision.py:365-376` `_credential_values`/`_redact`）+ 盘符/UNC/用户目录剥离 + `relative_to(project_root)` 路径收缩 + host:port 白名单 + 邮箱占位。**脱敏作用于值，不作用于序列化后的 JSON 串**（对序列化串跑正则会误伤转义序列且可能产出非法 JSON），因此不存在"序列化→脱敏→重序列化"三步，只有"脱敏→组装→一次性 canonical 序列化"。
- Python 侧兜底：`decide()` 入口在 `_validate_input` 之后对 dict state 的三个 L1 字符串字段重跑一次 `_redact`（`decision.py:378-387`）——堵 spec.md:159 点名的"`_redact` 当前不覆盖 state"缺口的最小改法（`_redact` 本体不动，扩其调用面）。

### Q3.4 失败上抛的形态

- **TS 侧没有异常**：D-004 fail-soft 是硬规则（`triage-client.ts` 头注释"never throws"；`triageDispatch` 全函数 try/catch 兜底 `:196` `unavailable()`）。构造失败 → `unavailable("input-incomplete")` / `unavailable("input-oversize")`，**零 spawn、零写**（对齐 D-007 的 default-off 语义），DP-1 advisory 语义退回"无建议"，派发本身不受影响（头注释 AC-007：建议永不改写派发）。
- **Python 侧异常只有一条通道**：`DecisionInputError`（`decision.py:138-141`，注释明确这是唯一允许逃逸的异常）→ `mw.py:806-808` 捕获、stderr 打印、`return 2`。语义 = 调用方 bug，不是服务不可用（不落入 8 类 reason，`decision.py:88-99`）。

### Q3.5 mode=suggest 与 auto：同一份输入（必须相同）

必须相同，三个理由：

1. **机制上必然相同**：`mode` 不是请求参数——它活在 `.mw/decide.json` 的 points 配置里（DS-13，spec.md:62、`:126`；`dp set <dp> mode=suggest` 切换，spec.md:228），只在**答案返回之后**决定 `acted=true`（auto，答案生效）还是 `acted=false`（suggest，只落档+展示）。请求构造代码里根本没有 mode 这个变量。
2. **观察期有效性**：suggest 存在的意义是度量 jev 建议与人的分歧（spec.md:285 明确"不拿 advisory 数据做门控；要观察期就用 mode=suggest"）。若两种模式输入不同，分歧样本不可比，整期作废。
3. **档案关联**：`decision_id = "<dp>:<trigger_id>"`（spec.md §6.1 :170）与 `state_digest` 都假定同一决策在两种模式下是同一输入；输入不同 → digest 不同 → `kind=decide` 行无法与转 auto 后的决策对账。

实现约束随之而来：`buildStructuredState` **不接收 mode 参数**；两模式共享同一构造函数、同一出口、同一脱敏管线，这是"同输入"的结构保证而不是约定。

---

## Q4 L2 字段负向测试矩阵

### Q4.1 哪一侧能观测到真正的出站字节（回答卡片问题）

存在**两道出站边界**，两侧各测一道：

- **TS 侧 = 客户端出站（判定性测试面）**。`DecideRunner` 是显式注入缝（`triage-client.ts:167-169` "Injectable runner (tests stub this)"），stub 捕获的 `request.input` 就是 spawnSync 管道里发给子进程的**逐字节 stdin 载荷**（`triage-client.ts:172`）。L2 的承诺是"凭据永不离开客户端"（`decision.py:23-27` 硬规则"credentials never leave the client"），所以**规范边界在 TS 侧**：断言对象 = `request.input` 全文。
- **Python 侧 = 模型出站（纵深防御测试面）**。dict state 抵达模型的两条路：B2 `build_payload` 把 dict **原样**放进 API payload（`decision_backends.py:808` `state if isinstance(state, (str, dict, list)) else ...`）；llm-transitional 把 `_serialize_state(state)` 嵌进 user_content（`decision_backends.py:522-531`，`:527`）。对 `json.dumps(payload)` 断言同一组负向模式，防止未来有人在后端加 state 直通时破坏承诺；另测 `_redact` 对三个 L1 字段的入口兜底（Q3.3）。

### Q4.2 六类必测字段的构造输入与断言（全部断言在 canonical 后字节串上）

| # | 类别 | 构造输入（进入 builder 前的值） | 断言（对 request.input / payload 字节） |
| --- | --- | --- | --- |
| 1 | API key/token | 测试 env `PI_TEST_API_KEY="sk-live-abcdef1234567890"` + `task_summary` 内嵌该值 | 不含 `sk-live-abcdef`、不含 env 原值；含 `<redacted>`；注：env 值替换需 TS 侧读同一进程 env，测试内 set/restore |
| 2 | Bearer 串 | summary 含 `Authorization: Bearer eyJhbGci.eyJzdWIi.sig` | 不含 `eyJhbGci`；`Bearer <redacted>` 可在 |
| 3 | 绝对路径 | summary 含 `H:\git\Multi-Workers\packages\multi-workers\decision.py` 与 `C:\Users\wenbozhou\x` | 不匹配 `[A-Za-z]:[\\/]`、不匹配 `Users[\\/]`；至多含 `packages/multi-workers` 形态相对路径或 `decision.py` basename |
| 4 | 用户原话引号段 | description（builder **收不到**它——测试断言签名层）+ PM 摘要内嵌 `"请修复登录页 bug，账号 foo@example.com 密码 hunter2"` | (a) `buildStructuredState` 参数类型无 free-text blob 入口（编译期）；(b) 摘要中无 ≥15 连续词与原话重合（滑窗断言）；(c) 无 `hunter2`；`foo@example.com` → `<email>` |
| 5 | 源码片段 | 摘要误含 `function foo() { return 1; }` 多行块 | state 顶层键集 ⊆ schema 键白名单（无 code/snippet/diff 键）；字节串无 `function `、无 `=>`、无三连换行 |
| 6 | git remote/凭据 | summary 含 `https://user:ghp_token123@github.com/org/repo.git` | 不含 `ghp_token123`、不含 `user:`；host:port/URL 规则后至多 `github.com/org/repo` 形态 |

每类同时给 Python 侧镜像断言（对 `build_payload` 返回的 payload 跑同表）；env 值类（#1）在 Python 侧用 monkeypatch env。1/2/6 类即使在"TS 忘了脱敏"的最坏情况下，也会被 Python 入口 `_redact`（Q3.3 兜底）拦下——两侧测试共同覆盖这条双保险。

### Q4.3 测试落位

- TS：`packages/coding-agent/test/triage-dispatch.test.ts`（已存在，扩展之；runner 缝已有 stub 先例）。新增 describe 块逐类对应 Q4.2 表。
- Python：`packages/multi-workers/test_decide_backends.py`（payload 边界断言）+ `packages/multi-workers/test_decide.py`（`_validate_input` 结构化分支 + `_redact` 覆盖 state 字段的入口兜底）。

---

## Q5 输入不足路径（input-incomplete）

### Q5.1 各 dp 必需字段集合（缺一即拒）

**dp1（派发 triage）**：`v`、`dp`、`key`、`phase`、`task_type`、`requested_type`、`risk`、`risk_source`、`authority_tier`、`task_summary`、`questions_version`、`scope.write_scope`、`scope.ext`。可选：`task_key`、`scope.images_required`、`history.*`。

**dp2-checkpoint**：`v`、`dp`、`key`、`phase`、`task_type`、`risk`、`risk_source`、`authority_tier`、`questions_version`、`progress.elapsed_min`、`progress.budget_min`、`progress.phases_done`、`progress.phases_total`、`progress.artifact_present`。可选：`task_key`、`progress.writes/uniq_targets/repeat_top/last_land_age_min`、`history.*`。（dp2 无 task_summary、无 scope——RQ-4 证据 Q2 表 B 行。）

**dp3-clarify**：`v`、`dp`、`key`、`phase`、`task_type`、`risk`、`risk_source`、`authority_tier`、`task_summary`、`questions_version`、`ambiguity.kind`、`ambiguity.question`。可选：`task_key`、`history.*`。

"必需"的含义（对齐 RQ-4 证据 Q6 判定规则）：缺失、类型错、枚举越界、超 cap 四者等价，一律拒绝；可选字段缺失则整体省略、**禁止占位默认值**（不许 `risk:"low"` 兜底）。

### Q5.2 跨字段一致性校验（缺失即拒，两侧同规则）

- `authority_tier = "P0"` → 拒发（P0 永久人工，`pm-state.md:45` DS-1；构造侧短路，连 unavailable 都算多余路径之外的后备）；
- `failure.exit` 与 `failure.kind="exit-nonzero"` 必须同现；
- `progress.elapsed_min > progress.budget_min` → `risk` 不得为 `low`（机器口径 `computeRisk`，`worker-mode.ts:351-368`）。

### Q5.3 TS 拒发与 Python exit 2 的分工

| 门 | 位置 | 行为 | 语义 |
| --- | --- | --- | --- |
| 第一门 | `buildStructuredState`（TS） | `{ok:false, missing:[...]}` → `unavailable("input-incomplete")`，零 spawn | 我方数据没备齐，不上服务（spec.md:160 前半句） |
| 第二门 | `_validate_input` 结构化分支（`decision.py:778-812` 内，`:780-781` 的 None 检查之后加 dict 分支） | `raise DecisionInputError("state missing required field 'risk' for dp1")` → `mw.py:806-808` stderr + **exit 2** | 调用方 bug（含其他 CLI 调用者），不伪装成 unavailable |
| 第三门 | `decision.py:653-659` 预算 | `budget-exhausted`（不变） | 体积超后端上限 |

TS 缺字段清单进 reason 吗？不进——`reason` 字段受 8 类冻结枚举约束（`decision.py:88-99`、头注释"reason field only ever carries values from the frozen set"），TS 侧 reason 用新值 `input-incomplete` 只存在于 **TS 本地** unavailable 返回与台账 detail，不进 Python 响应解析路径（`triageDispatch` 对 `payload.reason` 的读取不受影响）。

### Q5.4 拒发留痕（留什么、写哪）

- **TS 侧**：写 `_autopilot` 台账行 `kind=triage-unavailable`（`ui-bridge.ts:270-274` 通道），detail：`dp=dp1 reason=input-incomplete missing=risk,scope.write_scope`——**只记字段名**（字段名是 L0 枚举），绝不记缺失处的上下文值。现有通道默认受 `triage_notify_on_unavailable` 门控（`ui-bridge.ts:258-259`）；**设计建议**：`input-incomplete`/`input-oversize` 属构造 bug 信号（与"服务挂了"不同类），建议这两类 reason **绕过开关强制留痕**，服务类 reason 维持现状门控。零扰动不受影响：jev 未配置项目根本不进 triage 路径（D-007 零 spawn）。此为设计决策点，交 design 评审裁定。
- **Python 侧**：exit 2 走 stderr（`mw.py:807`），**不写证据行**（`_emit` 只在 `decide()` 完成路径上，`DecisionInputError` 在其之前抛出）。审计依赖调用方对 stderr/exit code 的处置。
- **截断类**（Q1.5）：同台账行，`reason=input-oversize dropped=<字段名列表>`。

### Q5.5 如何避免"字段缺失 → 静默变成空字符串"

1. **类型层**：`buildStructuredState` 入参接口必填字段为非可选属性（TS 编译期缺即红）；可选项显式 `?`，缺省语义 = 整键省略，绝无 `?? ""` / `|| ""` 出口（review 用 grep 门：builder 文件禁 `?? ""`）。
2. **运行层**：builder 对每字段做显式 `typeof`/枚举成员/长度断言，失败聚合进 `missing[]`，一条不满足即整体 `ok:false`——不存在"部分填充照发"。
3. **契约层**：空串按"缺失"处理（`task_summary` trim 后为空 = missing），杜绝"空串洗白成合法值"。
4. **Python 镜像**：`_validate_input` dict 分支同样禁 `state.get(k, default)` 式取值——required 用 `k not in state` 判定，optional 缺失则跳过该键。

---

## Q6 兼容与零扰动

### Q6.1 旧字符串输入路径逐字节不变

分派规则只加在两处，均为**新增分支**，不改旧行为：

- `decision.py` `_validate_input`：`:780-781` 的 `state is None` 检查保持第一行；其后 `isinstance(state, str)` → legacy（现行为：除 None 外零校验，直接进 `_encode_state` 的 str 分支 `decision.py:405-406`）；`isinstance(state, dict)` → 结构化校验（Q5）；其余类型 → `DecisionInputError`（现状 dict/list 等会被静默接受，新行为收紧——对既有 TS 调用者无影响，它只发 str）。
- `mw.py` `_decide_read_request`：`route:716-719` 现在只查 payload 是 dict 且含 `state`/`questions` 键；**新增值类型检查** `state` ∈ {str, dict}，其余 exit 2。请求外层 shape 不加新键（required-key 检查 `:718` 不动），旧调用者发 `{state: "<str>", questions: {...}}` 走的代码路径与今日完全一致。
- TS 侧 `buildTriageState`（`:201-208`）与 `boundTriageState`（`:216-222`）**保留不删**，字符串路径（及任何还在用 `TriageRunInput.state: string` 的调用者）行为不变；`_serialize_state` 的 str 分支（`decision_backends.py:326-327`）同理。

### Q6.2 max_state_bytes=16384 与新 2000B 的关系

**两个都生效，管不同的门**：

- `max_state_bytes=16384`（`decision.py:244`）= 服务端后门上限，**不动**。两条路径都受它约束（`decision.py:653-659` 对 `_encode_state` 字节统一检查）：legacy 可到 16384（现状）；结构化 canonical 恒 ≤2000 < 16384，永不触线。配置覆盖 `max_state_bytes` 的能力保留。
- 新 TS 常量（如 `MAX_STRUCTURED_STATE_BYTES = 2_000`）= 客户端结构化构造预算（Q1），只在 `buildStructuredState` 内生效；`MAX_TRIAGE_STATE_BYTES = 16_000`（`triage-client.ts:44`）**保留**给 legacy 字符串路径。
- 结论：旧路径仍允许 16KB；新路径以 2000B 为构造上限、16384 为永远够不着的服务端保险。spec.md:157 "canonical JSON ≤2000B" 由 Q1.3 的按构造封顶实现。

### Q6.3 未配置 jev 项目 doctor 输出逐字节不变的验证方法

不变性依据（实读）：`_doctor_decide`（`mw_common.py:1645-1698`）对缺失 `.mw/decide.json` 早退返回**恰好** `{"exists": False}`（`:1664-1666`）；`format_doctor_text` 只在 `decide_section.get("exists")` 为真时才输出 `triage:` 行（`mw_common.py:4590-4591`，注释 `:4588` "silent unless .mw/decide.json exists"；docstring `:1648-1650` 把"历史 doctor 文本逐字节不变"钉为零扰动规则）。本设计改动的面（`_validate_input` dict 分支、`_encode_state` dict 分支参数、triage-client.ts）不在该路径的 import 依赖上（早退只做 `decide_config_path(root)` 的 exists 检查）。`cmd_doctor`（`mw.py:609-660`）本体无写操作（实读扫 write/open/mkdir 0 命中），不带 `--fix` 为纯只读。

验证方法（三步，前两步按字节，第三步进 CI）：

1. **基线捕获**（改动前，临时目录建一个有 `.agenticdoc/` 骨架但无 `.mw/` 的项目）：
   `python -X utf8 -c "import subprocess,hashlib; out=subprocess.run(['python','-X','utf8','packages/multi-workers/mw.py','doctor','--project','<scratch>'],capture_output=True).stdout; print(hashlib.sha256(out).hexdigest(), len(out))"`
   同法再取 `--json` 形态的哈希（两个形态都钉）。
2. **改动后复跑**：同一 scratch 项目、同一命令，比对两个哈希——不相等即零扰动破坏。（PowerShell 下勿用 `>` 重定向比对——PS 5.1 默认 UTF-16 会污染字节口径，一律在进程内取 stdout 字节。）
3. **回归测试钉死**：扩展 `packages/multi-workers/test/test_write_face_doctor.py`：断言 `doctor_report(scratch)["decide"] == {"exists": False}` 且 `"triage:" not in format_doctor_text(report)`，另加整份 doctor 文本的 golden 快照比对。该测试把 `_doctor_decide` 的早退契约从注释升格为被测行为。

---

## 结论

- Q1：RQ-4 草案已细化为 28 行字段表（字段/类型/必填/L 级/字节预算）；dp1 实例 706B（余量 65%），per-dp 最坏 dp1=1397B / dp2=580B / dp3=1363B，2000B 上限**按构造成立**；超限走"可选 L1 固定优先级丢弃 → 必需 L1 半额收缩 → 仍超拒发"两段式，留痕走 `triage-unavailable` 台账行只记字段名。
- Q2：**推荐 Python 单点算 digest**（`sha256(canonical)[:16]`，canonical=sort_keys+compact separators+ensure_ascii=False），响应加 `state_digest` 回传，TS 零哈希依赖；若双侧各算，须钉死 Q2.2 七项参数（关键：`decision.py:410` 必须显式 `separators=(",", ":")`，现状默认带空格）；测试向量 `d428504f067a5092` 已在本机 Python+Node 双侧实算通过，现状参数反证 digest=`a4e0ddff7ed8a2e0`（向量当场红）。
- Q3：出口 `:273` 保持纯序列化；L2 靠"构造签名无入口"（主）+ 三个 L1 字段过 `redactSummary()`（纵深，前置 `decision.py:356-376` 同款凭据规则）双防线；脱敏作用于值不作用于序列化串；失败走 `unavailable()` 零异常（TS）/`DecisionInputError` exit 2（Python）；suggest 与 auto **结构上共享**同一构造函数与出口，mode 只在答案返回后生效。
- Q4：负向测试双面落位——TS `DecideRunner` 缝捕获的 stdin 字节是**判定性**边界（"永不离开客户端"），Python `build_payload`（`decision_backends.py:808`/`:527`）是**纵深**边界；六类 L2 构造输入与逐条断言见 Q4.2 表。
- Q5：dp1/dp2/dp3 必需字段集合逐项列出（13/14/12 项）；TS 第一门拒发零 spawn、Python 第二门 exit 2、语义分离（数据没备齐 vs 调用方 bug）；留痕只记字段名；禁静默空串靠类型层（非可选属性）+ 运行层（显式断言，禁 `?? ""`）+ 契约层（空串=缺失）三层。
- Q6：旧 str 输入的兼容面收敛为两处新增分支（`decision.py:780-781` 后、`mw.py:716-719`）；16384 与 2000B 双上限并存各管一门；doctor 零扰动依据 `_doctor_decide` 早退契约（`mw_common.py:1664-1666`+`:4590-4591`），验证 = 双形态 stdout 字节哈希前后比对 + golden 测试钉死。

## 证据

- 实算产物（2026-10-19 本机，Python 3.14.0 / Node v22，scratch 脚本已删）：dp1 示例 706B / digest `b8d767f1d8f3b187`；Q2.3 向量 canonical 157B、sha256 全长 `d428504f067a509291c57a3a73910f62e4287219a4cb52b7ee22534828663843`、digest `d428504f067a5092`（双侧一致）；现状参数 digest `a4e0ddff7ed8a2e0`（漂移反证）；per-dp 最坏 1397/580/1363B；全区块病态组合 2625B（超限反证）。
- 逐条实读行号：`triage-client.ts` :39/:44/:55-58/:167-169/:172/:196/:201-208/:216-222/:273/:319/:327/:340；`ui-bridge.ts` :236/:244/:258-274/:1429-1436（`:1432`）；`decision.py` :88-99/:105/:121-136/:138-141/:23-27/:241-245/:244/:356-362/:365-376/:378-387/:391-397/:402-414/:653-659/:778-812；`mw.py` :694-721（:716-719）/:795-813（:806-808, :809-810）/:609-660（无写操作）；`decision_backends.py` :325-331/:522-531/:805-810；`mw_common.py` :1645-1698（:1664-1666）/:4588-4600（:4590-4591）；`spec.md` :156-162/:167-176（:168/:170）。
- 测试落位实证：`packages/coding-agent/test/triage-dispatch.test.ts` 已存在；`packages/multi-workers/{test_decide,test_decide_backends,test_decide_cli}.py` 已存在；`packages/multi-workers/test/test_write_face_doctor.py` 已存在。
- 无引用风险实证：`_encode_state` 全仓唯一 caller=`decision.py:653`，无测试钉其字节（rg 0 命中）。

## 残留与未验证

- dp4/dp5/dp6/dp13 的最坏字节数是构造推算（≤900B/≤700B 量级），未逐字节实算；dp1/dp2/dp3 为实算。落地时应在 builder 单测里对全部 7 个 dp 各钉一个满额向量。
- Q5.4 的"`input-incomplete` 绕过 `triage_notify_on_unavailable` 开关强制留痕"是设计建议，与现有"不可用默认静默"语义（`ui-bridge.ts:258-259`）存在张力，需 design 评审裁定。
- `mw decide run` 响应加 `state_digest` 键（Q2.1 第 3 点）会改变响应 JSON 形状，未验证是否有消费方对响应键集做严格相等断言（TS 侧 `triageDispatch` 只按需取键，`triage-client.ts:283-309`，无严格键集断言；但 `mw.py --json` 的其他调用者未逐一排查）。
- `decision.py:780-781` 后新增"非 str 非 dict → 报错"对**现有程序化调用者**（若有测试直接传 dict/list 给 `decide()`）是行为收紧，未全量排查 `test_decide*.py` 中的 dict 直传用例；落地时需先跑该测试组。
- doctor 字节哈希前后比对（Q6.3 步骤 1/2）未实际执行——本任务禁改源码，方法已在文内给全，待实现卡片执行。
- TS 侧 `redactSummary()` 的 env 值替换需读进程 env（对齐 `decision.py:365-376` 语义），其实现细节（缓存、length≥8 门槛）未在本设计中展开，归实现卡片。

## 上下文来源

- 卡片：`tasks/D6-input-redaction.md`（card_sha256 ae44a21f…，envelope agent-team-loop-pm@0.83.0）
- 上游证据：`.agenticdoc/mw-decision-substitution/evidence/research/spec-structured-input-contract-20261016.md`（RQ-4：schema 草案、三级敏感度、8 条脱敏规则——Q1/Q3/Q4 直接引用）
- 规范：`.agenticdoc/mw-decision-substitution/spec.md` §5.4（:156-162 输入契约）、§6.1（:167-176 决策档案）、DS-13（:62 mode 语义）、AC-015（:228）
- 源码（实读）：`pm/triage-client.ts`、`pm/ui-bridge.ts`、`decision.py`、`mw.py`、`mw_common.py`、`decision_backends.py`
- 本机双侧实算：scratch Python/Node 脚本（已删除，命令与数值复现于 Q1.2/Q1.3/Q2.3/Q2.4 正文）

Q-answered: 6/6
