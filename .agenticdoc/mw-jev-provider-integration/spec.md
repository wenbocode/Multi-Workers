# Spec: mw-jev-provider-integration

## §0 Goal Alignment

**对齐**：goal.md 第 2 条"做成接口友好，框架需要决策的时候能正确调用并有效反馈"是本 key 的直接落点；第 1 条"jev 跑通能用起来"按用户裁定收敛为"决策调用链路可用"，不做聊天模型接入。

**GC 继承（goal.md Key Constraints）**：

- **不引入中心化调度器 / 协调经由文件系统**：决策服务是旁路调用，不承担调度裁决；决策不可用时编排仍按既有文件驱动逻辑推进（AC-002/AC-007）。
- **不修改 pi 核心**：实现落在 mw 侧（`packages/multi-workers/*`）与既有配置/证据读取面；不新增或修改 pi 的 provider 与模型目录。
- **Worker 进程级隔离**：决策调用由编排侧（PM 窗口 / launcher / mw）发起，不改变 worker 进程边界与生命周期。
- **凭据隔离**：复用既有剥离/回注机制，决策链路只依赖 `TIMI_API_KEY`（AC-005）。
- **文件锁与原子写**：决策证据/缓存落盘遵循既有 O_CREAT|O_EXCL 锁与 P-003 原子写约定。
- **goal.md 作为锚点**：证据行与文档引用 goal.md 第 2 条；相位收尾记录 goal mtime。

**冲突**：

- 与 `mw-model-fallback-cli`（active）：它持有 `mw.py` 的 `cmd_model`/`_model_write` 与 `ui-bridge.ts` 的 `/mw model` 转发段。本 key 新增 CLI 子命令独立成函数、不进入该段；不改模型前缀/路由/凭据值域。
- 与"把 jev 当聊天模型"的既有目录条目（`timi.json` jev-latest 的 `anthropic-messages`/`reasoning=true`/200K）：**不改**，仅作为遗留不一致记录在证据与 spec。
- 与 D-1（上游决策入口未暴露）：D-1 未决时交付物仍可按 AC-001..011 验收（过渡后端 + fake transport），但绝不允许把"未启用/不可用"呈现为"决策已生效"。

**预期收益（及判定方式）**：

- **决策调用接口统一**：一次调用拿到类型化结论 + 置信度 + 置信度来源 → AC-001（CLI 与 API 契约一致测试）。
- **编排在决策时刻可调用且不冒险**：不可用/超时/上游错误一律 fail-soft，默认零行为变化 → AC-002/AC-006/AC-007/AC-009（测试 + 关闭态逐分支等价）。
- **反馈在既有通道可见**：PM 在平日查看面（readback/ledger/doctor）看到分诊建议与置信度来源 → AC-008/AC-010。
- **上游可复验**：决策入口一旦开通，一条命令复跑即可切换启用 → AC-004 probe（含 429 / unmapped 锚点复现）。
- **诚实性**：过渡后端自报置信度与 typesafe 直出置信度在数据字段与呈现文案上均可区分 → AC-001 `confidence_source` + AC-008 文案带来源。

## §1 功能概述

### 1.1 目标

1. 交付一个决策客户端与统一入口：输入 `state` + 类型化 `questions`，输出类型化 `answers` + `confidence`；CLI（JSON 进 JSON 出）与 Python API 同一实现，PM 窗口（TS）与 Python 编排（conductor/launcher/mw）都可调用。
2. 交付传输抽象与诊断探针：传输后端可切换（llmproxy 统一鉴权为主），并提供一条命令当场产出"哪个端点/形状能通"的矩阵证据。
3. 接入首个框架决策点 **DP-1 派发前分诊**（判定任务类型与风险等级）：默认关闭；开启后以**旁路建议**形式产出（类型 + 风险等级 + 逐项置信度），写机器可读证据行并随既有 readback 通道呈现 PM；决策不可用时行为与未开启逐分支等价。

### 1.2 需求链 / 来源

