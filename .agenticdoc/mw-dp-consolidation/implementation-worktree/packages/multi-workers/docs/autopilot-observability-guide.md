# Autopilot 可观测面与生效动作（mw-autopilot-gate-alarm-liveness）

本手册是 key `mw-autopilot-gate-alarm-liveness` 落地的**运行期可观测面**收口文档。它回答一个问题：**现在卡在什么地方、卡了多久、为什么没提醒我、需要重启什么才看得到。**

三个第一性目标（`spec.md §0.1`）：

1. 阻塞必须可见——pending 门禁与 stage 主闸由**磁盘状态派生**、不依赖事件推送（事件会停、会衰减、会被 10MB×3 轮转挤出尾窗）；
2. 派发不得以"某窗口接管（`switch_key`）该 key"为前置——无人值守下 conductor 以**合成 claim** 接管；
3. 能自动放行的小门（`stage-close`）自动收证放行，人只面对真正的 judgment 门。

> 行号口径：下列 `path:line` 为**当前工作树**的 1-based 行号（baseline `cc9a46a1a` + 本 key 未提交改动）。行号会随后续提交漂移，定位一律以**符号/字符串锚**为准（P-07）。本 key 收口时对卡面种子锚点做过校准：卡面 `conductor.py:5742/:7193/:3933`、`change-ledger.ts:804`、`output-writer.ts:76` 为旧口径，实测为 `:6374/:7644/:4324`、`:812`、`:78`。

## 0. 生效动作总表（先看这张）

| 改动面 | 例 | 必须执行 | 为什么 |
|---|---|---|---|
| **Python**（`packages/multi-workers/**.py`） | `autopilot/conductor.py`、`autopilot/gates.py`、`mw.py`、`mw_common.py`、`autopilot/index_parallel.py` | **`/mw restart`**（每个项目各一次） | conductor 是 serve 的第三子进程，Python 只在启动时 import；旧进程不会因源文件更新而生效 |
| **TS 扩展**（`packages/coding-agent/src/extensions/agent-team-loop/**`） | `autopilot/monitor.ts`、`autopilot/status-model.ts`、`pm/*.ts`、`shared/*.ts`、`worker/*.ts` | **`mw build --install`（或 `/mw build`）+ `/mw restart` + `/reload`** | bundle 需重建并装到全局扩展目录；pi 窗口需 `/reload` 重新加载扩展；`/mw restart` 保证同批 Python 面同步生效、两侧同版本 |
| 只读 CLI 视图（不常驻） | `mw autopilot gates`、`mw status`、`mw doctor`、`mw autopilot answer` | 无需重启 | 每次是新进程，直接读磁盘/源码 |

**运行期实证（写进卡面、必须保留的教训）**：T-16 终态在**旧 bundle** 下仍报 4 条"已修"误判——TS 账本（`shared/change-ledger.ts`）修复只有在 `build --install` + `/reload` 之后才生效；源码改了、bundle 没重建 = 行为没变。**"源码即现实"不成立。**

**两侧同版本上线纪律**：Python 与 TS 的 config schema 互相 fail-closed（未知键即整份作废）。TS 镜像入口 `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts:167 BOOL_FIELDS`（对应 Python `autopilot/config.py::_BOOL_FIELDS`）。任何触及 config/schema 的改动必须**先 `build --install`，再重启各 pi 窗口的 serve**，否则旧 bundle 读含新键的文件会 fail-closed（README "两层配置 → 两侧同版本上线"）；跨语言一致性由 `autopilot-config-parity.test.ts` / `autopilot-config-sync.test.ts` / `mwgal-t20-config-parity.test.ts` 锁定（本 key 的 `envelope_fallback` 可选键教训：注册表条数 = 20 默认键 + 1 可选键，`npm run check` 不跑测试 ⇒ parity 红漏过 check）。

---

## 1. 常驻状态面：pending 门禁行 + stage 主闸行 + 六值抑制原因

**数据来源**：`.agenticdoc/_autopilot/gates/*.md`、`_roadmap.md`、`auto-decisions.jsonl`——每帧从磁盘现读并在读面派生，**无 cap、无衰减、无去重**，不依赖任何 timeline 事件（AC-001）。

