# Research: 自动 gate 决策的副作用护栏（RQ-11 / key `mw-autopilot-slot-capacity`）

> 角色：spec 期调研（**只读**）。本文件是本次调研唯一写入的仓库文件（临时复算脚本写在 OS `%TEMP%` 并在用后删除；未改 FM/E2 任何文件、未答任何 gate、未改代码/config、未 commit）。
> 代码基线：`H:/git/Multi-Workers` HEAD `4ef71e053`。
> 数据基线：FM=`E:/CLI_workspace/FeatureMigrator`（timeline 70.6h 窗口，快照 2026-09-26T07:40Z）、E2=`H:/git/E2Feature`（timeline 100.1h 窗口，同快照）。
> 前置笔记（不重复其内容）：`spec-stalled-slot-release-20260926.md`（RQ-6：反作用清单 a–d）、`spec-unattended-stage-closure-20260926.md`（RQ-8：门清单/阻塞面/等待时长）。RQ-10（"哪些 gate 可自动"）截至本卡写入时**尚无 output/证据笔记**（`workers/msc-rq10-auto-gate-boundary/` 无 output.md）⇒ 本卡只做护栏，不做边界判定。

## TL;DR

1. **既有原语够用，不要自造状态机**：9 类可复用原语（F1 的 P1–P9），其中 4 类自带上界/去重——`round_budget`（轮预算，config）、`advance_stall_ticks`（1..50 连续失败阈值）、`_XKEY_PROPOSAL_MAX_ATTEMPTS=2` + `proposal_exhausted_at`（"尝试次数上限 + 持久 exhausted 标记"范式，`conductor.py:2872/2959/3021`）、`_consumed_gate_ids` + `_gate_open`（持久消费去重）；3 类**无上界**——`_resume_credits`（每次人工 approve +1，无 cap、无夜窗）、timeline 事件量、gate 文件数。另有 `gate.created_at`（天然的宽限/冷却时钟）与 `paused`（现成的"停动作不停进程"）。
2. **最关键的新缺陷（护栏硬前置）**：`_consumed_gate_ids` 用 `re.match(r"(gate-\d{4})\b", ...)` 只认 **4 位** gate id（`conductor.py:310-312`）。`gate-10000` 起持久消费护栏**静默失效**；FM 洪泛已到 `gate-6687`（11.41h 内 6684 个文件，585.8 个/h）。**任何"自动过大量 gate"的方案首先会撞这条**（详见 F6-D1）。
3. **现状：零自动决策、零 TTL、零自动决策痕迹**。全仓无 auto-answer/unattended/cooldown/quota 代码（grep 零命中）；`answered_by` 是自由文本无枚举；`gate-answered` 事件 detail 不含 `answered_by`；面板只渲染 pending gate；`mw doctor` 的 autopilot 段只报 xkey，**零 gate/stall/slot 内容**（`mw_common.py:2022-2065`）。
4. **回放估算**：按"对历史答案 100% 一致的 gate 自动过"——FM+E2 三个有实例的 kind 全为 100% approve，共 **28 个 gate** 会被自动过；**最大单夜 3 个**（UTC+8 22:00–08:00）。但同期洪泛窗口有 **6684 个 pending stalled gate、单夜 5364 个、峰值 17 个/分钟**：自动批准一旦叠加"无去重/无配额"，单夜数量级是**数千**，`_resume_credits` 也会是数千（实测洪泛时该值恒为 1，因为门全是 pending）。
5. **kill switch**：`paused` 可"只停调度不停 conductor"，`enabled=false` 直接由 serve 终止 conductor（`mw.py:140-196`）。但**没有"只停自动决策"的粒度**；批量回看/撤销**没有**：`_consumed_gate_ids` 由 append-only timeline 推导，不可逆；gate 手改回 pending 也不会重新生效（同一个 id 已在 consumed 集合里）。

## 决策问题

本卡只回答"护栏"（RQ-11），边界如下（**不**回答"哪些 gate 可自动"——那属 RQ-10）：

1. **可复用的既有原语清单**：`_resume_credits` / `round_budget` / `advance_stall_ticks` / `_XKEY_PROPOSAL_MAX_ATTEMPTS` / `_consumed_gate_ids` / `goal-halt`+`goal-snapshot` / 既有预算 env 与 `config.json` 键——每项给 `file:line`、语义、**是否有上界**，结论落在"护栏应复用哪些原语"。
2. **逐条副作用的机制候选 + 可检测信号**：对 RQ-6 的 (a)~(d) 每条给机制候选、代价、**它发生时在 timeline/文件/面板上留什么痕（具体到事件名/字段/计数）**、当前有没有这个信号、缺位时首个失败模式（带判据）。
3. **配额阈值的数据依据**：用 FM/E2 历史做**回放估算**（100% 一致规则下会被自动过的条数、最大单夜条数、`_resume_credits` 消费量），给算法与复算方式、样本量、不确定性——直接支撑 U-8"由数据定"是否可行。
4. **kill switch 与审计现状**：`enabled`/`paused` 语义与生效路径；能否"只停自动决策不影响 autopilot"（是否需新键）；批量回看/撤销已自动过 gate 的现有能力（`_consumed_gate_ids` 是否可逆）。
5. **GC 校验**：每条候选是否满足 GC-1（不得引入内存控制器，必须每 tick 由文件重推）与 GC-3（新增落盘状态的锁面）；违反者明说。

**硬要求遵守**：只列"候选 + 代价 + 判据"，**不下最终决策**；不编造阈值；无法估算处写"无法估算 + 需要什么数据"；新机制必须能留痕。

## 调研方法与出处

### 代码（只读通读 + 定点复核）

