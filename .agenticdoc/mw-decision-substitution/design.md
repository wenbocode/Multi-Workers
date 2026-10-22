# Design — 用 jev 替换中低风险人工决策（mw-decision-substitution）

> 相位 DESIGN 定稿 · 依据 spec rev3（AC-001..015）+ 6 束设计调研（D1–D6）· 2026-10-20
> 底座：`mw-jev-provider-integration`（DONE，`decision.py` / `decision_backends.py` / `mw decide` CLI / DP-1）

## 0. 并行性分析（先定边界，再拆波次）

**必须串行的三处**

| 串行点 | 理由 |
| --- | --- |
| 配置表 schema → 所有读配置的组件 | 字段名/语义一改，Python 与 TS 两侧同时失效 |
| 档案行契约 → 报告器 / 签收 / 门禁 | 报告与门禁消费 `fold` 输出，契约变了统计口径就变 |
| `decide_for` 控制流 → 所有执行面插入 | 插入点只负责"何时问"，怎么答由控制流定义 |

**可并行的四组**（文件互不重叠）

```
A 组（Python 基础面）  W1 注册表+配置表+CLI   ∥   W2 档案写入器+fold
B 组（TS 输入面）      W3 triage-client 改造 + ask_decision 工具
C 组（执行面）         W4 dp3 插入 ∥ dp2 收窄（同包不同文件，PM 可并行派）
D 组（收尾面）         W5 关联+报告+签收+门禁+写守卫   →   W6 文档+全量验证
```

依赖：`A → C`（C 调 `decide_for`）、`B → C`（C 用工具返回值）、`A+W2 → D`。W3 可与 W1/W2 同时开工，因为 `dp` id 与 CLI 契约在 §2 已冻结。

**风险最高的一步**：W4 的 dp3 插入（改 worker 终态路径）。它必须在 W1/W2/W3 全部合入后再动，且先跑"关闭态字节同构"回归。

## 1. 架构总览

```
            ┌──────────────── 配置表 .mw/decide-points.json（唯一授权，热重载）
            │                        │
   mw decide dp on/off/set ──────────┤（人）
   LLM 建议（报告/对话，不写配置）────┘
            │
            ▼
  packages/multi-workers/decision_points.py     ← 24 个 DecisionPoint 注册表（唯一权威）
            │  decide_for(dp_id, trigger)
            ▼
   enabled? ──no──► escalate(human) ［零 spawn，字节同构］
            │yes
            ▼
   build_state(≤2000B, L0/L1 only) ──► decision.py DecisionClient ──► 后端 B1/B2/B3
            │                                                        │
            │◄────── answers + digest(sha16, Python 单点算) ──────────┘
            ▼
   mode=suggest ──► 档案行(acted=false) + 展示建议
   mode=auto    ──► 执行器 → acted=true, actual_action → 档案行
            │
            ▼
  decide_archive.py → decisions.jsonl（4 类行，哈希链，单写者）
            │
            ▼  fold(decision_id)
  phase 末报告（advance_phase 推进后自动）＋ 收尾签收 sign-final.md → dp apply → authority-change
```

## 2. 冻结接口

### 2.1 注册表（`packages/multi-workers/decision_points.py`）

```python
@dataclass(frozen=True)
class DecisionPoint:
    id: str                      # "dp3-worker-clarify"（唯一，稳定，禁改）
    tier: str                    # "P0" | "P1" | "P2"
    default_enabled: bool        # P2=True，P1/P0=False
    default_mode: str            # "auto"
    questions: tuple[dict, ...]  # 问题集（TS 不再持有字面量）
    build_state: Callable[[Trigger], dict]   # 产出 L0/L1 字段
    executor: Callable[[dict, Trigger], str] | None  # 返回 actual_action；None=不可自动执行
    questions_version: str       # 内容哈希短码，问题集变更即变
    p0_consequences: str | None  # P0 必填：打开后会发生什么（人大声确认时展示）
    description: str
```
- **import 期 fail-loud**：id 重复、tier 非法、P0 缺 `p0_consequences`、P2 缺 `executor` 一律抛错。
- TS 侧只持 id 常量；CI 测试断言 `TS 常量集合 ⊆ DP_REGISTRY`（防漂移）。`DP1_QUESTIONS` 字面量删除。

### 2.2 配置表（`.mw/decide-points.json`）