- 用户裁定（2026-10-16）：**路线 B —— 只跑决策，不当聊天模型；不需 typesafe.ai 自备账号，走 timiai 统一鉴权（TIMI_API_KEY → llmproxy）**。
- 用户裁定（2026-10-16，三次）：传输层取 **(ii)** —— **过渡后端**（现有 LLM 结构化输出，走同一 `TIMI_API_KEY`）与 **jev 后端**并存；jev 是决策服务的正式后端，过渡后端保证 DP-1 当下即可真实可用。
- 用户裁定（2026-10-16，二次）：首个决策点取 **DP-1 派发前分诊**；本波为旁路建议，不据此改写派发策略。
- 官方契约（RQ-1）：Jev = "System One" 结构化决策 API，唯一端点 `POST /v1/systemone`（`state` + `questions` → `answers`），Bearer 鉴权；问题类型 `choice / score / noul / box`；响应只读 `confidence`（0–1，由 probabilities 派生）；无流式、无 reasoning 参数；官方明示 Jev 不是 coding-agent 的后端模型。
- 仓内接线（RQ-2）：目录/生成/路由/凭据层**均已就绪、无断点**；唯一断点在调用层（上游 llmproxy）。
- 决策面盘点（RQ-3）：选型/回退/反馈三条链的接入点、配置键与冲突边界。
- PM 直执线上探针（evidence/research/spec-jev-live-probe-20261016.md）：llmproxy 是 litellm，`jev-latest` 已注册（`owned_by=typesafe`），但 `/v1/messages` 持续 429（≥90s 复测仍 429）、`/responses` 报 `Unmapped LLM provider for this endpoint`、自定义决策路径全 404、anthropic schema 严格拒绝 `state/questions` 字段。

### 1.3 面向用户故事

- 作为 PM，我希望在 worker 终态/产物判定这类"需要判断"的时刻，能拿到一个独立、类型化、带置信度的第二意见，并在我能看到的地方（readback/ledger）看到它，而不是只能靠 LLM 自查。
- 作为编排层（conductor/launcher），我希望调用决策服务是**纯旁路**：不可用、超时、被限流时一律当作"没有这个意见"，绝不改变派发/执行/收尾的既有行为。
- 作为运维/未来接手的窗口，我希望一条命令就能知道"决策链路现在通不通、堵在哪一层"，而不是重新做一轮调研。

### 1.4 范围说明（不做什么）

- **不做**：把 jev 接成 packages/ai 的聊天模型（不新增 api 类型、不新增 provider 工厂、不改模型目录语义）。
- **不做**：新增 provider 前缀 / 路由 / 凭据条目（`mw_common.py` 前缀表、`dispatch-models.ts` 镜像、`providers.json` 均不动）。
- **不做**：typesafe.ai 自备账号直连（网络可达但需凭据，用户已排除）；传输层保留该后端作为可切换项，但**不交付其凭据配置**。
- **不做**：改动 `.mw/dispatch.yml` 的 `models` / `fallback_models` 语义（决策服务是旁路，不承担模型路由决策的落地）。
- **不做**（本波）：依据决策结果改变派发策略（类型改写 / 风险升级 / 模型切换）。DP-1 本波为旁路建议，行为落地留待后续波次且需显式配置开启。
- **不做**：修改 `timi.json` 中 jev-latest 的标注（`reasoning=true` / 200K ctx 与官方契约不符一事记为遗留，另案处理）。
- **不做**：引入中心化调度；不新增跨 key 写入。

## §2 业务约束

### 2.1 平台 / 环境

- Windows 主开发环境；Python 3.x（mw 现有运行时）；shell 为 PowerShell（多行脚本一律落盘执行）。
- llmproxy 内网可达（`api.timiai.woa.com`），凭据链路沿用 `TIMI_API_KEY` →`~/.pi/agent/auth.json` 的 `timi.key`。
- llmproxy 只接受**裸模型 id**（provider 前缀写法被 403 拒）；真实 openai-responses 路径是 `/responses`（**无** `/v1` 前缀）。

### 2.2 质量指标

- 决策调用不得给主流程增加不可控延迟：单次调用超时可配、默认 ≤30s，超时即失败退出（fail-soft）。
- 调用预算有界：单次决策问题数上限、`state` 字节上限、重试次数上限、退避上限。
- 默认零行为变化：未启用配置时，框架行为与现状逐字一致（无新 spawn、无新网络调用）。

### 2.3 安全约束

- 只使用既有 `TIMI_API_KEY`（llmproxy 统一鉴权），**不新增任何凭据文件或字段**；复用既有 per-task 凭据剥离/回注机制。
- 任何日志/证据/trace 不得落明文 key；错误文本按既有截断规范收敛。
- fail-soft 铁律：决策服务不可用绝不阻断派发、执行、收尾；不得因决策失败产生新的终态语义。

### 2.4 兼容约束

- 不改动既有输出契约（output.md 段落、trace 机器行格式、exit 码语义）；新增证据行为**新增前缀**，不复用既有前缀。
- 不触碰并行 key 的写入面：`mw-model-fallback-cli`（active）持有 `mw.py` 的 `cmd_model/_model_write` 与 `ui-bridge.ts` 的 `/mw model` 转发段；本 key 的 CLI 子命令须独立成函数，避让该段；冲突时等其 settle。

## §3 验收标准（AC）