- `packages/multi-workers/autopilot/conductor.py`：`orchestrate:183`、`_consumed_gate_ids:297`、`_consume_answered_gates:316`、`_stage_closure:616`、`_advance_stall_ticks:794`、`_advance_failure_streak:803`、`_record_advance_result:868`、`_advance_key:907`、`execute_loop:1062`、`_verify_loop:1573`、`tick:2050`（`enabled/paused` 门 `:2060`，goal 分支 `:2064-2113`）、`_deps_satisfied:2153`、`_create_gate:2159`、`_gate_open:2188`、`_budget_bonus:2216`、`_budget_gate_rejected:2228`、`_resume_credits:2273`、`_apply_stalled_approvals:2295`（消费守卫 `:2315-2319`，resume 事件 `:2349`）、`_apply_stalled_rejections:2363`（reject 事件 `:2388`）、xkey 段 `:2860-3070`、`mark_stalled:3944`、启动 goal baseline `:4139`。
- `autopilot/config.py`（13 键 `:48-61`、范围 `_INT_RANGES:68-76`、fail-closed `validate_config:89`、`save_config:150`）。
- `autopilot/gates.py`（`GATE_KINDS:54`、`FRONTMATTER_FIELDS:68-80`、schema 校验 `_to_gate`）。
- `autopilot/effective_config.py`（`EFFECTIVE_KEYS:66-70` = 仅 2 个 xkey 键可机器层覆盖）。
- `autopilot/timeline.py`（`EVENT_TYPES:67-84` 17 类、append-only、rotation）。
- `autopilot/xkey.py`（`LOCK_NAME:102`、`ledger_append:544`、`ticket_write:790`、`tickets_iter:824`）。
- `mw_common.py`（`acquire_lock:1482`、`_TERMINAL_STATUSES:158`、`_doctor_queue:1954`、`_doctor_autopilot:2022`、`_doctor_issues:2067`、`PI_WORKER_ORPHAN_DEAD_MIN:1860/1917`）。
- `mw.py`（serve↔conductor 生命周期 `_conductor_decision:140`、spawn/terminate `:173-196`、`mw autopilot` CLI `:3514`）。
- TS：`agent-team-loop/autopilot/status-model.ts`（`DEFAULT_CONFIG:102`、`INT_RANGES:134`、`saveConfig:289`、`GATE_KINDS:561`、`EVENT_TYPES:779`）、`monitor.ts`（`deriveAutopilotPanel:463`、`renderMonitorLines:557`、slots 行 `:596`、attention `:603-627`、gates 行 `:644-655`）、`console.ts`（`cmdGates:182`、`cmdGate:204`、`saveConfigLocked:293`、`cmdSetEnabled:319`、`cmdSetPaused:371`）、`shared/xkey-gate-guard.ts`（工具层封 gate 目录写）、`worker/worker-mode.ts:154/162/742/894-895`（PI_WORKER_TIMEOUT_MS / PI_WORKER_IDLE_MS）、`rag/budget.ts:39`。
- grep：`auto.?answer|auto_gate|autonomous|unattended|auto_decision|kill.?switch|cooldown|quota` 在 `autopilot/*.py` **零命中**（除 `conductor.py:1` docstring 的 "autonomous"）；gate TTL `expires/ttl` 对 gate 零命中（RQ-6/RQ-8 已固化）。

### 数据复算

- gate 文件：FM `gates/*.md`（10 个）+ `_gates-flood-20260924/*.md`（6684 个）；E2 `gates/*.md`（18 个）。逐文件解析 frontmatter（`kind/stage/key/created_at/status/answered_at/answered_by`），统计答案分布与等待时长。
- timeline：合并 generation（`timeline.jsonl.1` older → `.jsonl` newer），统计事件词表计数。
- "单夜"判定：`created_at/answered_at` 转 UTC+8，`22:00–08:00` 归到"22:00 那天"的夜；**推断**（输入本身是带时区 ISO8601，时区换算是我方约定）。
- 复算脚本（最小版，`python -` 或临时文件运行；本卡实际用 OS `%TEMP%` 脚本并已删除）：

```python
import re, glob, os, datetime, collections
TZ = datetime.timezone(datetime.timedelta(hours=8))
def parse_gate(p):
    t = open(p, encoding="utf-8", errors="replace").read()
    e = t.find("\n---", 3); b = t[:e] if e > 0 else t
    d = {}
    for line in b.splitlines():
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
        if m: d[m.group(1)] = m.group(2).strip() or None
    return d
def iso(s):
    if not s: return None
    s = s[:-1]+"+00:00" if s.endswith("Z") else s
    return datetime.datetime.fromisoformat(s)
def night(ts):
    if ts is None: return None
    loc = ts.astimezone(TZ)
    return loc.date().isoformat() if loc.hour >= 22 else ((loc.date()-datetime.timedelta(days=1)).isoformat() if loc.hour < 8 else None)
# 对每个 gates 目录: Counter((kind,status)), waits, Counter(night(answered_at))
```

- 直接可复现的实测计数（本次）：FM timeline `beat=53882`、`gate-created=6696`、`gate-answered=6694`、`stalled=6691`、`resume=6691`；E2 `gate-created=18`、`gate-answered=18`、`stalled=13`、`resume=13`、`beat=83717`。FM 洪泛目录 6684 文件（`gate-0004..gate-6687`，全部 `pending`、无 `answered_at`），`created_at` 窗口 `2026-09-23T15:37:12Z..2026-09-24T03:01:32Z`（11.41h），峰值 17 个/分钟（`2026-09-23T15:45..15:50Z`），按 key = `gui-contract-surface` 5587 / `gui-shell-spike` 1097。
## 发现

### 【事实】F1 — 可复用的既有原语清单