- 采集：`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:420 readMonitorState`（`MonitorSnapshot` 收全量 pending gates；单文件读失败进 `queueFailures`）。
- 渲染：`monitor.ts:1164 renderMonitorLines` 的 gates 段；单行编码器 `monitor.ts:1105 renderPendingGateLine`。
- 行宽上界：`monitor.ts:85 MONITOR_LINE_MAX = 110`。

**stage 主闸行（AC-016，"派发为什么停"的直接答案）**：`monitor.ts:638 deriveMonitorStages` 为 `_roadmap.md` 每个 stage 产出一行——状态（`pending/running/closed/halted`）+ 卡在哪道门（`stage-confirm`/`stage-close`/`stalled`/`budget-exhausted`/`goal-change`，`STAGE_BLOCKER_KINDS`）+ 已等时长 + **被冻结的 key 列表**（`status ∈ {stalled, pending-review}`）。`halted` 自名 blocker（无门可放行，只能人工改 `_roadmap.md`）。这是唯一能覆盖"没有 running stage、也没有 gate"这种形状 A/C 而不只是逐 gate 形的面。

**六值抑制原因（AC-003，封闭枚举，派生不落盘）**：

| 值 | 含义 |
|---|---|
| `gate-queue-unreadable` | 队列本身读不到（目录扫描失败 / 路径是普通文件） |
| `key-in-flight` | 该 gate 所属 key 有在飞 worker（**per-key**，非项目级） |
| `cap-reached` | 提醒打断次数已达 `gate_reminder_max` |
| `stage-terminal` | gate 可证属于已终止 stage |
| `not-due` | 未到 `age >= n * gate_reminder_after_min` |
| `unresolved-scope` | **正交标记**（scope 不可解析），不是抑制原因 |

- 权威声明：`packages/coding-agent/.../autopilot/status-model.ts:696 GATE_REASONS`、`:707 GATE_SUPPRESSION_PRIORITY`（漏斗序，优先级自上而下）、`:712 GATE_SCOPE_UNRESOLVED`、`:738 deriveGateReason`。
- Python 侧同口径：`packages/multi-workers/autopilot/conductor.py:2950 pending_gate_reminders`（抑制漏斗，注释逐条写明优先级即归因优先级）；`conductor.py:2930 _REMIND_SUPPRESSED_PHASE`。

**优先级 = 代码漏斗序**：`gate-queue-unreadable > key-in-flight > cap-reached > stage-terminal > not-due`；`unresolved-scope` 与抑制正交。**本轮到期必须显式写 `reason=-`**（不可用空值冒充"未知"）。

**fail-open 边界**：key/stage 不可解析的 gate（存量 JCodingAss `gate-0007`/`gate-0008` 是 `stage-close` 且 key 为空）**一律不抑制**——缺记录不得静音。

---

## 2. 编码与预算：`~D`、`R:*`、紧凑 age、`+N`、`J`/`P`、110 列 fit ladder

为在 110 列内**永不丢三件必显事实**（证据漂移、抑制原因、已等时长），T-10b 引入固定编码表与确定性 fit ladder（`monitor.ts:1005-1104` 注释即完整编码表）：

| 记号 | 含义 |
|---|---|
| `~D` | 证据漂移（evidence mtime 新于 `created_at`；紧凑形式取代 verbose 的 `DRIFT(mtime>created_at)`，**永不丢**） |
| `R:queue` | `gate-queue-unreadable` |
| `R:flight` | `key-in-flight` |
| `R:cap` | `cap-reached` |
| `R:term` | `stage-terminal` |
| `R:notdue` | `not-due` |
| `R:scope` | `unresolved-scope` |
| `R:due` | 无抑制（到期，verbose 为 `reason=-`） |
| `J` | blocker_class=`judgment`（人必须决定；**缺字段/空值/枚举外的 fail-closed 折叠**——v1 存量 gate 全落这里） |
| `P` | blocker_class=`paperwork`（证据可确定性收集，自动放行候选） |
| `+N` | 本行压缩掉的次要字段数（可见留痕） |
| `age=<n>s/m/h/d` | 紧凑 age |