| AC 编号 | 判据 |
| AC-001 | 决策入口契约：`mw decide` 接受 JSON 请求（`state` + `questions`，问题类型覆盖 `choice/score/noul/box`），输出 JSON 响应（`answers` 各项含取值与 `confidence`，附 `available/transport/model/attempts/latency_ms/reason/**confidence_source**` 元数据）；同一实现同时暴露 Python API（可 import 调用），CLI 与 API 共用同一参数校验与响应构造代码路径。**`confidence_source` 必须区分 `api`（上游直出，如 typesafe）与 `model-self-report`（过渡后端由模型自报，未经校准）**，不得把两者混同呈现 |
| AC-002 | fail-soft：传输层任何失败形态（连接不可达 / 超时 / 429 / 529 / 5xx / 响应不可解析 / 上游显式错误体）一律返回 `available=false` + 机器可读 `reason`，**退出码 0**，调用方主流程行为不变；仅参数非法（缺字段、未知问题类型、超上限）退出码 2；任何情况下不向编排主流程抛未捕获异常 |
| AC-003 | 传输抽象（≥3 后端可切换，调用方接口不感知后端差异）：**(B1) `llmproxy-anthropic`** —— jev 决策的正式目标后端，当前受 D-1（决策入口未暴露）阻塞，实现到位但默认不可用并显式报 `reason=entry-unavailable`；**(B2) `llm-transitional`** —— 以 timiai 可用模型（默认 `glm-5.3-flashx`）承载**同一 `state/questions` 契约**，强制结构化 JSON 输出（含逐项置信度且标 `confidence_source=model-self-report`），**本波默认后端**；**(B3) `direct-systemone`** —— typesafe 直连，保留实现位、不交付凭据配置。后端由配置选择，未配置走默认 |
| AC-004 | 诊断探针：`mw decide --probe` 输出矩阵（各后端 × 候选端点/请求形状的 HTTP 状态 + 结论），并把结果落成证据文件；当下 429（`/v1/messages`）与 `Unmapped LLM provider`（`/responses`）必须能被复现为锚点 |
| AC-005 | 凭据最小面：在仅存在 `TIMI_API_KEY`（或配置指定的同一凭据源）而其它 provider 凭据被剥离的环境下，决策调用链路仍可用；证据与日志中无 key 明文 |
| AC-006 | 预算与退避：超时、重试次数、退避、问题数、`state` 字节数均可配且有默认值；超预算立即 fail-soft 返回，不重试到最后一条预算线下仍阻塞 |
| AC-007 | 首个决策点 DP-1（派发前分诊）：默认关闭；开启后每次派发前产出一条分诊建议（任务类型 + 风险等级 + 逐项置信度），写入证据行并随既有 readback 呈现 PM；**不改写派发的类型/角色/模型，不改变 watchdog/checkpoint 策略**；决策不可用（未配置 / 超时 / 上游错误 / 响应不可解析）时该路径行为与未开启逐分支等价（有测试证明） |
| AC-008 | 有效反馈：每次决策调用写一条机器可读证据行（含决策点 id、传输后端、模型、尝试次数、延迟、可用性、原因、结论值、置信度）；被接入的决策点把结论经**既有** readback/ledger 通道呈现给 PM（不新造通道） |
| AC-009 | 默认零行为变化：仓库未创建/未启用决策配置时，`mw doctor`、派发、执行、收尾行为与现状一致；无新增子进程、无新增网络调用 |
| AC-010 | 可运维性：`mw doctor` 增加决策服务行（启用状态 / 传输后端 / 上次探测结果）；`packages/multi-workers/README.md` 与 `packages/multi-workers/CHANGELOG.md` 落地对应说明与条目 |
| AC-011 | 测试：以 fake transport 覆盖 AC-001/002/003/006/007/008；真实链路因上游阻断以 probe 证据（AC-004）呈现而非测试断言；相关测试套件全绿，既有环境红列零新增 |
| AC-012 | 上游依赖显性化：spec/design 记录 D-1（llmproxy typesafe 契约未知）与给 llmproxy 维护方的问题单文本；D-1 未决时交付物仍可按 AC-001..011 完整验收（以 fake transport） |

## §4 依赖与未决项

**D-1（阻塞上游，非本仓可修）timiai/llmproxy 未对外暴露承载决策语义的入口。** 本 key 只做决策调用（不当聊天模型用），而官方决策 API 是 `POST https://api.typesafe.ai/v1/systemone`（`state` + `questions` → `answers`，Bearer 鉴权）；llmproxy 上**不存在等价入口**。探针事实（均可复现）：决策形状路径穷举 20+（`/v1/systemone`、`/systemone`、`/v1/decide`、`/v1/classify`、`/v1/query`、`/v1/ask`、`/v1/jev`、`/typesafe/v1/messages` …）**全部 404**；`/v1/messages` 的 schema 校验显式拒收 `state`/`questions`（400 `unknown_fields`）；`/responses` 报 `Unmapped LLM provider for this endpoint ... custom_llm_provider=typesafe`；旁证：`/v1/messages` + `jev-latest` 聊天形状持续 429（≥90s 复测仍 429，同秒对照模型 200）；`GET /v1/models/jev-latest` 显示 `owned_by=typesafe`、`created_at=2026-10-14`。