| # | 原语 | 锚点（file:line） | 语义 | 有上界？ |
|---|---|---|---|---|
| P1 | `_resume_credits(project_root, key)` | `conductor.py:2273-2293`；消费点 `:966`（L2 `limit=budget+credits`）、`:1088`（EXECUTE）、`:1594`（L3）、`:1735`（repair） | `count(gate.kind=="stalled" and gate.status=="approved" and gate.key==key)`，每次调用从 gate 目录重推（零内存态）；每个 credit 在**每个** cap 回路各给一轮 | **无上界**。可被任意多次 approve 单调抬高；无 per-key/每夜 cap；不计"谁批准的"。 |
| P2 | `round_budget` | `config.py:53`（默认 2）、`:71`（`>=1`）；TS `status-model.ts:107`；消费点 `conductor.py:964/1086/1593/1735` | 每个 cap 回路的轮预算基线（L2 / EXEC / L3 / repair 共用一个数） | 有下界无上界（`>=1`，可任意大）。是"每回路配额"的现成承载键。 |
| P3 | `advance_stall_ticks` | `config.py:57`（默认 5）、`:75`（范围 **1..50**）；`_advance_stall_ticks:794-799`；streak 重推 `_advance_failure_streak:803-866`；触发 `_record_advance_result:868-902` | 同一 `(key, edge)` 连续失败 N 次 ⇒ `mark_stalled`（有界失败，避免无限重试） | **有上界（50）**。是唯一"连续尝试计数"旋钮；streak 从 timeline tail 重推，restart-safe。 |
| P4 | `_XKEY_PROPOSAL_MAX_ATTEMPTS = 2` + `proposal_exhausted_at` | 常量 `conductor.py:2872`；判定 `:3021-3027`、`:3051-3057`；`_xkey_proposal_exhaust:2959-2979`（写 ticket frontmatter `proposal_exhausted_at/detail`）；`xkey.ticket_write:790`（锁 `xkey-ledger.lock` `xkey.py:102/165`） | "尝试次数上限 + 持久 exhausted 标记 + 不再 spin"的完整范式：界限、去重、留痕三件齐 | **有上界（常量 2）**。这是"自动决策次数上限"最该照抄的范式。 |
| P5 | `_consumed_gate_ids` + `_gate_open` | `_consumed_gate_ids:297-313`；消费点 `_consume_answered_gates:341-345`、`_apply_stalled_approvals:2315-2319`；去重 `_gate_open:2188-2214` | 从 timeline `gate-answered` 事件反解已消费 gate id 集合（append-only = 持久、restart-safe）；`_gate_open` 保证同 (kind, loop/stage/request_id) 只有一个 pending gate | **去重（无计数上界）**。`4e874f5cc` 用它终结 FM 6684 洪泛。**缺陷见 F6-D1：正则只认 4 位 id。** |
| P6 | `goal-halt` / `goal-snapshot` / `goal-change` gate | 事件 `conductor.py:2093`（halt）、`:2109`（snapshot）、`:4139`（启动 baseline）；`open_goal_change_gate:174-181`；gate kind `gates.py:54-61` | goal.md mtime 变化 ⇒ 挂一个 `goal-change` gate 并 halt（tick 在 orchestrate 前返回 `halted-goal-change`，全停）；答后刷新 baseline + `goal-snapshot` 恢复。halt 状态由"gate 目录里有没有 pending goal-change"重推（create-once） | 单 gate（文件真值去重）；**这是"文件驱动的硬停杆"范式**：不需要改 config，挂一个 pending gate 即停。 |
| P7 | 预算类 env | `PI_WORKER_TIMEOUT_MS` / `PI_WORKER_IDLE_MS`（`worker-mode.ts:154/162/742/894-895`；`budget.ts:39`）；`PI_WORKER_ORPHAN_DEAD_MIN`（`mw_common.py:1860/1917`，默认 90min）；`PI_WORKER_TASK`（`launcher.py:248/266/275/298/326`） | worker 墙钟兜底 / idle 看门狗 / 孤儿行静默窗 / worker 任务书 | 有（各自 env 或默认）；**都在 worker 生命周期，与 gate 决策不同域**——不能拿它们当 gate 配额。 |
| P8 | `config.json` 13 键 | `config.py:48-61`、范围 `:68-76`；TS 镜像 `status-model.ts:102-141`；机器层仅 2 键 `effective_config.py:66-70` | 用户可用的"数量/时间"旋钮只有：`round_budget`（轮）、`advance_stall_ticks`（连续失败）、`poll_interval_sec`（1..5，tick 粒度）、`worker_timeout_min`、`xkey_verify_timeout_s`；停止杆只有 `enabled`/`paused` | **没有任何"配额/冷却/夜窗/最大自动次数"键**。 |
| P9 | `enabled` / `paused` | `config.py:49-50`；语义 `conductor.py:2060`（`enabled && !paused` 才 orchestrate）；serve 生命周期 `mw.py:140-196`；写入 `console.ts:319-385`（`saveConfigLocked:293`）；落盘 `config.save_config:150` | `enabled=false` ⇒ serve **terminate** conductor（全停）；`paused=true` ⇒ conductor 存活、仍写 beat、但不 orchestrate（软停） | 二值、全局粒度。**无"只停自动决策"颗粒度**。 |

**F1 结论（回答"护栏应复用哪些原语"）**：组合 `P5`（同 gate 只消费一次）+ `P4`（尝试上限 + 持久 exhausted 标记）+ `P2/P3`（已有的"轮/连续失败"上界语义）+ `gate.created_at`（天然的宽限/冷却时钟，无需新状态）+ `P6`（文件驱动硬停杆）+ `P9`（kill switch）即可覆盖全部护栏诉求，**不需要新状态机**。只有"每夜/每 key 的自动决策计数"这类需要窗口计数的量，应优先从 **timeline 事件扫描**推导（`gate-answered` 带新 auto 标记），而不是新增内存计数器。

### 【事实】F2 — 逐条副作用：机制候选 / 可检测信号 / 缺位时首个失败模式

> 列的是**候选**（含代价），不是决策。信号一栏明确"当前有没有"；这是"cap 阻塞零痕迹"教训的对齐点。

#### (a) auto-approve × `_resume_credits` 无上界（RQ-6 反作用 2）