- 编码常量：`monitor.ts:1050 GATE_DRIFT_MARK`、`:1057 GATE_BLOCKER_MARK`、`:1061 GATE_REASON_CODE`、`:1082 GATE_DROP_RANK`。
- **fit ladder（首个 fit 胜出）**：① 恢复命令由全 `-> /autopilot gate <id> approve|reject` 降到短 `-> /autopilot gates`；② 压缩级别 0→2（full age+reason → compact age+full reason → compact age+compact reason，`~D` 恒紧凑）；③ 次要字段丢弃阈值 0..5，丢弃序 `code= → scope marker → stage/key → reminders= → blocker 标记`，**blocker 标记最后丢**，每丢一个计入 `+N`。ladder 先压缩必显字段的**格式**（可逆）再丢次要字段，最后才缩短恢复命令。
- **必显三件套（`~D`/age/reason）没有 drop rank，永不丢**——这是对 DRQ-2 发现的"事故形状下现行 drop 序先丢 reason 再丢 age"的修正（spec 坑点 9）。

---

## 3. 抑制可视：per-key 抑制 + `remind-suppressed` 留痕 + cap 降级 + 双通道

**per-key 抑制（AC-002）**：抑制判据从"整个 `_workers.parallel` 有在飞工作"（项目级，任意 key 在飞即全项目静默）改为**该 gate 所属 key**。派生点 `conductor.py:2950` 条件 1；`blocked_on_human` 三处实现必须同批改（否则面板与发射器互相矛盾）：

- `packages/multi-workers/mw_common.py:3354 _blocked_on_human`（per-key）
- `autopilot/monitor.ts:607 blockedOnHuman(gates.length, nonTerminalRows, {…})`
- `autopilot/status-model.ts:1586 blockedOnHuman(..., perKey?)`

**`remind-suppressed` 留痕**：被抑制的 gate 每窗口留一条 append-only 台账行 `.agenticdoc/_autopilot/auto-decisions.jsonl`，`phase:"remind-suppressed"`，携 `gate_id/kind/key/reason/bucket/reminder_n/waited_min/suppressed_at/detail`（detail 含 act 提示）。写入点 `conductor.py:3178 _remind_pending_gates`；去重 `seen_suppressed` 按 `(gate_id, reason, bucket)`；**重启安全**——台账是文件真值，每次 pass 重读。

**cap 降级为"打断次数"（AC-004）**：`gate_reminder_max` 用尽后不再发**中断**，但状态面照旧 pending 并显式标注"已达打断上限，仍待处理"（`conductor.py:3229`）。cap 计数唯一权威输入是 `_reminder_count`（`conductor.py:2935`，读台账 `phase:"remind"` 行，D-006：时序状态不能靠 timeline 尾窗）。

**fail-loud 双通道**：每次发射经唯一 choke point `conductor.py:3043 _emit_alarm`——stderr（随 serve 进 `.mw/mw.log`）+ timeline `config` 事件（data 携 reason/waited_min/bucket/suppressed），**不新造日志文件、不新造事件名**（P-01）。

---

## 4. serve 漂移自证：`serve.meta` 身份 + `code_digest` + `mw status`/`mw doctor` 判 `STALE CODE` + `history-only`

**事故成因（spec E7）**：运行中的 serve 比源码早 15 天，提醒守护从未存在于该进程；旧 `serve.meta` 只有 `{pid, started_at_ms, code_dir}`，无 commit/版本，且 `code_dir` 无任何读者 ⇒ "进程活着但跑旧代码"不可见。

**身份字段（AC-005）**：`.mw/serve.meta` 现含 `pid`/`started_at_ms`/`code_dir` + `commit`（**40 位 OID**）/`dirty_tracked`/`dirty_untracked`/`code_mtime_ms`/`code_digest`/`schema`/`version`。

- schema 常量：`packages/multi-workers/mw.py:120 SERVE_META_SCHEMA = 1`（旧 meta 等价 `schema=0 < 1` ⇒ "必须重启"）。
- 写入：`mw.py:161 _write_serve_meta`；身份采集**整体前置到 `_write_pid` 之前**（否则一次挂死的 git 会留下"PID 在、服务没起"的假象，违反"PID 文件存在 ⇒ 服务已起"既有不变量）。
- digest：`mw.py:5312 _runtime_digest`（runtime 文件集 sha256，实测 71 文件 / ~1.3 MB / 7.6 ms）。
- 纯文件读 commit（免 spawn）：`mw.py:5416 _git_head_oid`（`HEAD`→loose→`packed-refs`，`re.fullmatch(40 hex)`）；**永不用** `_git_head_short`（它给动态长度短 OID，与 40 位永不相等 ⇒ 永久假漂移）。
- skip 集含**目录名 `test`** 与 `test_*`/`_*` 文件（否则改夹具会把健康 serve 判 stale）。