```json
{ "version": 1, "updated_at": "...", "updated_by": "human",
  "points": { "dp3-worker-clarify": { "tier": "P2", "enabled": true, "mode": "auto", "note": "" } } }
```
- **读侧 8 层降级**：L0 文件缺失→全默认；L1 JSON 语法错→全默认+doctor；L2 行非对象→该 dp 关；L3 字段类型错→该 dp 关；L4 `tier` 非法→沿用注册表 tier；L5 `enabled` 非 bool→关；L6 未知 dp→保留并标 `orphaned`；L7 `tier` 与注册表冲突→以注册表 tier 为准 + warning。
- **热重载**：进程内缓存以 `(st_mtime_ns, st_size)` 双签名为键；命中即用；未命中重读。读侧无锁（写侧 `os.replace` 原子换 inode）。Windows FAT 2s 粒度风险 → 写侧显式 `os.utime(ns=)`，测试用该方式制造"同秒改动"。
- **写协议**：复用 `_decide_write_config` 的 锁 + tmp + `os.replace`（`mw.py:772-792`）。

### 2.3 `decide_for` 控制流（11 步）

| # | 判定 | 出口 |
| --- | --- | --- |
| 1 | dp 不在注册表 | exit 2（未知 id 大声失败） |
| 2 | 配置行 `enabled=false` 或缺失且默认关 | `escalate(human, "disabled")`，**在 `_encode_state`/`_resolve_backend` 之前**返回 |
| 3 | `mode=suggest`/`auto` 读取并与注册表校验 | — |
| 4 | 预算/可用性（`budget-exhausted`、`disabled`） | `escalate("unavailable")` |
| 5 | `build_state` 产出字段 → 必需字段缺失 | `escalate("input-incomplete")`（TS 侧同判定，双保险） |
| 6 | 序列化体积 > 2000B | 丢可选 L1 → 必需 L1 减半 → 拒发 `input-oversize`（TS 本地原因） |
| 7 | 调 `DecisionClient`（async spawn，20s 硬超时） | `available=false` → `escalate("unavailable")` |
| 8 | `confidence_source == api` 且 `confidence < 阈值`；或 `answer` 为空/缺 qid/值非法 | `escalate("low-confidence")`。**`confidence_source != api` 时忽略置信值，不门控** |
| 9 | `mode=suggest` | 落 `decide` 行 `acted=false` + 返回建议 |
| 10 | `mode=auto` 且 `executor` 存在 | 执行 → `acted=true` + `actual_action` |
| 11 | 执行器抛错 | `escalate("over-authority")` + 落 `acted=false` 行 |

### 2.4 档案行契约（`.agenticdoc/_autopilot/decisions.jsonl`）

| kind | 必填 | 说明 |
| --- | --- | --- |
| `decide` | `seq/prev_sha/decision_id/ts/dp/key/state_digest/questions_version/available/authority/acted`；`available=true` 时 `answer`；`acted=true` 时 `actual_action` | `outcome` 恒 `pending` |
| `override` | `decision_id/override_by/override_reason` | 不回写 decide 行 |
| `settle` | `decision_id/outcome/settled_by`；`outcome=pending` 时 `note` 必填 | 取最后一条生效 |
| `authority-change` | `dp/by/change`；`by ∈ {human, human:p0-confirm, signoff:continue|narrow|revoke, refresh}` | **按 dp 展开一行一个** |

`decision_id = "<dp>:<trigger_id>"`；`prev_sha` = 上一可解析行 canonical JSON 的 sha256 前 16（首行 `"0"*16`）；`state_digest = sha256(_encode_state(state))[:16]`。

### 2.5 CLI（`mw decide dp ...`，挂在 `decide_sub` 下，`mw.py:7508`）

| 命令 | 行为 | exit |
| --- | --- | --- |
| `dp list [--json]` | 全部 dp：id/tier/enabled/mode/来源(default|config)/orphaned/P0-ON | 0 |
| `dp show <dp>` | 单点详情 + 最近 N 条档案行 | 0 / 2 未知 |
| `dp on <dp> [--i-understand-p0]` | 写 enabled=true；P0 缺 flag → 2 且 **配置 sha256 不变** | 0 / 2 |
| `dp off <dp>` | 写 enabled=false | 0 |
| `dp set <dp> <key>=<value>` | key ∈ `tier|enabled|mode|note` | 0 / 2 |
| `dp refresh` | 注册表→配置表单向合并：补缺失行、不动已有、标 orphaned、**无变化不写文件** | 0 |
| `dp check` | 体检：坏行/孤儿/tier 冲突/orphan 行/未注册 id；人读 + `--json` | 0 干净 / 1 warning / 2 error |
| `dp apply <sign-file>` | 全量校验→单锁内原子写；agent 会话内拒绝 | 0 / 2 |