| 机制候选 | 代价 | 可检测信号（当前？） | 缺位时首个失败模式（判据） |
|---|---|---|---|
| A1 自动批准**不产生 credit**（credit 只数 `answered_by` 非 auto 的 stalled gate；`_resume_credits:2273` 加过滤） | 需定义"auto 批准"标记（见 d）；与现有人工语义解耦 | 当前**无**：`_resume_credits` 只看 kind/status/key，`answered_by` 不在消费面；但 `stalled` 事件的 detail 文本含 credit 展开后的 `used/{budget+credits}`（`execute_loop:1101`、`_verify_loop:1725/1739`）——**是文本不是字段** | `limit` 单调抬高、同 key 每回合都"还有一轮"；判据 = 窗口内该 key `resume` 事件数上升而 `done`/`stage-close` 不出现。 |
| A2 per-key 每夜自动决策配额（由 timeline `gate-answered`(auto) 在 22:00–08:00 窗内计数，`>=N` 即停 auto 并挂 gate） | 需要 auto 标记 + 窗口扫描（GC-1 友好）；阈值要数据定（见 F3） | 当前**无** auto 标记、无夜窗计数 | 单 key 单夜无限自动过；判据 = 该 key 单夜 auto 批准数 ≥ 配额且 key 未收敛。 |
| A3 全局熔断阈值（窗口内 auto 决策总数 > N ⇒ 停 auto + 挂 `goal-change` 式 gate） | 需要一个"停 auto"的全局开关（见 F4）；阈值数据不足（见 F3 数据缺口） | 当前**无**任何 auto 计数/开关 | 全项目夜间一起烧；判据 = 全项目 auto 批准数跨过阈值、`dispatch` 数同比例上升。 |
| A4 同 gate 最大自动次数（复用 P5 的 consumed 语义，auto 决策写入独立 consumed 集合） | 若用同一 `answered_by` 标记即可复用；无需新状态 | 当前**有**部分：`_consumed_gate_ids` 已保证同 id 只消费一次（但见 F6-D1 溢出） | 同一人工裁决被重放（已修）；auto 若无去重则每 tick 新 gate 一个新 id，去重自然失效 ⇒ 见 (c)。 |
| A5 auto 批准只给"一轮"并**不写回** `approved`（例如记为 `approved` 但 `answered_by=conductor-auto` 且 credit 过滤） | 语义上"批准但不给预算"可能让 key 立即再次 stalled → 需要 (c) 的振荡护栏 | 当前**无**；`answered_by` 自由文本（`gates.py` `FRONTMATTER_FIELDS:68-80`，`_to_gate` 只要求非空字符串） | 批准后 key 立刻同因失败再 stall（FM 洪泛形态）；判据 = 同 key `resume→stalled` 循环间隔 ≈ 1 tick。 |
| A6 延迟生效窗（gate `created_at` 至今 ≥ T 才允许 auto；`gates.py` 已写 `created_at`） | **零新状态**（`created_at` 在盘上）；T 与人类响应时间冲突 | 当前**有**时钟：gate 文件 `created_at`；但**无** auto 判据 | 人还没来得及看一眼就被机器过了；判据 = 人类回答集里"如果晚 T 分钟"会改变答案的比例（**当前无此数据**）。 |

#### (b) auto-reject ⇒ `closed-legacy ∈ _DEP_SATISFIED` 解锁依赖 + 放行 stage 收口（RQ-6 反作用 1）

| 机制候选 | 代价 | 可检测信号（当前？） | 缺位时首个失败模式（判据） |
|---|---|---|---|
| B1 **绝不 auto-reject**（closed-legacy 只能人工产生）；auto 只允许 approve | 把"无人值守关闭"永远排除；夜跑遇到真该关的 key 仍停 | 当前**有**（因为根本没有 auto） | 不适用（该机制就是防这条）。 |
| B2 auto-reject 仅影子模式（记录建议、不写文件） | 需"影子记录"落点（可复用 timeline 新事件 + gate `note`），且人要真看 | 当前**无**影子记录面 | "建议了没人看" = 与 (d) 同型；判据 = 影子建议数 > 0 而无人复核。 |
| B3 若必须 auto-reject，先把 `closed-legacy` 从 `_DEP_SATISFIED` 摘除（`conductor.py:56`） | **改全局语义**，撞 P-018/P-019 冻结判据；依赖方/收口全部行为变化 | 当前**有**锚点：`_DEP_SATISFIED:56`、`_deps_satisfied:2153`、`_stage_closure:616-631` | stage 带未验证 key 收口；判据 = `gate-answered ... closed-legacy` 之后**同 tick** 出现依赖方 `dispatch`，或 `stage-close` gate 在存在 `achieved.md` 遗留草稿时被创建。 |
| B4 auto 决策类型白名单：只允许"不产生终态"的 gate（approve stalled / stage-close confirm），**排除**任何会写 `closed-legacy` 的 reject | 同 B1；需在决策点显式枚举 | 当前**有**枚举点：`_apply_stalled_rejections:2363`、`_consume_answered_gates:349-378`（stage-close reject→halted） | 白名单漏一个分支即静默降级；判据 = 代码里出现第 2 条写 `closed-legacy`/`halted` 的路径。 |
| B5 收口前加"遗留项清单"人工门（auto-reject 可以，但 stage-close 必须人确认） | 多一个人工 gate（夜跑仍可能停）；需 `achieved.md` 遗留项机器可读 | 当前**有**产物：`achieved.md` 的 `## 遗留问题（stalled 草稿）`（`mark_stalled:3984-3993`）、`patterns/<key>/stall-lesson.md`；但**无**机器判定它非空 | auto 关单后 stage 直接收口；判据 = `stage-close` 事件的 key 集合含带非空遗留草稿的 key。 |

#### (c) 自动决策与 `advance_stall_ticks` 的 stalled↔running 振荡（RQ-6 反作用 3；FM 6684 洪泛已实证）