**判据轴 = `code_digest`（权威）**：`mw.py:5495 serve_code_verdict` 决策序 `content(digest) → commit(仅 legacy meta) → capability(schema) → undecidable`。

- `content_changed` ⇒ `verdict=drift` / `reason=content-changed` ⇒ `restart_required=True`。
- digest 相等但 commit 移动 ⇒ **`history-only`**（D-009 收窄）：只记录、不告警、不要求重启——"把 dirty 树提交掉"属正常开发流，不应造成假漂移疲劳。
- `meta.schema < SERVE_META_SCHEMA` ⇒ `CAPABILITY DRIFT (schema older than checker)`。
- `mw.py:5667 _report_serve_code_drift`：serve 环路 60s 自查，限频键 `(code_dir, meta_commit, head_commit, serve_pid)`（一次漂移一次告警），走 stderr + timeline `config`；**Python 不自动重启**。

**新鲜进程侧入口 4+1**（serve 不能自证）：

1. `mw status`（打印 `serve code:` detail）；
2. `mw doctor`（drift ⇒ issues + exit 1）；
3. `mw update-env` A3（基线改 `meta.code_dir`）；
4. TS `packages/coding-agent/.../shared/mw-runner.ts:301 serveStaleness`（只保留交互恢复，不新增周期通知）；
5. 可选 OS 探针（ctypes `GetProcessTimes`）。

**具体界面**：`STALE CODE (content changed)` / `STALE CODE (head moved)` / `CAPABILITY DRIFT (schema older than checker)` / `fresh (history-only)`（`mw.py:5631-5636 _serve_code_detail`）。monitor 面板同源渲染为 `serve: PID <n> STALE CODE (...) -> /mw restart`（`monitor.ts:1181` 附近）。

**分工不重复（AC-006）**：Python 拥有持久记录 + serve 生命周期限频；TS 只保留交互恢复；同漂移在两侧不产生双份周期通知。

---

## 5. `stage-close` 自动收证放行：五判据 + `answered_by="conductor-auto:<rule>"` + `phase:"decide"` 台账 + 回落点名缺失项

**为什么是 stage-close**：它是主闸（形状 A/B 的根），且是唯一同时满足"证据可确定性机器收集 + 非 policy"的 kind（56 gate 普查：stalled 31 / stage-close 14 / stage-confirm 10 / goal-change 1）。`stage-confirm` **不自动**（"开始一个 stage"是授权，不是文书，D-014②）。

**五判据（全部从磁盘现算，gate 开着永远不够）**：`conductor.py:6374 proposition_stage_close_credentials` + `conductor.py:6932 _stage_close_facts`：

1. stage 在 roadmap 上可解析；
2. stage 全部 key 终态（`done`/`closed-legacy`）；
3. 无在飞 worker 行属于该 stage 的 key；
4. 无 done key 处于 evidence-reconciliation 争议；
5. close dossier 已在磁盘且每个 key 的终态凭据齐备（`_done_credentials_present`）。

任一记录缺失 ⇒ **falsifying（fail-closed）**；`detail` **点名缺失项**（如 `l3-verdict.txt=meets`、`l3-report.md`），使回落可审计且无需新字段。

**留痕（零新字段）**：`conductor.py:7576 answer_gate_auto` 写 `answered_by="conductor-auto:<rule_id>"` + `answer_source="conductor-auto"` + `auto_policy_id="<rule>@<version>"`；rule id 是代码常量 `conductor.py:6554 STAGE_CLOSE_AUTO_RULE_ID = "stage-close-credentials"`。每次裁决落一条 append-only 台账行 `phase:"decide"`（`conductor.py:7301 _append_auto_decision_row`；主判决入口 `conductor.py:8130 auto_decide_gates`）+ `gate-auto-decision` timeline 事件。

**安全阀（D-011 中档 + P-03）**：

- 只对**证据判据确定性（可复算 + 可留痕）且非 destructive** 的门自动；
- `stage-close` 自动放行被 `auto_gate_mode`（`off|shadow|live`，默认 `off`）+ shadow 门槛（≥5 夜 AND ≥20 决策 AND 每规则 ≥1 反例）双重 opt-in 锁住；
- 收集失败/判据不可用 ⇒ **回落人工 gate，绝不静默跳过**，并在状态面显示缺失项。