### 2.6 TS 侧

- `pm/triage-client.ts`：入参从"整份 state 字符串"改为 `(dpId, stateObj)`；出口 `:273` 保持纯序列化；新增 `input-incomplete` 拒发路径（零 spawn）；保留 20s 硬超时与 `available=false` 归一化；digest 由 Python 回传，TS 不算。
- 新增 `pm/decision-tool.ts`：`ask_decision` 工具（`pi.registerTool` + TypeBox），**仅 worker 分支注册**，经 `activeToolsForType` 全角色追加，**不进 `TOOL_ALLOWLISTS`**；失败一律 `throw`（`AgentToolResult` 无 `isError`，`packages/agent/src/types.ts:355-368`）。
- `tool_call` 钩子：只做**同步快判定**（查配置 + 返回 `{block:true, reason}`），**不起子进程**；Python 往返只在 `ask_decision.execute` 内 async spawn。block 落地 `packages/agent/src/agent-loop.ts:636-641`。
- 反重试：`reason` 里给出路（"应改为询问用户"）+ turn 级熔断 + trace 行。
- `xkey-gate-guard` 模式新增写守卫：目标 `evidence/review/sign-final.md`（fragment 匹配，含反斜杠/相对拼写）与 `.mw/decide-points.json`；写动词/重定向/PowerShell 正则复用既有族。

### 2.7 文件契约汇总

| 路径 | 生产者 | 消费者 |
| --- | --- | --- |
| `.mw/decide-points.json` | 人（CLI / 手改） | Python 读侧、TS 读侧、doctor |
| `.agenticdoc/_autopilot/decisions.jsonl` | `decide_archive.py`（单写者） | 报告器、`mw decide dp show`、doctor |
| `.agenticdoc/_autopilot/triage-decisions.jsonl` | 底座 `decision.py`（既有） | `mw decide show`（不变） |
| `task.md` 头 `decision:` 行 | PM（仅 `acted=true` 时） | settle 追加点、档案反查 |
| `evidence/review/decision-review-<phase>-<yyyymmdd-hhmm>.md` | 报告器 | 人 |
| `evidence/review/sign-final.md` | **人** | `dp apply`、done 门禁 |

## 3. 设计决策