| 机制候选 | 代价 | 可检测信号（当前？） | 缺位时首个失败模式（判据） |
|---|---|---|---|
| C1 同 `(key, loop/stage)` 自动处置次数上限（照抄 P4 范式） | 需持久计数：可落 gate/新侧车（锁面，见 F5）或从 timeline 重推 | 当前**无** auto 计数；有先例：xkey ticket `proposal_attempts`/`proposal_exhausted_at` | 无限重放/重批；判据 = 同 key 自动批准数 > 上限仍继续。 |
| C2 冷却窗口（同 key 两次 auto 决策间隔 ≥ T） | 零新状态（用上一条 auto `gate-answered.ts` / gate `created_at`） | 当前**无** auto 时间戳；可用 timeline ts | 每 tick 一次自动决策（洪泛速率）；判据 = 同 key 相邻两次 auto 决策间隔 ≈ `poll_interval_sec`（4s）。 |
| C3 进展门（两次 auto 之间必须出现新的 `advance exit=0` 或新 `dispatch` 行，否则升级人工） | 需解析 timeline/行状态；判据清晰 | **有原材料**：`advance` 事件 detail `edge exit=0`（`conductor.py:887`）、`dispatch` 事件、worker 行；**无**"自上次 auto 后是否有进展"的判定 | 每次"重试"都无新进展；判据 = 两次 auto 决策之间 advance 事件里 `exit=0` 数为 0。 |
| C4 只对"答案唯一且可逆"的 gate 自动（边界属 RQ-10） | 不属本卡；需 RQ-10 的白名单 | — | — |
| C5 振荡熔断（同 key 窗口内 `stalled` 次数 > N ⇒ 停 auto 并挂文件驱动 stop gate，复用 P6） | 需窗口计数 + 一个 stop 载体（goal-change gate 可复用其 halt 语义） | 当前**有**硬停杆范式（P6）但**无**自动触发；gate 目录文件数是人工判据（pitfalls §42.6） | 洪泛复现；判据 = `_autopilot/gates/` 文件数单调增长（同类 pending > 10）且非 beat 事件间隔 > 阈值（FM 实测 6684/11.41h，585.8/h，peak 17/min）。 |

#### (d) 注意力掩盖（RQ-6 反作用 4；FM §42.4"掩盖真实 stalled 信号"是既有先例）

| 机制候选 | 代价 | 可检测信号（当前？） | 缺位时首个失败模式（判据） |
|---|---|---|---|
| D1 auto 决策强制留痕：`answered_by=conductor-auto`（或 `auto:<rule-id>`）+ timeline 专属事件 | 需要两侧镜像（Python `answered_by` 无枚举，TS `answerGate` 只重写 4 字段）；新事件类型需进 `EVENT_TYPES` 两侧 | 当前**无**：`answered_by` 自由文本（`gates.py:68-80`）；`gate-answered` 事件 detail = `<id> approved → <key> running`（`conductor.py:2349`），**不含 answered_by**；monitor 只渲染 pending gate（`monitor.ts:644-655`） | 人无法区分"机器过的"和"我过的"；判据 = gate 文件 `answered_by` 无 auto 值域，timeline 无 auto 事件。 |
| D2 早上汇总（nightly digest：列出过去夜 auto 决策 + 影响面） | 需新视图（CLI/doctor/面板三选一）；纯读文件可实现 | 当前**无**：`/autopilot gates` 只列 pending（`console.ts:182-200`）；`mw doctor` autopilot 段只报 xkey（`mw_common.py:2022-2065`） | 夜里的自动动作没人复核；判据 = auto 决策数 > 0 而 digest 视图不存在/为空。 |
| D3 面板 auto badge/计数（monitor 行加 `auto N`） | `monitor.ts` 需读 gate `answered_by` 或 timeline；面板行长度预算 | 当前**无**；面板有 slots/keys/gates 三段（`:596/:603-627/:644-655`） | `stalled 0` 被当作"全好"；判据 = 面板 stalled 计数为 0 但有 auto 决策。 |
| D4 `mw doctor` issue：存在未复核 auto 决策时告警 | 需 doctor 段扩展（`_doctor_autopilot:2022` 目前零 stall/slot/gate） | 当前**无** | CLI 侧完全不可观测（RQ-8/RQ-6 已记录同一缺口）。 |
| D5 延迟生效（先记录 N 分钟，人可拦；复用 `created_at`） | 需"待生效"表示（gate 文件一个新字段或 note 约定）；等于 A6 | 当前**无** | 见 A6。 |

**F2 结论**：**四条副作用当前都无任何机器可检测信号**——这正是"cap 阻塞零痕迹"的同型问题。任何方案的第一步都必须是 D1（auto 决策留痕），否则 (a)~(d) 全部不可观测；第二步才是 A2/A3/C1/C2/C5 的"上界 + 窗口"。
### 【事实】F3 — 配额阈值的数据依据（回放估算）

#### 样本与答案分布（复算口径见上）

| 项目 | 窗口（timeline） | 窗口长 | gate 文件 | stage-confirm | stage-close | stalled | rejected | pending | 全部由人批准？ |
|---|---|---|---|---|---|---|---|---|---|
| FM | 2026-09-23T09:06:44Z → 2026-09-26T07:40:05Z | 70.6h | 10 | 2 / 2 approve | 1 / 1 approve | 7 / 7 approve | 0 | 0 | 是（`user-via-pm-window` 10/10） |
| E2 | 2026-09-22T03:35:07Z → 2026-09-26T07:40:03Z | 100.1h | 18 | 3 / 3 approve | 2 / 2 approve | 13 / 13 approve | 0 | 0 | 是（`wenbozhou` 17 / `human-pm-window` 1） |

- **`budget-exhausted` / `goal-change` / `xkey-authorize`：零实例**（两项目 0 个 gate 文件、0 个 timeline 事件）⇒ **无法估算**，需要的数据见"数据缺口"。
- stall 等待中位/最大：FM `3.62h / 15.19h`，E2 `4.04h / 17.40h`（与 RQ-6/RQ-8 实测一致）。

#### 回放规则 A：对"历史答案 100% 一致"的 gate 自动过

规则（可直接复算）：`auto(kind) := (rejected==0 and pending==0 and approved>0)`，对历史中 `status==approved` 的该类 gate 计为"会被自动过"。

| 项目 | 100% approve 的 kind | 会被自动过的 gate 数 | 按夜分布（UTC+8 22:00–08:00） | 最大单夜 |
|---|---|---|---|---|
| FM | stage-confirm(2/2), stage-close(1/1), stalled(7/7) | **10** | `2026-09-23: 2` | **2** |
| E2 | stage-confirm(3/3), stage-close(2/2), stalled(13/13) | **18** | `2026-09-22: 1`、`2026-09-23: 1` | **1** |
| FM+E2 | 同上（合并） | **28** | `2026-09-22: 1`、`2026-09-23: 3` | **3** |