**与既有 48h 兜底不冲突**：`_process_deferred_reviews` 的 48h fallback **不是**自动闭合路径（只推 `review-escalated` 升级信号给人类，docstring 明写 "It NEVER closes the stage and NEVER rewrites a key"）——与 AC-015 互补，无需合并（D-014④ 核实结论）。

**现实基线**：本机生产台账 `phase:"decide"` = 0 行，自动批准占比 0%——本 key 交付的是**判据与安全阀**，默认关闭；开箱占比为 0 属设计内，需先跑 shadow 池。

---

## 6. re-attest 与 reject 二次确认

**re-attest（AC-008，schema 零改动）**：证据刷新后重评 = 新建 gate + `context_refs` 放 `reattest-of:<id>`，由**不依赖 `status=="stalled"` 的独立消费者**处理。

- 建 gate：`conductor.py:4271 reattest_gate`（编号取 `max(existing)+1`，不复用；原 gate 字节不变、原判定留痕）。
- 消费：`conductor.py:4324 _apply_reattests`。

**reject 二次确认（AC-009）**：`reject` 是 destructive（`stalled` reject 是全仓唯一 `closed-legacy` 写入点），单次按键不得提交。

- 拒绝在**任何写之前**返回：`conductor.py:7644 answer_gate_confirmed`（`decision=="reject" and not confirm` ⇒ `GateAnswerResult(ok=False)`，返回后果说明 `conductor.py:102 REJECT_CONSEQUENCE_STATEMENT`）。
- CLI 入口：`python mw.py autopilot answer --project <dir> --gate-id <id> --reject --confirm-destructive`（`mw.py:6385`；未给则 exit 1、零写盘；`--approve` 不需要）。
- **措辞校正（写进文档以替代夸大的"选错就废掉一个 key"）**：reject 在**状态机内不可逆**，但恢复 = 人工改 `_roadmap.md` 一行（stage 已 closed 时再改一行），代价是**无审计痕迹** + 已耗轮次不退 + 需重新 stall→approve 才得一轮；`closed-legacy ↔ stalled` 回环**只在 out-of-band（`_roadmap.md` 写者）可达**，conductor 内部无路径（14 个调用点被 `_DISPATCH_SKIP_STATUSES` 挡住）。

---

## 7. `blocker_class`：序外标量 + `None → judgment` 折叠 + monitor `J`/`P`

**schema（AC-007，P-05 兼容）**：gate frontmatter 新增标量 `blocker_class ∈ {paperwork, judgment}`。

- 声明：`packages/multi-workers/autopilot/gates.py:197 BLOCKER_CLASSES`、`:190 _SCALAR_EXTENSION_FIELDS = frozenset({"blocker_class"})`。
- **标量 ≠ 列表**：必须新开**平行标量集**，**不得复用** `_JSON_LIST_FIELDS`（对照先例 `_AMBIGUOUS_SCALARS` + `_render_scalar` `gates.py:315`）。
- **冻结 40 名序之外注册**（照 `authorizes` 先例，7 登记点 + 3 测试锁 + 1 materialize 点，Py 4 / TS 3）；漏注册一处即 fail-closed ⇒ 专项测试（T-A…T-E 五形态）。
- **缺省语义（fail-safe）**：parser 保留 `None`，**只有判定层折成 `judgment`**——解析层折不把"未知"伪装成"已知默认"，且 fail-safe 方向是"不得自动放行"。
  - Python 判定层：`conductor.py:7028 blocker_class_of`（非 `"paperwork"` 一律 `judgment`）+ `auto_decision_for_rule` 前缀 `blocker-class-not-paperwork`。
  - TS 判定层：`status-model.ts:769 blockerClassOf`。
- **写入端最小面**：`conductor.py:6030 mark_stalled` 的 `machine_fields` + `conductor.py:3615 _stamp_gate_defaults` 闭集守卫（越集值丢弃并落 `config` 事件）。`gates.create()`、`gate-writer.ts`、`contract_guard.py` **零改动**。
- **`paperwork` 判据**：`.mw-achieved-baddraft.json` 的 `NO MATCH: achieved.md missing pattern '…'`，走幂等 `splice_achieved` 钩子且不消耗判定预算。