| 编号 | 决策 | 依据 |
| --- | --- | --- |
| D-001 | 配置表唯一授权；`enabled/mode` 两列 | 用户唯配置论（DS-9） |
| D-002 | 注册表 Python 唯一权威；TS 只持 id + 一致性测试 | D1 Q1（避免双写问题集） |
| D-003 | `enabled=false` 在 `_encode_state`/`_resolve_backend` **之前**返回 | D1 Q2；可用 `FakeBackend.calls==0` 断言 AC-001 |
| D-004 | `state_digest` 由 **Python 单点计算并随响应回传**，TS 零哈希 | D6 Q2（实测两种分隔符产出不同值 `d428504f...` vs `a4e0ddff...`） |
| D-005 | 档案 **fail-loud**（抛→exit 2 上抛人），与传输行 best-effort 分道 | D2 S0（档案是正确性依赖） |
| D-006 | `authority-change` 按 dp 展开多行 | D2 S1（保住 `<dp>:<trigger_id>` 文法） |
| D-007 | `settle` 允许 `outcome=pending` 登记行，`note` 必填 | D2 S2（`lost`/NC 有显式落点） |
| D-008 | 哈希链取**规范形**（canonical JSON），非逐字节 | D2 S3 |
| D-009 | dp3 插入点 = `finishSuccess` 内 `exitCode` 判定(`:3664`) 与 `writeOutputGuarded`(`:3671`) 之间 | D3 Q1（实测贯通；6 个候选点被否决） |
| D-010 | dp3 注入 = `sendUserMessage(followUp)` + `[mw dp3-answer]` 机器前缀；指标双计 `nc_raw`/`nc_human` | D3 Q3（防 17.4% 被读成 0%） |
| D-011 | dp2 `auto` **只允许"收窄"**；拆/直执必须人 | D3 Q5（其余三种在改目标或扩大授权面） |
| D-012 | `decision:` 头行**仅当 `acted=true`** 注入 | D5 Q1（否则 settle 会错记到未生效建议） |
| D-013 | settle 幂等 = 最后一条生效 + `(decision_id,outcome,run_id)` 去重 + `rollback` 必须晚于 `ok` | D5 Q2 |
| D-014 | 签收文件固定名 `sign-final.md`，门禁用**现成** `content_match` | D5 Q5（`content_match` 对含 `*` 的路径恒 False，spec 原写法不可行） |
| D-015 | 新增 `tool_call` 写守卫覆盖 `sign-final.md` 与 `.mw/decide-points.json` | D5 Q6（`:666-687` 只是审计计数器，不是写守卫） |
| D-016 | `dp apply` 在 `PI_CODING_AGENT`/`AI_AGENT`/`PI_WORKER_TASK` 存在时 exit 2 | D5 Q6（PM 无专属标记，用"有 agent 无 worker"推断） |
| D-017 | 钩子只做同步快判定；Python 往返只在 tool execute（async spawn + 20s） | D4 Q3（钩子每轮可能触发，禁子进程） |
| D-018 | 档案锁内覆盖"读尾→sha→追加"并做尺寸复核；半行尾保留不 truncate | D2 Q2 |
| D-019 | 输入 ≤2000B 两段式截断；L2 靠**构造签名无入口**（不是事后清洗） | D6 Q1/Q3 |
| D-020 | 报告挂 `advance_phase` 推进成功后生成；`N<5` 强制"数据不足，不结论" | D5 Q3 |
| D-021 | `input-incomplete` 落档案行 + 回执一行，但不弹告警（告警只在 doctor 汇总） | PM 裁定（DS-4：上抛人是动作不是噪声） |
| D-022 | `dp refresh` 无变化时**不写文件**（保 mtime）；第二次 `added=0` | D1 Q6 |
| D-023 | `trigger_id` **允许含 `:`**，`decision_id` 按**首个** `:` 切分（推翻 D2 Q1.3 的"不含冒号"假设） | T-03 实现事实：`authority-change` 用 ISO ts 作 trigger 必含 `:` |
| D-024 | 档案行**不实现 `evidence_sha`**，只存 `evidence_line` | 契约优先：不加未入表的字段 |
| D-025 | 身份文法：`human` 或 `human:<account>`；`agent:*`/`pm`/`worker` 一律拒 | T-03 `_is_human_identity` |
| D-026 | `questions_version = q-<8 hex>`、`config_sha_after = 16 hex` 强校验 | 已注入 T-02 卡契约补充 |
| D-027 | 请求缺 `questions` 时由 `mw decide run --dp <id>` 从 `DP_REGISTRY` 解析并填充；两者都缺或 dp 不一致 → exit 2 | T-04 实测：现行 `mw.py:718` 强制 `questions`，结构化路径 rc=2 |
| D-028 | 超限拒发用 TS 本地原因 `input-oversize`（与 `input-incomplete` 区分），不进入 Python 冻结的 8 值 reason 集 | T-04 实现；design §2.3 第 6 步原写 `input-incomplete` 作废 |
| D-029 | `dp13-commit-release` 取 **P0**（发布/版本号不可逆）；落位 P2=9 / P1=5 / P0=10 = 24 | T-01 残留 1；spec §4 原复合值 `P1/P0` 与“P2=9/P1=6/P0=9=24”自相矛盾 |
| D-030 | `escalated_reason` 单一词表：`{disabled, unavailable, input-incomplete, input-oversize, low-confidence, over-authority, p0}`；`input-invalid` 仅供读取旧行 | T-01 残留 3（映射表会把 `disabled` 伪装成 `unavailable`） |
| D-046 | `box` 是 TypeSafe 的**图像定位题**（答案 `{top,bottom,left,right}` 归一化坐标，需 `TypeSafe-Danger-Zone-Images: true` + 图像 `assets`），Jev 无自由文本题型；文本决策请求含 `box` 时后端在凭据/HTTP 之前返回 `available=false, reason="box-requires-image"`，该值并入 Python `REASON_CODES`（第 9 值），不再被客户端归一成 `upstream-error` | FIX-G 曾把 `box` 实现成自由文本（与官方契约相反），FIX-H 撤销；同时 `score` 答案按官方为**浮点**（示例 `1.7`）；依据 `https://api.typesafe.ai/api/system-one.md`（2026-10-20 抓取） |
| D-047 | jev 的传输不是聊天协议：`packages/ai` 新增 api `typesafe-systemone`（`POST <baseUrl>/v1/systemone`，body 只 `{model, state, questions}`，Bearer 鉴权，一次性 JSON，无流式无文本生成）；timi provider 在构造 models 时**仅对 `jev-latest` 覆写** `api: "typesafe-systemone"`（目录数据 `generate-models.ts` 仍写 anthropic-messages，留待下次目录刷新）。输入约定：最后一条 user 消息必须是 `{state, questions}` JSON，否则 fail loud、零请求 | FIX-K。**真调用仍不可达**：llmproxy 对 `/v1/systemone` 及 9 条变体全 404（2026-10-20 复测），`/v1/messages` 上 jev 持续 429；需网关补路由，或改用 typesafe 凭据直连 B3 |
| D-031 | 步 8 语义修正：`confidence_source != api` 时 **忽略置信值、不门控也不上抛**，按配置执行；只有“无可使用答案”才 `low-confidence` | **关键**：B2 后端返回 `model-self-report`，若一律上抛则 P2 自动决策永不生效，整个特性空转 |
| D-032 | `decide_for` 调 `append_decide` 用 `duplicate="existing"`（重放）+ `note=duplicate-replay`，不抛异常不加新 escalate 值 | T-01 残留 5（worker 重试不应因幂等冲突崩掉） |
| D-033 | `questions_version` 取 `q-<8hex>`（与档案校验对齐） | T-01 残留 2 / D-026 |
| D-034 | 无可使用答案时落 `available=false` + `reason=bad-response` + `answer=None`；同一条不得既 `available=true` 又无答案 | T-01b 残留 3（坏答案不能当答案落盘） |
| D-035 | `decide_for(..., intent="answer")`：跳过 executor（步 10/11），仍落 `acted=false` 档案行并回传 `decision_id`/`mode`；`intent="act"` 行为不变 | T-05 残留 2：`ask_decision` 要的是「答案」不是「执行」 |
| D-036 | **单一权威**：`mw decide run` 必须走 `decide_for`；TS 只消费 `mode/acted/decision_id`，**不得自行镜像配置表推导授权** | T-05 已出现 TS 镜像（`decision-tool.ts:236`）；两处漂移即静默错配（违反 DS-9） |
| D-038 | dp2 收窄 steer 文件**必须有消费者**：worker 侧 `before_agent_start` + settle 双查消费、消费后写 marker 幂等，PM 侧终态回退 `deliverPmAlert([dp2-narrow-fallback])` | T-07 残留 1：`steer-dp2.md` 写出后无读者 ⇒ 整条 dp2 自动收窄 fail-open |
| D-041 | **`acted` 是消费侧事实**：由执行点（采纳该答案的地方）显式给出，不得由 `mode` 反推、不得读配置表推导。dp1 `dispatchDecisionOf` / dp2 `appendDp2ActedTrace` / dp3 注入点是三个消费点 | T-08 残留 2：`acted` 由 `mode==="auto"` 反推会让模型把「已授权」当事实（`ask_decision` 曾如此，QG MAJOR-1 已回收） |