`_resume_credits` 消费量（按现口径：每个被自动 approve 的 stalled gate 给该 key **每个** cap 回路各 +1 轮）：

| 项目 | approved stalled | per-key credit（窗口末） | 最大 credit/key | 折合 `limit=round_budget(2)+credit` 最大 |
|---|---|---|---|---|
| FM | 7 | `gui-skeleton-shell: 2`，其余 5 key 各 1 | **2** | 4（每个 cap 回路） |
| E2 | 13 | `feature-gui-time-mvp-board: 3`、`feature-false-meets-remediation: 3`，其余 6 key 各 1 | **3** | 5（每个 cap 回路） |

⇒ 在**真实历史**上，"100% 一致"回放被自动过的量很小（28 个 / 149h 合并窗口；单夜 ≤3），credit 增量 ≤3/key。**但这只说明"当人一直在场时，门很少"，不说明"无人值守时也这么少"。**

#### 回放规则 B（关键反证）：洪泛窗口下"自动批准 + 无去重/无配额"

FM 洪泛是**已发生的实测**（RQ-6/A-04 / `_pitfalls.md §42.4`）：同一人工批准被无限重放 ⇒ 6684 个 pending stalled gate。若当时叠加"自动批准且无 per-key/每夜 cap"：

| 量 | 实测/推算 | 来源 |
|---|---|---|
| 洪泛 gate 数 | **6684**（全部 `pending`，`gate-0004..gate-6687`） | 目录实测 |
| 窗口 | 2026-09-23T15:37:12Z → 2026-09-24T03:01:32Z = **11.41h** | 文件 `created_at` |
| 速率 | **585.8 个/h ≈ 9.76/min**，峰值 **17/min** | 实测 |
| 单夜（UTC+8 22:00–08:00） | **5364 个**（同夜 08:00–11:01 另有 1320 个） | 实测 |
| 涉及 key | 2 个（`gui-contract-surface` 5587 / `gui-shell-spike` 1097） | 实测 |
| 若自动批准这些 gate 的 credit | 这 2 个 key 的 `_resume_credits` 会从实测的 **1** 变成 **数千**，`limit = round_budget(2) + credit` 随之数千 | **[推断]**（未真的开启 auto，历史只证明"pending 不放大"，见 A-04"纯文件+事件洪泛、不放大执行量"） |

⇒ **可检测信号的缺失正在此处**：洪泛期间 `_resume_credits` 恒为 1 恰恰是因为门全是 `pending`（没人批）。若引入 auto-approve，同一个 4s tick 循环会把"未放大"变成"放大"；**这就是 (a) 无上界的量化形态**（单夜数量级 10^3，速率受 `poll_interval_sec` 控制）。

#### 算法与不确定性

- 算法：解析每个 gate 文件的 frontmatter；`auto(kind)` 按"历史 100% approve"筛选；计数 = 符合条件的 approved gate 数；按夜分桶的最大值 = 最大单夜；credit 按 key 聚合。
- 不确定性：① **选择偏差**——所有 28 个 gate 都是"人在场"时被批准，100% 一致是"人在场"的产物，不能外推到无人值守；② 3 个 kind 零实例；③ 夜分类依赖 UTC+8 换算（**推断**）；④ 洪泛门无 `answered_at`，规则 B 是反事实推算；⑤ 无 token 账本 ⇒ credit 的成本（token/时间）**无法估算**，需要逐 worker token 账本或 proxy 日志。

### 【事实】F4 — kill switch 与审计现状

**停止杆（两条，语义不同）**：

| 杆 | 语义 | 生效路径 | 锚点 |
|---|---|---|---|
| `enabled=false` | serve **terminate** conductor（全停；autopilot 不再 tick） | serve 每轮 `_conductor_decision(enabled, pid_alive)` → `proc.terminate()` | `mw.py:140-196`；写入 `console.ts:319-325`；落盘 `config.save_config:150` |
| `paused=true` | conductor **存活**、继续写 `beat`、但不 `orchestrate`（软停） | `tick` 第 2 步：`if not cfg["enabled"] or cfg["paused"]: return "idle"` | `conductor.py:2060`；面板文案 `monitor.ts` conductorIntent；写入 `console.ts:371-385` |

**能否"只停自动决策不影响 autopilot"**：**不能**。现有两个杆的粒度都是"全局 autopilot"，没有"自动决策子系统"这一层；也没有任何 auto-gate 键。要支持必须**新增键**（例如 `auto_gate_enabled` / `auto_gate_paused`），代价：
- `config.py` `DEFAULT_CONFIG` + `_BOOL_FIELDS`/`_INT_RANGES`（fail-closed）；
- TS 镜像 `status-model.ts DEFAULT_CONFIG/BOOL_FIELDS/INT_RANGES/saveConfig`（P-021 两侧一致）；
- 机器层覆盖需加进 `effective_config.EFFECTIVE_KEYS`（当前仅 2 个 xkey 键，`effective_config.py:66-70`），否则机器层覆盖会走"非机器可覆盖 ⇒ origin=project/default"路径；
- 新增键必须能被 console/`mw autopilot verify` 两条写路径材料化，否则出现"看起来改了其实没改"（风险 5）。

**替代的零新键硬停杆（推荐给 design 参考，不决策）**：复用 P6——挂一个 pending `goal-change` gate 会让 `tick` 在 `orchestrate` 前 `return "halted-goal-change"`（`conductor.py:2064-2113`，`goal-halt` 事件 `:2093`）。它停的是整 tick，不是只停 auto；若要"只停 auto 不停别的人工 gate"，仍需新粒度。

**批量回看 / 撤销能力**：