**monitor 面**：`J`/`P` 一列标记（`monitor.ts:1057 GATE_BLOCKER_MARK`），在 fit ladder 中**最后丢**（rank 5），保证"自动放行还是等人"这个判断在压榨时仍可见。

---

## 8. 合成 claim：`autopilot@<host>:<pid>` 创建 / 续期 / 失效回收 + 人工让位

**动机（AC-014 / D-013 路线①）**：autopilot 常态就是**没有任何窗口 `switch_key` 接管 key**；旧行为在无 live claim 时 conductor 主动跳过（C-35："claim-free repair skipped, nothing written … 原因=index 状态 idle"）。⇒ conductor 以**合成 claim-id** 接管"有工作但无 live claim"的 key。

**生命周期**：

- 创建/续期/回收：`conductor.py:391 maintain_synthetic_claims`；心跳周期常量 `conductor.py:225 SYNTHETIC_CLAIM_HEARTBEAT_SEC = 60.0`（每心跳 `index_parallel.set_claim` 续期）。
- 绑定 serve 身份：`synthetic_claim_owner` 绑 `serve.meta` pid；`conductor.py:280 _synthetic_claim_stale` 只在"本机 + 身份不一致 / pid 已死 / serve 被替换 / `serve.meta` pid 消失"时判 stale ⇒ 回收。serve pid 变后旧合成 claim 失效（测试 `test_serve_pid_change_invalidates_the_previous_claim`）；孤儿 conductor（serve 比自己新）永不 claim。
- 外机合成 claim：`conductor.py:263 _foreign_synthetic_claim`；外机合成 claim **永不 stale**、不回收、不覆盖、不越权 dispatch，只留一条可去重的 `skip` 痕（R-5 对齐）——"宁可卡住不可双持"。
- `_index.parallel` 呈现：`packages/multi-workers/autopilot/index_parallel.py:126 set_claim` / `:149 clear_claim`（新的 Python 写者，只写 `Claim`/`Status`/`Updated` 单元格、不造行、逐行保字节，与 TS `IndexStore` 同用 `.mw/index.lock`）。
- 解析/判定：`packages/coding-agent/.../shared/index-store.ts:132 parseSyntheticClaim`、`:157 syntheticClaimLive`、`:180 conductorClaimState`；`pm/ui-bridge.ts:251 ClaimState = "free" | "held-live" | "held-stale" | "held-conductor"`、`:267 claimState`（仅 `synthetic.host === os.hostname()` 判 `held-conductor`，外机合成落 `held-live`，不放宽）。
- **人工让位**：活人 claim 优先，conductor 让位并留痕一次（`_human_claim_blocks_synthetic`；`test_human_takeover_yields_and_is_not_reclaimed`）。
- **窗口重启复认领**：`pm/pm-orchestrator.ts:277 restoreWatch` 会重新认领被 conductor 接管的 key，但**非静默**——`pm-orchestrator.ts:319 tookOverFromConductor` 落既有 `agent-team-loop:watch` session entry + `displaySummary` 转写通知 + `_index.parallel` Claim 单元 + `syncPmStateClaimId` 镜像；幂等（第二次重启安静复认领，留痕恰一条）。
- **单一写入方**：合成 claim 走既有 host:pid 存活检查 + 单锁；未引入无锁第二写者。

---

## 9. 回收契约：角色分流 + infra 白名单 + `## Ledger Unresolvable`

**问题（C-36，本 key 内修，AC-013）**：账本（change ledger）对 writeless 角色**量错对象**——四份 research worker 的 `trace.log` 里 `evidence/research` 出现 0 次而交付物都在；同时把报告里**被读取**的路径名当写入意向、把**未展开变量**当路径记录。

- 角色分流（C-36a）：writeless 角色（`research`/`review`/`verifier`/`reviewer`/`rag-research`）只把"声明的唯一交付物 + 显式 `改动清单`"当写入意向，其余按**读取引用**。
- taskDir 外交付物（C-36b）：`<key>/evidence/**` 内的新鲜交付物（存在 + `mtime >= run.started_at`）通过磁盘通道进入 `recorded`。
- 路径卫生（C-36c）：未展开变量（`$dir`/`${VAR}`/`%TEMP%`）与不可解析路径统一 `malformed`（warn、不计入判定）。
- 真实越界写入**仍红**：coding 角色与 writeless 的显式写入声明都保持 `declared ⊆ recorded`（P-03）。
- 分类落点：`packages/coding-agent/.../shared/change-ledger.ts:323 isInfrastructurePath`（**R-1 后收窄为文件级 basename 判定**，删除了 `_autopilot`/`.mw` 整树豁免）、`:426 deliverableDir`、`:812 unresolvable`、`:864`（`infra.push`）。