> **编号说明（QG MINOR-6 回填）**：本 key 的契约表实际正文为 D-001..D-036 + D-038 + D-041。D-037 / D-039 / D-040 / D-042 是裁定编号分配后**未形成独立契约正文**的号（内容被 D-036/D-038/D-041 与对应任务卡吸收），编号不复用；任何引用「D-001..D-042」的卡片/注释均以本表为准。

## 4. 波次拆分

| 波次 | 内容 | 写面 | 依赖 | 验收 |
| --- | --- | --- | --- | --- |
| **W1** | `decision_points.py`（24 项注册表 + 校验）、配置表读侧 8 层降级 + `(mtime,size)` 热重载、`decide_for` 11 步、`dp` CLI（list/show/on/off/set/refresh/check）、`test_decision_points.py` | `packages/multi-workers/decision_points.py`、`mw.py`（`dp` 子命令段）、`test_decision_points.py` | — | pytest 全绿；`FakeBackend.calls==0` 断言；P0 缺 flag 时配置 sha256 不变 |
| **W2** | `decide_archive.py`（4 类行 + 链 + 幂等 + fold）、`test_decide_archive.py` | 新文件 + 测试 | — | 链校验、半行尾、重复 decide 拒绝、fold 合并 |
| **W3** | `triage-client.ts` 改造（dpId/≤2KB/`input-incomplete`/digest 回传）、`decision-tool.ts`（`ask_decision`）、工具注册接线、TS 测试 | `pm/triage-client.ts`、`pm/decision-tool.ts`、`index.ts`、`test/suite/*.ts` | §2 冻结契约 | TS 测试绿；stdin 字节断言 L2 不外发 |
| **W4** | dp3 插入（`worker-mode.ts`）、dp2 收窄（`pm-orchestrator.ts`）、`nc_raw`/`nc_human` 计数 | `worker/worker-mode.ts`、`pm/pm-orchestrator.ts`、`worker/heartbeat.ts`(如需) | W1+W2+W3 | 关闭态字节同构回归；NC 四面一致；checkpoint 一次界 |
| **W5** | `decision:` 头行、settle 追加、报告生成、`sign-final.md` 门禁两条、`dp apply`、写守卫 | `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`、`mw.py`、`xkey-gate-guard.ts`、`advance_phase.py` | W1+W2 | 门禁缺签收时 fail；三种 conclusion 各写 authority-change |
| **W6** | 文档（README + `docs/decision-substitution.md`）、CHANGELOG、全量验证、度量基线复核 | 文档 + 证据 | 全部 | 全量 pytest / test.sh；基线 93.3min 复核 |