| 能力 | 现状 | 锚点与判定 |
|---|---|---|
| 列出"已自动过"的 gate | **不存在**。`/autopilot gates` 只列 `status==pending`（`console.ts:182-200`）；timeline 可查 `gate-answered`（`status-model.ts queryTimeline`），但**事件 detail 不含 `answered_by`**，无法按"谁答的"过滤 | `gate-answered` detail = `<gate-id> approved → <key> running`（`conductor.py:2349`；reject `:2388`）；`answered_by` 只在 gate 文件 |
| `_consumed_gate_ids` 是否可逆 | **不可逆**。它由 `timeline.query_events` 的 `gate-answered` 推导（`conductor.py:297-313`），timeline 是 append-only、无删除/改写 API（`timeline.py` 只有 append/rotate，rotate 不改写内容） | `conductor.py:297-313` + `timeline.py:append/rotate` |
| 把 gate 文件改回 `pending` 能否"撤销" | **不能重新生效**。`:2319`（approve）先看 `gate.id in consumed`；id 已消费 ⇒ 即使文件回 pending/再次 approved 也不会被再次应用。要重新触发必须**新 gate id** | `_apply_stalled_approvals:2315-2319` |
| `_apply_stalled_rejections` 的消费记录 | **缺失**：该函数**不检查** `_consumed_gate_ids`（只按 `status_of[key]=="stalled"` 去重）——与 approve 路径不对称 | `_apply_stalled_rejections:2363-2420`；对比 `:2315-2319` |
| 真正"撤销"一条已应用的 key-status 变更 | 只能**手改** `_roadmap.md` 的 `key-status:` 行（**不留 timeline 事件**）；这正是 RQ-6 F1 的解除路径 3 | RQ-6 F1；`roadmap.update_key_status` 无反向 API |

⇒ 审计现状 = "**有 append-only 事实、无按来源分类的视图、无撤销原语**"。任何 auto 决策方案必须补：`answered_by` 的机器可判定值域 + 一个"auto 决策清单"视图 + 明确的"不可撤销、只能人工改 roadmap"声明（或新增撤销原语）。

### 【事实/推断】F5 — GC 校验

| 机制候选 | GC-1（不得引入内存控制器，每 tick 由文件重推） | GC-3（新增落盘状态的锁面） | 判定 |
|---|---|---|---|
| A1 credit 过滤 | PASS：`_resume_credits` 已每调用重推 gate 目录，只加一个谓词 | 无新状态 | 合规 |
| A2 per-key 每夜配额 | PASS（若从 timeline `gate-answered`(auto) 窗口扫描推导） | 无新锁（timeline append-only，conductor 单写） | 合规（**必须**走 timeline 推导，不得用内存 counter） |
| A3 全局熔断 | PASS（同 A2） | 无新锁 | 合规 |
| A4 同 gate 自动次数 | PASS：复用 P5 的 `_consumed_gate_ids` 语义 | 无新状态（消费在 timeline） | 合规；**前置修 F6-D1** |
| A6/D5 延迟生效窗 | PASS：`gate.created_at` 已在盘上 | 无新状态 | 合规（零成本） |
| C1 每 (key,loop) 处置上限（落盘计数） | PASS（可每 tick 从 gate 目录含新字段/或 timeline 重推） | **若新增侧车/新 gate 字段**：gate 字段走 `gates.lock`（现成）；侧车需像 xkey 一样新增专属锁（`xkey.py:102` 范式）⇒ **有锁面成本** | 条件合规：优先"从 gate 目录/timeline 重推"，避免新锁 |
| C2/C3/C5 冷却/进展/熔断 | PASS（时间与事件均在盘上） | 无新状态 | 合规 |
| D1 auto 标记（`answered_by` 值域 + 新事件类型） | PASS | gate 字段走 `gates.lock`；timeline 无锁 | 合规；**需两侧镜像**（`EVENT_TYPES` 两处、`FRONTMATTER_FIELDS` 两处） |
| D2/D3/D4 视图（digest/badge/doctor） | PASS（只读推导） | 无新状态 | 合规 |
| **反面（违反 GC-1）** | 任何把"今晚已自动几次"存活在 `ConductorState`/模块全局/内存队列的方案 | — | **违反 GC-1**：conductor 重启即丢失 ⇒ 计数归零 ⇒ 夜跑无界；必须禁用 |
| **反面（违反 GC-3）** | 任何新增可写侧车/队列但不定义锁、或复用 `_workers.parallel` 的锁去写 gate/配额 | — | **违反 GC-3**：并发写竞争（P-018/P-019 家族） |

### 【事实】F6 — 护栏级代码缺陷（自动决策的硬前置）

**D1（最严重）：`_consumed_gate_ids` 的正则只认 4 位 gate id。**
- 代码：`re.match(r"(gate-\d{4})\b", str(ev.get("detail", "")))`（`conductor.py:310-312`）。
- 判定：`gate-9999` 命中，`gate-10000` **不命中**（`\d{4}` 匹配 `1000`，其后 `0` 与 `\b` 不构成边界，无法回退）。gate id 由 `gates._next_seq` / `GATE_FILE_RE = ^gate-(\d+)\.md$` 无上限生成 ⇒ id 可超 4 位。
- 影响：一旦自动决策把 id 推过 10000，持久消费护栏**静默失效**，`_apply_stalled_approvals` 回到 FM 洪泛的"状态推导幂等"形态（`4e874f5cc` 修复被绕过）。FM 洪泛已达 `gate-6687`，距 10000 只差 ~3313 个 gate——在"每个停滞事件自动过"的方案下是**一夜可达**的量级（实测 585.8/h）。
- 判据：`python -c "import re; print(re.match(r'(gate-\\d{4})\\b','gate-10000 approved -> k running'))"` → `None`（本卡实测）。
- **建议护栏**（候选，不决策）：把正则放宽到 `gate-(\d+)` 或直接用 gate 对象的 `id` 与 `answered` 事件做集合比较；并补一条 `gate-10000` 的回归用例。

**D2：`_apply_stalled_rejections` 没有消费记录。** `_apply_stalled_approvals` 有 `gate.id in consumed` 守卫（`:2315-2319`），reject 路径只按 `status_of[key]=="stalled"` 去重（`:2363-2420`）。在正常流程下 reject 后 key 变 `closed-legacy`、永不再 stalled，故实际风险低（**[推断]**，未找到触发样本）；但"批准有消费记录、拒绝没有"是不对称的，任何新增"自动 reject"方案会直接踩在没有消费护栏的那一侧。