拟提交给 llmproxy 维护方的问题单：

1. timiai 是否提供（或可开通）承载 typesafe 决策调用的入口？端点与请求形状是什么——直接接受 `state` + `questions`，还是必须借某一标准端点承载？
2. 若只能借标准端点：决策语义如何编码（模型 id 约定 / 消息内容约定 / 专用字段 / header 开关）？
3. `/responses` 报 typesafe `Unmapped LLM provider for this endpoint` 是否为预期？
4. 聊天形状下 `/v1/messages` 对 `jev-latest` 持续 429 的原因（配额 / 白名单 / 上游限流），解除条件是什么（旁证，非本 key 主路径）。
5. 是否可开放版本化 id（`jev-1.13.0` / `jev-1.14.0`）与长上下文开关（262k）。

**D-2** 上游给出入口后复验：`mw decide --probe` 单命令复跑，结果补为证据（不需改代码）。

**D-3（已定档）** 首个决策点 = **DP-1 派发前分诊**（用户裁定 2026-10-16；候选"产物与终态第二意见 / 模型路由判据 / review 分级复核"留待后续波次）。设计相位需给出接入锚点，并做文件新鲜度与并行冲突检查（`mw.py` 的 `cmd_model` 段、`ui-bridge.ts` 的 `/mw model` 段归 `mw-model-fallback-cli`，须避让）。

**D-4** 上游若长期不修：交付物仍具备价值（接口、传输抽象、探针、测试、配置面就绪），但"生产启用"需 D-1 解除；此情形下的启用状态必须显式记录为不可用，不允许静默降级成"决策总是 no-op 却看似生效"。

## §5 开工前必须掌握的知识与已知坑

### 可复用资产

- 调研证据四份（`.agenticdoc/mw-jev-provider-integration/evidence/research/`）：typesafe 官方契约、仓内接线与断点清单（含生成链 `generate-models.ts:724-736`）、决策面锚点表、PM 线上探针矩阵。
- 配置读取：`mw_common.py:217-261`（`dispatch_config_path`/`load_dispatch_config`，fail-soft 语义）。
- doctor 行渲染：`mw_common.py:4460-4496`。
- 原子写与读改写模式：`mw.py:3464-3492`（只借模式，不占该代码位置）。
- 重试/退避参考：`packages/ai/src/utils/retry.ts`、`provider-retry.ts`。
- 决策时刻锚点表：RQ-3 Q5（`dispatch.py`/`conductor.py`/`launcher.py`/`ui-bridge.ts`/`dispatch-models.ts` 的 path:line）。
- Python 测试骨架：`packages/multi-workers/test_*.py`；探针蓝本：本次 PM 探针脚本。

### 需规避坑点

1. **host 写法**：仓内真值是 `api.timiai.woa.com`（RQ-2 正文写作 `api.timia.woa.com`，该名不解析）。
2. **路径陷阱**：openai-responses 的真实路径是 `/responses`（无 `/v1`）；`/v1/chat/completions` 与 `/v1/responses` 一律 404（与模型无关）。
3. **只认裸 id**：`typesafe/jev-latest` 这类前缀写法被 403 拒；别名外的版本化 id 亦被拒。
4. **429 无 retry-after**：退避只能指数估计（RQ-2 Q4 的既有处置仍适用；anthropic-messages 路径 HTTP 层默认零重试）。
5. **`models.generated.ts` 是聚合 hub**：该文件 grep 不到具体模型不等于模型不可见，不要据此下"需修生成链"的结论（RQ-3 曾据此误判）。
6. **中文/编码**：PowerShell 管线会改写 UTF-8（P-001）；探针与 CLI 的输入输出一律走 Python 落盘/管道，不用 PS 重定向处理中文载荷。
7. **并行写面**：`mw.py` 的 `cmd_model` 段与 `ui-bridge.ts` 的 `/mw model` 段属 `mw-model-fallback-cli`（active）；新增 CLI 子命令须独立函数、避让该段。
8. **决策入口未暴露**：llmproxy 上决策形状路径已穷举 20+ 且全 404；不要把 `/v1/messages` 当作决策载体——其 schema 校验明确拒收 `state`/`questions`。传输层的入口形状在 D-1 解除前属未知，实现必须允许后端整体替换（含请求编码方式）。
9. **置信度语义**：过渡后端（B2）的 `confidence` 是模型自报值，**未经校准**，不得与 typesafe 直出置信度同等对待（AC-001 的 `confidence_source` 即为此设）；DP-1 建议的呈现文案必须带来源标识。