**并行执行序**：`W1 ∥ W2 ∥ W3` → `W4 ∥ W5` → `W6`。

## 5. 测试矩阵

| 层 | 覆盖 | 位置 |
| --- | --- | --- |
| Python 执行器 | Python 卡一律 `python -m pytest <file> -q`；TS 卡才用 vitest（T-03 已暴露卡片缺陷，已批量修正） | `packages/multi-workers` |
| 注册表/配置 | 24 项完整性、8 层降级、热重载（同秒改动）、P0 flag、refresh 幂等 | Python |
| 控制流 | 11 步分支、`escalated_reason` 9 值、零 spawn 断言 | Python（FakeBackend） |
| 档案 | 4 类行、链断裂检测、半行尾、并发锁、幂等、fold | Python |
| 输入/脱敏 | ≤2000B 实测、两段式截断、L2 六类不外发（stdin 字节）、digest 向量 | TS + Python |
| 工具/钩子 | 四模式可用性、block 落地、反重试熔断、失败→上抛 | TS suite |
| 执行面 | dp3 插入五不变量、dp2 只收窄、nc_raw/nc_human | TS suite + 真实 run |
| 关联/签收 | 6 终态映射、`decision:` 仅 acted、门禁两条、`dp apply` 拒绝 agent 会话 | Python + TS |
| 端到端 | 关闭态逐字节同构、开启态一次真实 dp3 自答 | 手工 + 证据文件 |

## 6. 风险与回退

| 风险 | 缓和 | 回退 |
| --- | --- | --- |
| dp3 插入破坏 worker 终态路径 | 关闭态字节同构回归 + 五不变量 | `dp off dp3-worker-clarify` 即回原路径 |
| 配置表被 agent 写 | `tool_call` 写守卫 + `dp apply` 拒绝 agent 会话 + grep 审计 | 配置进 git 可 diff |
| 钩子里做重活拖慢每轮 | D-017 硬约束 + 单测断言钩子内无 spawn | 移除钩子，仅留工具 |
| 2KB 上限导致输入不足 | 两段式截断 + `input-incomplete` 上抛（不猜） | 提高上限需改 spec |
| settle 错关联 | 只在 `acted=true` 注入 + 三元组去重 + `note=composite` | 停用自动结算，转人工标注 |
| 签收门禁误伤 | 门禁只验存在与格式，不提内容 | 临时手写 `sign-final.md` |
| `content_match` glob 陷阱 | D-014 固定文件名 | 若需多文件，另立 `glob_content_match` |

## 7. 需规避坑点（继承 spec §13 + 本轮新增）