**D3（附带）：TS 镜像 `EVENT_TYPES` 缺 `target-config-rejected`。** Python `timeline.py:67-84` 17 类含 `target-config-rejected`；TS `status-model.ts:779-796` 16 类**不含**。新增 auto 事件类型时必须同时补两侧，否则面板/CLI 的默认过滤集会不一致（P-021）。

## 结论 → 决策映射

> 说明：快照 `spec.md`（15:45）的 AC 止于 **AC-015**、风险止于 **风险 10**、U 止于 **U-7**；任务书引用的 AC-016..019 / 风险 11..12 / U-8..U-9 在该快照中尚不存在。本卡按任务书对 AC-017/018/019 的定义作答，编号以 PM 锁号为准。

- **支撑 AC-017（逐条副作用 → 机制候选 + 可检测信号）**：F2 表逐 (a)~(d) 给出候选、代价、信号、首个失败模式。核心结论：**当前四条副作用全部零机器信号**；护栏第一步是 D1（`answered_by` 自动值域 + timeline auto 事件），第二步才是上界（A2/A3/C1/C2/C5）。
- **支撑 AC-018（配额阈值的数据依据）**：
  - 三层结论：(i) **有实例的 3 个 kind** 在 28 个 gate / 149h 合并窗口上 100% approve，单夜 ≤3、credit ≤3/key——这只是**粗上界**；(ii) **3 个 kind 零实例** ⇒ 无法估算；(iii) 选择偏差（人一直在场）⇒ **不能**用"历史 100% 一致"直接定无人值守阈值。
  - 洪泛反证给出**唯一可量化的失败速率**：585.8 gate/h（peak 17/min）、单夜 5364、2 key——阈值应参照"失败速率 × 可容忍夜长"，而不是参照"历史答案一致性"。**具体数值留给 design/PM（本卡不决策）。**
- **支撑 AC-019（kill switch 与审计）**：F4。现状 `enabled`/`paused` 是全局杆；"只停自动决策"**需要新键**且必须走两侧镜像 + 机器层判定；`_consumed_gate_ids` **不可逆**，撤销只能手改 `_roadmap.md`（无事件）；批量回看/按来源过滤**不存在**。
- **支撑 U-8（"由数据定"是否可行）**：**部分可行、边界清楚**。可行的是"哪些 kind 历史答案一致"（3/6 类有数据；另 3 类零实例）；不可行的是"阈值多少"——历史没有"无人值守"样本（所有 gate 都被人应答），也没有 token 账本。**建议 design 期先做影子模式（只记录 auto 建议、不动作）收集无人值守样本**，再定阈值；阈值至少要有上界（C1/C2/C5）与全局熔断（A3），不能只有"一致性"判据。
- **U-9**：快照中不存在；按本卡范围理解为 kill switch/审计粒度（F4 覆盖）。若 U-9 另有定义，请 PM 校正后本卡可补。
- **给 design 的护栏硬前置（不含方案选择）**：① 先修 F6-D1（消费护栏溢出），否则任何"自动过很多 gate"的方案会重演洪泛；② auto 决策必须留痕（D1）才能被 (a)~(d) 的护栏检测到；③ 复用 P4（尝试上限 + 持久 exhausted）与 P5（消费去重），不自造内存计数器（GC-1）；④ 新增落盘计数必须声明锁面（GC-3）；⑤ 阈值不得只凭"历史 100% 一致"。

## 数据缺口

1. **`budget-exhausted` / `goal-change` / `xkey-authorize` 零实例**：无法回放其答案分布、也无法估其自动过后果。需要什么数据：这三类 gate 的真实发生样本（或受控实验）。
2. **无"无人值守"历史样本**：20/20 stalled gate 都是人在 0.19–17.40h 内应答。要量化"无人值守下自动决策的收益/风险"，需要影子模式（只记录不动作）跑至少一个完整夜窗。
3. **夜分类依赖 UTC+8 换算**（`[推断]`）：输入为带时区 ISO8601，但"夜"的定义是我方约定；若 PM 的夜窗定义不同，最大单夜数会变。
4. **洪泛门无 `answered_at`**：规则 B 的 credit 放大量是**反事实推算**（[推断]），不是实测；实测只到"6684 pending / 单夜 5364 / 585.8 个·h⁻¹"。
5. **无 token/成本账本**：credit 的 token 成本、自动决策的成本增量**无法估算**；需要逐 worker token 账本或 proxy 日志。
6. **样本仅 FM/E2 两项目、合并 149h**：JC 的 gate 事件已被 rotation 剪掉（RQ-6 数据缺口 2），不可用于回放。
7. **当前无 auto 决策信号**：`answered_by` 无枚举、timeline 无 auto 事件 ⇒ 未来要对 auto 决策做回放，必须先有 D1 的留痕（否则重演"零痕迹"）。

[VERIFY] RQ-11: reusable_primitives=9(P1..P9) resume_credits_bound=no(no cap, no per-night window; counts approved stalled gates per key) replay_auto_gates=28(FM10+E2 18, all 3 observed kinds 100% approve) max_per_night=3(UTC+8 22:00-08:00, FM+E2; FM2/E2 1) kill_switch=exists(global only: enabled=false terminates conductor mw.py:140-196; paused=true soft-stops orchestrate conductor.py:2060; NO auto-decision-only granularity -> needs new key) consumed_gate_id_regex_overflow=yes(gate-10000+ silently escapes _consumed_gate_ids conductor.py:310-312; FM reached gate-6687) reject_path_consumption_guard=missing(_apply_stalled_rejections:2363-2420 vs approve:2315-2319) flood_gates=6684 pending/11.41h/2 keys, one night=5364, peak=17/min, rate=585.8/h auto_decision_trace=missing(answered_by free text gates.py:68-80; gate-answered detail lacks answered_by conductor.py:2349; monitor renders pending only monitor.ts:644-655; doctor autopilot section has zero gate/stall content mw_common.py:2022-2065) audit_reversible=no(_consumed_gate_ids derives from append-only timeline; gate re-pending does not re-apply; only manual _roadmap.md edit, no event) ts_mirror_drift=EVENT_TYPES missing target-config-rejected(status-model.ts:779-796 vs timeline.py:67-84)