**infra 白名单（R-1 收窄后）**：只按 **basename** 判定的文件名级清单 `INFRA_BASENAMES`（`change-ledger.ts:296`，13 项）——worker 自身运行产物（`_workers.parallel`、`_index.parallel`/`_index.md`、`task.md`/`run.json`/`trace.log`/`output.md`/`report*.md`/`progress.md`/`worker.log`/`phase-*.md`/`stage-*`、`serve.meta`、`pm-state.md`）。

**明确判红（不再是 infra）的控制面**：`.agenticdoc/_autopilot/gates/**`（应答通道）、`_roadmap.md`（阶段真值）、`auto-decisions.jsonl`（决策台账，伪造 shadow 历史可解锁 live）、`timeline.jsonl`（审计真值）、`config.json`（kill switch）、`xkey/ledger.json` + `xkey/tickets/**`（授权状态）、`.mw/**`（锁/pid）。红线 = "写它改变框架自身对世界的判断"。

**`## Ledger Unresolvable`（T-17c）**：声明了但**磁盘上不存在**的路径不再计入 `extra`（falsifying 红），改为可见 warn 通道。

- 判定：`change-ledger.ts:812 unresolvable`；分类三路 `infra → unresolvable → judgeable(=extra)`，**infra 先判、存在性后判**（infra 是所有权，与文件当下是否存在无关）。
- 产品段：`packages/coding-agent/.../worker/output-writer.ts:78 unresolvableFiles`、`:356 sections.push('## Ledger Unresolvable')` + trace 行 `[FLOW] ledger-unresolvable count=N samples=…`。**不**并入 `## Questions`（不留失败回读信号），也**不**是静默通道。

**共同可见产物段**：`## Ledger Infra`、`## Ledger Malformed`（C-36c，`malformedFiles`）、`## Ledger Unresolvable`。三者的语义边界：infra=所有权、malformed=形态非法、unresolvable=形态合法但盘上无此物。

---

## 10. 已知限制与残留（收口时点）

- **`stage-close` 自动放行默认关闭**：`auto_gate_mode=off` + shadow 门槛 ⇒ 生产自动批准占比 0%（本机 `phase:"decide"` = 0 行）。这是安全阀而非缺陷；需先跑影子池（≥5 夜 / ≥20 决策 / 每规则 ≥1 反例）。
- **`halted` stage、roadmap-writer 2 次提案上限、`pending-review` 出口需 `auto_gate_mode≠off`**：三处仍是设计内"停等人工"，无自动出口。
- **G-1 未实现**：AC-005 判据内"重启后复核 pending 门禁未被新自动裁决意外改写"（`answered_by=conductor-auto:` ∧ `answered_at > 新 started_at_ms`）的机器检查在全仓无实现无测试（T-18 G-1）。
- **R-1 工具层拦截面**：本 key 只把 `_autopilot/**`/`.mw/**` 越界写从"infra 豁免"收窄为"ledger 报红"；工具层守卫（`shared/xkey-gate-guard.ts`）的 `python -c write_text` 等 marker 缺失、`.mw/**` 无守卫，仍属后续卡。
- **R-5 多机**：两机共享文件系统时 Python 与外机合成 claim 的语义已按"宁可卡住不可双持"对齐；真多机长跑未验证。
- **六值中 `gate-queue-unreadable` 的三面覆盖**：R-2/R-3/R-4 已由 T-21/T-22 修复（monitor partial+0、TS `listGates` 吞错、Python `queue_entries`），详见 `evidence/quality-gate-report-20261013.md`。

## 相关文件

- 目标锚点：`.agenticdoc/goal.md`
- 需求/设计/计划：`.agenticdoc/mw-autopilot-gate-alarm-liveness/{spec.md,design.md,plan.md}`
- 收口证据：`.agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/quality-gate-report-20261013.md`、`evidence/runs/closeout-runtime-actions-20261013.md`
- 对抗式质量门：`.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t18-adversarial-qg/report.md`（R-1…R-8 缺陷/反证）
- 更新锚点自检：[UPDATE.md](../UPDATE.md)