| 坑 | 规避 |
| --- | --- |
| **`agent-loop.ts` 在 `packages/agent/src`**（不是 coding-agent） | design/实现一律按此路径 |
| `content_match` 对含 `*` 路径恒 False（`advance_phase.py:195/223` 的 `is_file()`） | 固定文件名 `sign-final.md` |
| `AgentToolResult` 无 `isError` | 失败一律 `throw` |
| 钩子里 spawn 子进程 | 只同步判定；往返放 tool execute |
| `pm-orchestrator.ts:666-687` 是审计计数器 | 写守卫另注册 `tool_call` 钩子 |
| `decision:` 在 `mode=suggest` 时注入 | 仅 `acted=true` 时注入 |
| 锚点漂移（已 3 次：`ui-bridge.ts:241-247`→`:1429-1436`、`advance_phase.py:345-351`→`:538-557`、`launcher.py:593`→`:976`） | 写"函数名 + 行号"，实现前复核 |
| Windows FAT mtime 2s 粒度 | `os.utime(ns=)` 制造同秒改动测试 |
## 8. 增补设计（2026-10-21 第二轮：A + 上下文 + 决策本）

| ID | 决策 | 理由 / 取舍 |
| --- | --- | --- |
| **D-048** | per-dp 策略旋钮只放 `min_confidence`/`max_questions`/`timeout_s`，写进 `.mw/decide-points.json` 行；内置常量降级为"最后一层缺省" | TS 已经解析这个文件（`enabled`/`mode`），加键不改文件格式；常量继续存在保证无配置文件也能跑，且旧代码路径不失效 |
| **D-049** | 生效值解析放在两侧各自的薄函数里（TS `resolvePolicy(pointId)`、Python `resolve_policy(dp_id)`），用同一份 fixture 做 parity 测试 | 跨语言同读一份配置必须有锁，否则 TS 与 Python 对"缺省是多少"会悄悄分叉 |
| **D-050** | 阈值消费点保持现状（`worker-mode.ts:4434/4440/4444`、`pm-orchestrator.ts` dp2 门），只是把常量换成 resolve 结果；不改判定结构 | 改判定结构会把 FIX-J/FIX-M 的已验证行为推倒重来，收益不等于风险 |
| **D-051** | 档案 `decide` 行新增 `policy` 回显（三个生效值） | 事后复盘"0.7 是哪来的、这次是不是被 per-dp 调到 0.5 了"必须能从档案读出来，不靠翻配置历史 |
| **D-052** | `context` 挂在 `state.context` 内，不新增请求字段 | 端点是固定三键契约（FIX-L/N），加字段等于重开传输面；`state` 内嵌天然进 `state_digest` |
| **D-053** | 上下文槽位由**生产者代码**填（TS 从工程现场取），不由 LLM 生成；每槽带 `source` | 上下文是证据的一部分，与 AC-018 "禁止编造"同源；模型只消费 |
| **D-054** | 截断 = 头 60% + 尾 40% + 显式 `…truncated N chars…` 标记，总长按槽位优先级砍 | 报错类信息（栈尾/断言）在尾部，纯头部截断会丢关键行；显式标记防"以为看全了" |
| **D-055** | 决策本 = `{schema_version, decision_point, state, context?, notes}` 单文件；`mw decide ask/run --book` 先验后发 | 与"预期答案不落盘"的 AC-018 一致；`--book` 让"人手写 state"从随口一说变成可审计工件 |
| **D-056** | `book check` 复用 `_estimate_tokens`、`_redact` 检测面、`REQUIRED_STATE_FIELDS` + 类型表，不引入新判定器 | 同一套规则只有一处实现，避免"book 过了但 decide 拒了"的双标 |
| **D-057** | `book check` 只报告不修，`--json` 供 CI/PM 用；`--book` 失败即零 HTTP | 自动补字段会让"编造"合法化；拒绝发送保证不会用错输入烧一次真调用 |
| **D-058** | 证据引用校验"path 存在 + line ≤ 行数 + 文件在仓库内"，不做内容相似度匹配 | 内容匹配会被格式化/换行打破（历史上 content_match 已踩过），存在性校验已足以挡住编造 |
| **D-059** | 决策本的键集合 = 注册表 `required_state_fields` + 允许的 `context` 槽位，**封闭集合**（缺与多都失败） | 只有封闭集合才能让"配置即契约"成立；开放集合等于让人自由发挥，验收器立刻退化成摆设 |
| **D-060** | 骨架由 `book new` 生成，值为类型占位符 + `notes.evidence` 同名待填项；占位符未替换即 `book-placeholder` | 生成器把"要填 13 个字段"变成填空，验收器再挡住"填了占位符就发" |
| **D-061** | TS 字段清单走生成物 `shared/decide-registry.generated.ts`（Python 脚本产出 + 逐字节漂移锁），不在 TS 里手写第二份 | 与 `models.generated.ts` 同构；手写两份必然漂移，而漂移的后果是"配置要求 A、代码发 B"却无人发现 |
| **D-062** | 生成物只含**契约**（字段名/类型/版本/槽位白名单），不含 `description` 文本以外的任何逻辑；校验仍在各自语言内实现 | 生成物是数据不是代码，避免两套校验逻辑 |
| **D-063** | `book new` 不联网、不读工程现场，只读注册表；真实值由 PM/worker 从证据里填 | 生成器一旦"猜值"，编造就被合法化 |

---

## 9. 修订 2 设计（D-064..D-073）：模型签收 + decide_prepare

| 编号 | 决策 | 理由 / 取舍 |
| --- | --- | --- |
| D-064 | 签收模式落在 `.mw/decide.json` 的 `signoff`，**不进** `.mw/decide-points.json` | 后者是逐 dp 授权表（唯配置论）；签收是流程模式，属于客户端配置层 |
| D-065 | `signoff` 解析 fail-soft：非法值保留 `auto` 并记 `signoff_error`，决策主链路不受影响；`mw decide sign` 读到时 exit 2 | 一个拼写错误不该让 24 个 dp 全掉线（与 D-007 的 fail-soft 读取一致） |
| D-066 | `auto` 的判定顺序固定：`disable` → 退出；decide 可用且 `dp25` enabled → jev；否则 LLM 推断（需 `--conclusion`）；都不成立 → 只打印预览 + 指引，exit 0，不写文件 | 保证"不卡流程"：任何情况下 agent 都能靠 `--conclusion` 收尾，且不产生空签收 |
| D-067 | `dp25` 的 state 只由 `decide_signoff.collect()` 的事实组装：`key` / `rows_total` / `rows_available` / `rows_escalated` / `escalated_reasons` / `chain_ok` / `p0_open` / `engine_violations` | 签收问题不需要读 diff 或代码；事实必须与门禁重算同源，否则模型与门禁会打架 |
| D-068 | `dp25` 的判据写进 `instructions`：`continue` 需 N≥1 available + 链闭合 + 每行真 jev engine；`narrow` 用于能力降级；`revoke` 用于链断/engine 不符 | 模型看到的是判据而不是沉默的阈值，减少"猜" |
| D-069 | 置信低于该 dp 生效 `min_confidence`、或 `available=false` → 回落 LLM 路径，并在 `sign-final.md` 记 `decide_fallback: <reason>` | 与 dp1/2/3 的 escalate 语义一致；签收不因模型抖动失败 |
| D-070 | 自动签收允许 agent 会话写文件（`signed_via=auto-decide|auto-llm`）；人签（`cli`/`tui`）保持"agent 会话拒绝" | 用户裁定 D 的直接后果；风险已显式接受，靠档案行 + sha 事后可审 |
| D-071 | `done` 门禁：`signoff=disable` → 通过并输出 note；`auto` → 仍校验文件存在 + `counted_rows`/`rows_sha256` + `continue` 的 verdict | disable 是"永不签收"的显式声明，门禁必须认这条声明 |
| D-072 | 类型改名一次到位 `decision` → `decide_prepare`，不留别名 | 项目规则"不做向后兼容"；旧名只存在于历史档案 |
| D-073 | `decide_prepare` 的模型走既有 role→model 机制：`DISPATCH_ROLES` 增项即可，`.mw/dispatch.yml` 的 `models.decide_prepare` 提供默认值；解析顺序 task override > role > fallback chain 不变 | 无新增代码路径；per-role 模型本来就是这个框架的能力 |

| D-070a | `authority-change` 行的 `by` 仍用冻结词表 `signoff:<conclusion>`；`signed_via` 与 `decide_fallback` 落 `sign-final.md` 机器行与行 `note`，**不**扩 `_CHANGE_BY` | W9 实测：`decide_archive._CHANGE_BY` 是冻结词表，扩词表会让 4 类行契约与历史档案对不上；把 `signed_via` 留在文件里同样可审计，且门禁已经校验 sha |
| D-071a | `dp25-signoff-conclusion` 登记为 **P2**（默认开、默认 auto），executor 只回显 `signoff:<conclusion>`（不写文件、不联网） | W9 实测默认路径落到 `auto-llm`：`decision_points.py` 铁律"只有 P2 默认开"。要让"默认 auto 就走 jev"成立，dp25 必须是 P2；写文件仍由 `mw decide sign` 做，executor 不获得写权限 |
