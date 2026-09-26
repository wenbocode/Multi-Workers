# Research: 仓内可复用先例盘点（RQ-3）

- Key: xkey-repair-mechanism / Phase: SPEC（research RQ-3）
- 日期: 2026-09-26
- 产出: 本文件为唯一写入；未改任何 key 文件、未跑写状态命令、未 commit
- 行号口径: 当前工作区 HEAD（dirty 树）实测行号，方法 `Select-String -Pattern '...' | % { "$($_.LineNumber): ..." }`

## 决策问题

1. 本仓已有机制中，哪些**可直接复用**来实现 xkey 治理通道（账本 → 工单 → 追认 gate → 受限修复 → 证据包 → 闭合写回），哪些**需改造**，哪些**不适用**？
2. 四个被 spec §2.4/§5 点名的复用面的**精确落点与落盘形状**：闭环/证据包（mw-done-closure-repair）、gate 状态机（stalled-gate 家族）、失败定位穿线（mw-l3-fail-marker-forms）、任务级作用域/可见性（mw-task-scope-isolation / mw-worker-visibility-gate）。
3. `mw-crosskey-risk-escalation` 是否就是本次"跨 key 红修复"的**前半（升级半环）**？

## 调研方法与出处

- **逐 key 读文档 + 对照其实际产出的代码**（以 code 为准，文档为线索）：`.agenticdoc/<key>/{spec,design,achieved}.md` + `packages/multi-workers/**` + `packages/coding-agent/src/extensions/agent-team-loop/**`。
- 只读检索工具：`Select-String`（PowerShell）/ grep，全包扫描 `.py` 与 `.ts`（`dist/**` 为构建产物，只读 src；`dist/extensions/agent-team-loop.js` 仅用于确认镜像存在）。
- **关键否证检索**（均实测，命中数见 §7）：
  - `cross_key|crosskey|handoff` in `packages/multi-workers/*.py,autopilot/*.py` → **0**
  - `ledger|账本` 同范围 → **0**
  - `ttl|expiry|expire|deadline` in `gates.py,config.py,conductor.py` → **4**（全部为 conductor 主循环 sleep 与 advance 子进程 TimeoutExpired，见 §3）
- 上游语料：`.agenticdoc/xkey-repair-mechanism/spec.md`（§1.1/§2.4/§5）、`key-decision.md`（Q1..Q9）、`evidence/research/spec-problem-framing-20260926.md`（R-1/RQ-3 待深化项）。

## 发现

### 0. 全局比例（先给结论）

| 治理通道能力域 | spec/design 点名的最近先例 | 判定 |
|---|---|---|
| 追认 gate 抬起 / 作答 / 消费 / 预算 | \`gates.py\` + \`conductor.py\` + \`autopilot/gate-writer.ts\` | **直接复用**（kind 扩展；"仅人可答"需新建） |
| 超时 / 重试 / 预算 | \`round_budget\` + \`_resume_credits\` + \`_budget_bonus\` + \`advance_stall_ticks\` + \`mark_stalled\` | **直接复用** |
| 闭环坏稿守卫（内容寻址三条件授权） | \`autopilot/closure.py\` | **直接复用**（条件换对象） |
| 闭合写回事务范式 | \`_done_transaction\` | **需改造**（对象=两 key 登记 + 账本行） |
| 幂等去重 / append-only 落盘 | \`_persist_l3_provenance\` | **需改造**（同家族、换形状） |
| 红来源（fail_line） | \`_l3_provenance_record\` | **需改造**（有 fail_line，无 file/test_id） |
| 受限 worker（工具白名单 / read 面 / 凭证隔离 / 派发） | \`dispatch.py\` + \`worker-mode.ts\` + \`launcher._stripped_env\` | **直接复用** |
| 写面拦截先例 | \`shared/protected-config.ts\`（路径集合） | **需改造**（本机制要行集合） |
| 证据包组装器（AC-006 五项） | 未发现组装器；碎片散在 3 处 | **需新建**（碎片可复用） |
| 仅人可答强制（AC-004） | 未发现 | **需新建** |
| 跨 key 红账本 | 未发现 | **需新建** |
| 工单（AC-003 机器可读边界） | gate frontmatter 可承载一部分 | **需改造**（边界载体不够） |

**比例（估）**：直接复用 ≈ 35–40%；需改造 ≈ 40%；需新建 ≈ 20–25%（账本、仅人可答强制、diff 行集合边界、工单/证据包形状）。即"重用为主、新建集中在治理语义本身"，符合 spec §5"避免重造"的意图。

---

### 1. mw-done-closure-repair（闭环 / reprompt / 闭合写回）

> **口径修正**：本 key **不包含"抬 gate"与"答复消费"**。它的"closure"= done 门禁驳回后的自愈 + achieved.md 闭合写回；抬 gate / 作答 / 消费在 stalled-gate 家族（§3）。spec §5 记忆前馈表把它映射为"证据包生成与闭合写回"是准确的，映射为"抬 gate"不准确。

| 已有件（做什么 / 在哪 / file:line） | 关系 | 改造点一句话 |
|---|---|---|
| **失败原文回流契约** \`_done_transaction(...) -> (verdict, err)\`，err 仅在 gate-blocked 路携带 advance stderr；消费方用 \`_classify_advance_failure\` 重导分类（单一来源）— \`autopilot/conductor.py:1715\`（调用点 \`:1585\`） | 直接复用 | 把"失败源"从 advance stderr 换成 L3 FAIL 行/交接登记，范式不变 |
| **失败行解析 + 触发判据** \`closure.failure_lines(err)\` 按稳定前缀 \`"   - "\` 逐字保留余文；\`has_achieved_failure(lines)\` = 任一行含字面量 — \`autopilot/closure.py:37,65,84\` | 直接复用 | 判据从"含 achieved.md"换成"含交接登记/冻结常量块标识" |
| **reprompt 提示词两分式** \`compose_reprompt_prompt(base, lines)\` = base + 固定指示常量 \`REPROMPT_INSTRUCTION\` + 失败行逐字列表（逐字节可断言；常量零工程词表字面量）— \`autopilot/closure.py:48,91\` | 直接复用 | 作"仅升级 / 仅提案"分支的 prompt 模板，替换指示常量 |
| **自持预算的 reprompt 回路** meets 分支展开四路：gate-blocked∧含 achieved.md → 自持 \`used < l3_limit\` → 派 \`l3-a{N+1}\`；耗尽 → \`mark_stalled\` 且 **verdict 保真 meets**；其他 gated → 走 streak；事件 \`l3-reprompt\` — \`autopilot/conductor.py:1580-1626\`（\`mark_stalled\` :1602） | 直接复用 | 作为"授权 reject/超时后去向"的预算封顶范式（P-009/AC-007/D 场景） |
| **内容寻址坏稿守卫（三条件授权）** marker \`.mw-achieved-baddraft.json\` schema \`{file,sha256,declared_at,failures}\`；\`read/write/delete_bad_draft_marker\`、\`overwrite_authorized(marker,current_bytes,lines)\` = marker 存在 ∧ sha256(当前字节) 匹配 ∧ 记录的失败行含 achieved.md；写入 tmp+\`os.replace\`、锁内、单文件幂等 — \`autopilot/closure.py:105,123,151,159\` | 直接复用（核心可复用件） | 三条件换成"授权边界快照 ∧ 被涉及文件 sha 未漂移 ∧ 改动行集合 ⊆ 声明行集合" |
| **marker 生命周期收口** 覆盖成功同锁删（\`:1783\`）；advance exit=0 惰性清理（\`:1833\`）；终态（DONE / closed-legacy）清扫（\`:2163, :2286\`） | 直接复用 | 同样收口"工单已闭合 / 已拒绝"的 sidecar 生命周期 |
| **闭合写回事务骨架（check-before-write）** \`_done_transaction\`：step1 QG 落盘 \`evidence/quality-gate-report-*\`（\`:1744-1755\`）→ step1b \`_persist_l3_verdict\`（\`:1756\`）→ step2 achieved 覆盖（\`:1770-1790\`）→ step3 ≥200B 后验（\`:1794\`）→ step4 pm-state PASS（\`:1810\`）→ step5 advance done（\`:1811\`）→ step6 index 后验（\`:1845-1860\`） | 需改造 | 每一步都可 resume、每步都有后验，但对象是单一 key 的 done；xkey 需换为"两 key 登记标注 + 账本行 closed + 证据包完备" |
| **机械验收封口** \`_done_credentials_present\` 五项派生件全在才允许 roadmap 置 done（\`l3-verdict.txt=meets / l3-report.md / quality-gate-report-* / achieved.md≥200B / pm-state PASS\`）— \`autopilot/conductor.py:1415\` | 直接复用（判据范式） | 直接对应 AC-006"缺任一项不得置为已闭合" |
| **抬 gate / 作答消费** | **不适用本 key** | 见 §3 |

**与 xkey 证据包的关系**：本 key 无"证据包组装器"（没有把 old→new sha256 / 复跑 stdout / 红数 before→after 打成一包的地方）。可复用碎片 = ① sha256 现场哈希（\`closure.py:135\` 字节精确 / \`mw_common.sha256_eol_normalized:2926\` EOL 归一）；② 落盘 tmp+\`os.replace\`+LF（\`closure.py:123-149\`、\`gates._write_atomic:198\`）；③ "\`_done_credentials_present\` 式缺项即拒"。**组装器本身需新建。**

---

### 2. mw-crosskey-risk-escalation —— 同一词汇、不同问题

**它当时把"跨 key 风险"做成了什么？**——**派发路由的窗口归属**："本窗口派发到别键（含 \`_scratch\`）的 worker，其高风险检查点会唤醒 PM 一次，alert 带 owner key；别窗口的 worker 仍静默。"（\`achieved.md:5\`）

原文引用：
- design D-101（\`.agenticdoc/mw-crosskey-risk-escalation/design.md:31-46\`）："归属判定改为'或'关系（watched key ∪ 本窗口派发）"——改的是
  \`if (!watch.key || ownerKeyOf(entry) !== watch.key) continue;\` → \`const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false; if (!watch.key || (ownerKey !== watch.key && !owned)) continue;\`
- design D-102（同文件 :47-59）：异地 alert 在 worker 名后附加 \`（owner key=<ownerKey>）\`；watched key 自身文案逐字不变。
- design D-103/D-104（:61-77）：\`escalated\` 每 task 每窗口至多 1 条、\`risk === "low"\` 抑制不变；否决"全局广播"。
- achieved 残留（\`achieved.md\` R-1/R-2）：\`dispatchedTaskKeys\` 进程内、不持久化，窗口重启后异地 worker 不再升级。

**代码落点**（TS 扩展，非 Python）：
- \`packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts:564-578\`（\`owned\` 判定 + 过滤分句；\`:573\`）
- \`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:154\`（\`PmWatchState.dispatchedTaskKeys?: Set<string>\`）
- 测试：\`packages/coding-agent/test/extensions/agent-team-loop.test.ts:4007,4060,4108\`；\`agent-team-loop-watch-aggregate.test.ts:80-160\`

**与本次的关系（结论）**：

| 已有件 | 关系 | 改造点 |
|---|---|---|
| 归属 = watched key ∪ 本窗口派发（进程内 Set） | 不适用 | 它管"窗口是否拥有某 worker 的可见/升级权"，不管"某处红由哪个 key 的写面负责" |
| 投递纪律：once-per-task 去重 + low-risk 抑制 | 直接复用（仅设计原则） | 可作为 AC-001 幂等去重 / "无登记红只升级不提案"的语义参照；代码不可复用（TS/UI 层） |
| 分级升级判据 | 需改造 | 它只有 worker-mode \`computeRisk\` 的 low/mid/high（执行风险），没有"红的分级（可修/真回归/不可解析）"；本机制判据需新建 |
| 落盘形状 | 未发现 | 全进程内状态，无 ledger / ticket / gate / 事件；本机制"升级半环"的落盘形状需新建（可参照 \`_persist_l3_provenance\`） |

**判定：不是同一问题的前半环，是不同问题。** 它解决"跨 key 派发的 worker 的 PM 通知归属"（治理对象=通知），本次解决"跨 key 冻结面失效的修复权归属"（治理对象=写面与红）。二者唯一共享的是"升级要有 owner、要幂等、低风险不打扰"的设计原则与"owner key 要写进文本"的可读性要求。spec §2.4 把它列为"与'升级'半环的边界与复用"——**结论：复用面 ≈ 0 代码，只继承原则**；spec/design 不应期待从它取到账本、工单、gate 或分级判据。

---

### 3. stalled-gate 家族（gate 状态机：抬起 / 作答 / 超时 / 重试 / 预算）

#### 3.1 落盘协议与 payload 形状

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| gate 落盘：一 gate 一 markdown，\`<project>/.agenticdoc/_autopilot/gates/gate-{seq:04d}.md\`；frontmatter=机器契约，body=人读 | \`autopilot/gates.py:116\`（\`Gate\` dataclass）、\`:480\`（\`enumerate\`）、\`:506\`（\`pending_gates\`） | 直接复用 | — |
| **payload 形状：12 字段 frontmatter** \`id,kind,stage,key,created_at,created_by,question,context_refs,status,answered_at,answered_by,note\` | \`gates.py:65\`（\`FRONTMATTER_FIELDS\`）、\`:83\`（必填集）、\`:259\`（\`create\`） | 直接复用（协议） | — |
| kind 闭集 \`{stage-confirm, stage-close, stalled, budget-exhausted, goal-change}\`；status 闭集 \`{pending, approved, rejected}\` | \`gates.py:52,60\`；TS 镜像 \`autopilot/status-model.ts:467,468\` | 需改造 | 新增 \`xkey-authorize\` 必须**两侧同步**并在 TS \`parseGateFile:529/595\` 放行，否则面板枚举抛 \`GateFormatError\` |
| **承载约束**：\`question\` 必须单行（拒 \`\\n\`/\`\\r\`），\`context_refs\` 是单行字符串列表（块列表或 \`[]\`），无嵌套/无多行标量 | \`gates.py:209-238\`（\`_validate_new_gate\`）、\`:308-364\`（\`_parse_frontmatter\`） | 需改造 | AC-003 工单的 \`request_id/affected_keys/拟授权边界/追认入口\` 是复合 payload，**不能塞 gate**：独立工单文件 + gate 用 \`context_refs\` 指路（先例形状见 spec RQ 的 \`cross-key-repair-request-20260925-n1.md\`） |
| 原子写 | \`gates.py:198\`（\`_write_atomic\`，tmp + replace + UTF-8/LF） | 直接复用 | — |
| seq 分配 = 目录重扫 \`max(id)+1\`（无内存计数器，重启安全） | \`gates.py:243\`（\`_next_seq\`） | 直接复用 | — |
| 解析容错：corrupt gate 抛 \`GateFormatError\`，调用方 skip + timeline config 事件 | \`gates.py:104,460\`；\`conductor.py:283-288\` | 直接复用 | — |

#### 3.2 抬起 / 作答 / 消费 / 预算

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| **抬起（conductor 是唯一创建者；gates 锁内；锁忙返回 None 下 tick 重试）** | \`conductor.py:2064\`（\`_create_gate\`）；调用点：\`:370/:436\`（stage-confirm）、\`:594\`（stage-close）、\`:939-944\`（budget-exhausted）、\`:2321\`（stalled） | 直接复用 | 抬起 \`xkey-authorize\` 直接调 \`_create_gate(kind="xkey-authorize", key=source_key, refs=[ticket_path])\` |
| **四件套停滞** key-status=stalled + stalled gate + achieved 遗留草稿 + \`patterns/<key>/stall-lesson.md\`，幂等 | \`conductor.py:2294\`（\`mark_stalled\`） | 直接复用 | 无登记红"只升级"可直接复用四件套或新写升级记录 |
| **作答（TS）** \`.mw/gates.lock\`（O_CREAT\|O_EXCL）下重写 \`status/answered_at/answered_by/note\` 四字段，原子替换 | \`autopilot/gate-writer.ts:139\`（\`answerGate\`）；\`:33\`（\`answered_by\`=作答窗口 claimId）；锁路径 \`status-model.ts:61\` | 直接复用（写面） | **AC-004"仅人可答"无任何判据**：\`answered_by\` 只是 claimId，"人"与"PM/agent"在协议上不可区分 → 需新建判别（见 §7 未发现） |
| **消费（durable / 幂等 / 零私有状态）** timeline \`gate-answered\` 事件为持久消费记录，重启重派生 | \`conductor.py:255\`（\`_consumed_gate_ids\`）、\`:274\`（\`_consume_answered_gates\`） | 直接复用（AC-007 幂等先例） | 工单闭合"重复闭合幂等"可复用同一模式：以事件为消费记录而非计数器 |
| **approve 恢复** key-status stalled→running + \`gate-answered\` + \`resume\` 事件 + 就地改本 tick \`status_of\` | \`conductor.py:2190\`（\`_apply_stalled_approvals\`） | 直接复用（范式） | xkey approve 的推进应在 conductor 单点（Q9） |
| **reject 去向** key-status→closed-legacy + 事件 | \`conductor.py:2258\`（\`_apply_stalled_rejections\`） | 直接复用（范式） | AC "reject 后去向"按 Q7 推荐：留账本 \`rejected\`，不静默丢 |
| **恢复额度（一次 approve = 各回路各放宽一轮，不可复用）** \`_resume_credits\` = approved stalled gate 计数，四个预算点统加 | \`conductor.py:2168\`；消费点 L3 \`:1516\`、repair \`:1652\`、L2 \`:909-912\` | 直接复用（范式） | 作为"追认一次只给一次修复机会"的语义参照 |
| **budget-exhausted bonus / rejected** 一题恰好加一轮；rejected → stall | \`conductor.py:2111\`（\`_budget_bonus\`）、\`:2123\`（\`_budget_gate_rejected\`） | 直接复用 | — |
| **重试上界（连续失败升级）** \`_classify_advance_failure\`（4 类有序探针）+ timeline 尾部派生 streak（零私有状态、失败开放）+ 达 \`advance_stall_ticks\` → \`mark_stalled\` | \`conductor.py:720\`、\`:747\`、\`:812\` | 直接复用 | 可作为"修复未收敛"的兜底升级；\`advance_stall_ticks\` 默认 5、范围 1..50 |
| **超时 / TTL** | **未发现**：gate 12 字段无 expiry/ttl/attempt；\`gates.py,config.py,conductor.py\` 中 \`ttl\|expiry\|expire\|deadline\` 命中 4 处全部是 conductor 主循环 \`time.sleep\` 与 advance \`subprocess.TimeoutExpired\`（\`conductor.py:1711,2503-2505\`） | **不适用** | 门禁"超时"在协议层**不存在**：时间维度由回路预算 + streak + 面板 STALE 显示承担（$\ne$ gate 内部 TTL）。R-3 的"超时/提醒语义"若理解为 gate TTL 需新建，若理解为回路预算则复用 |
| **配置开关（默认关、per-project、落盘）** \`DEFAULT_CONFIG\`（\`enabled:false, paused:false, poll_interval_sec, max_parallel_keys, round_budget, worker_timeout_min, l2_read_file_cap, l2_read_byte_cap, advance_stall_ticks\`）；\`_BOOL_FIELDS\` 先于 int 校验；未知键 fail-closed | \`autopilot/config.py:38,51,52,75\`；TS 镜像 \`status-model.ts:82,112,149,199\` | 直接复用落点 | AC-008 开关加 \`xkey_repair:false\`（bool）+ TS 双侧同步（P-015；先例 mw-autopilot-stall-feedback） |
| 面板只读消费 | \`autopilot/status-model.ts:638\`（\`listGates\`）、\`:1011\`（\`deriveStatusModel\`）、\`monitor.ts\`（STALE 判据） | 直接复用 | 工单/账本可加只读面板行 |

**判定**：gate 协议（落盘/解析/抬起/作答/消费/预算）**整体可直接复用**；需要三处新建/改造：① 新 kind 的**两侧镜像同步**；② **仅人可答**判别（无先例）；③ 复合工单 payload 需**独立文件**（gate 字段承载不下）。时间维度不要指望 gate TTL（不存在），沿用回路预算 + streak。

---

### 4. mw-l3-fail-marker-forms（fail_line 穿线 / provenance 记录）

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| **FAIL 行检测（三形态 + token 局部零值豁免）** pipe/bullet/prose 三正则 + \`_L3_FAIL_ZERO_RE\`；全文件扫描（不限 QG 节） | \`conductor.py:1164\`（\`_l3_fail_marker_line\`）、常量区 \`:1150-1158\` | 直接复用 | 可作本机制的"红行定位器"；扫的是 L3 判定源文本，不是测试输出 |
| **resolver 三元组** \`_l3_resolve_source(sources) -> (verdict, source_path, fail_line)\`；fail-closed：任一可读源带 FAIL → below + 该源 + 首命中行 | \`conductor.py:1215\` | 直接复用 | — |
| **round_verdict 四元组** \`_l3_round_verdict(...) -> (verdict, worker_status, deciding_source, fail_line)\`；worker 终态失败先判 \`no-verdict\` | \`conductor.py:1233\` | 直接复用 | — |
| **provenance 落盘字段形状** \`l3-verdict-provenance.json\` 记录 \`{round, task_key, deciding_source, source_mtime_ns, anchor_path, anchor_mtime_ns, suspect, reasons[], raw_verdict, verdict, fail_line, recorded_at}\` | \`conductor.py:1267\`（\`_l3_provenance_record\`；字段字面量 \`:1293-1305\`） | 需改造 | 可作为"红来源"**直接输入**：可拿 \`fail_line\`（行原文）+ \`deciding_source\` + \`round/task_key\`；但要 \`(file, test_id)\` 必须改造 |
| **append-only + 去重 + 原子写的不覆盖历史** 按 \`task_key\` 去重，\`tmp\`+\`os.replace\`，corrupt sidecar 不覆盖 | \`conductor.py:1359\`（\`_persist_l3_provenance\`） | 直接复用（账本原语范式） | 跨 key 红账本可同族：append-only JSON + 去重键 + 原子写 + 不覆盖历史；**去重键要换成 Q8 的 \`(file, test_id, 冻结块指纹)\`** |
| **消费面** fail_line 进 stall reason / timeline \`config\` detail（\`l3-verdict ... fail: ...\`）/ repair prompt | \`conductor.py:1597-1602\`（stall reason）、\`:619,646-651\`（\`_persist_l3_verdict\` reason）、\`:1130\`（\`_repair_prompt\`） | 直接复用（范式） | — |

**能否取到 \`(file, test_id, fail_line)\`？**

| 目标字段 | 可得性 | 证据 |
|---|---|---|
| \`fail_line\` | ✅ 逐字行（整行，表格行/项目符/散文三形态之一；来自 output.md 或 report.md **全文**） | \`conductor.py:1164,1304\` |
| \`deciding_source\` | ✅ \`workers/ap-<key>-l3-aN/{output.md\|report.md}\` 相对路径 —— 是**判定源**文件，不是失败测试文件 | \`conductor.py:1296\` |
| \`round\` / \`task_key\` | ✅ 轮次与派发键（可回溯 key） | \`conductor.py:1294-1295\` |
| \`file\`（被测文件） | ❌ 未结构化：无拆分器；路径只能从 \`fail_line\` 文本里启发式抽 | 全包 \`.py\` 无 test-id/file 拆分器 |
| \`test_id\` | ❌ 同上 | 同上 |
| 交接登记 \`cross_key_test=... / owner=... / handoff=registered\` | ❌ **非机器字段**：全包 \`.py\` 检索 \`cross_key\|crosskey\|handoff\` 命中 **0**；只在 FM 的 L3 散文中（spec RQ-2 语料） | 检索实测（§7） |
| \`[VERIFY] VC-NNN: k=v\` 行 | ❌ 无消费侧解析器：\`[VERIFY]\` 在 \`packages/multi-workers\` 只出现在 prompt 文案与测试打印，无机器读取 | \`conductor.py:1001,1116,1140\`（prompt）；测试文件多处 print |

**判定**：provenance sidecar 是本机制"红来源"的**唯一现成机读入口**，但只到"fail_line + 判定源"，**不覆盖 \`(file, test_id)\`，也不覆盖交接登记**。→ **代码层面证实 spec §4 R-1 成立**：交接登记是散文，必须先做"机器可读化 + 兼容散文解析"（写侧 + 读侧双侧测试，P-005）。AC-001 的 \`(file, test)\` 去重键需本机制自建最小解析器（从 \`fail_line\` 抽 \`path::test\` 或 \`tests/...py\` token），解析失败按 Q5 降级为"仅提案 / 仅升级"。

---

### 5. mw-task-scope-isolation / mw-worker-visibility-gate（任务级作用域 / 可见性）

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| **任务级作用域（窗口口径）** \`PmWatchState.dispatchedTaskKeys?: Set<string>\`（进程内、不持久化） | \`pm/ui-bridge.ts:154\` | 不适用 | 管"哪个窗口的责任"，不管写面 |
| 归属谓词 \`ownedByThisWindow(entry, watch, root) = ownerKeyOf===watch.key \|\| dispatched.has(taskKey)\`（纯函数、fail-closed） | \`pm/ui-bridge.ts:297\` | 不适用（可借形状） | 越权拒绝的"注入式归属谓词 + fail-closed 默认收窄"可作工单越权判定的形状参照 |
| ack 收窄：\`ackTasks(..., ownedBy?)\`，越界 → rejected 且**不写盘** | \`pm/ui-bridge.ts:446\`，谓词 \`:454\`，调用点 \`:1300, :2259\` | 需改造（范式） | "越权即拒 + 不落盘 + 给出替代指引"正是 AC-005 fail-closed 的文案/行为模板 |
| \`list_tasks\` 三档 scope（\`mine\`/\`key\`/\`all\`），未知 scope/缺参数 → 文本错误不静默降级 | \`pm/ui-bridge.ts:1316\`，过滤 \`:1344,1347,1360\` | 不适用 | — |
| 派发记账写入点 | \`pm/ui-bridge.ts:1263-1266\` | 不适用 | — |
| **派发文档门禁（相位分层）** \`phaseDocGaps\`：SPEC 只查 spec 侧四项，DESIGN 起加 design 侧 | \`shared/phase-docs.ts\`（\`DESIGN_TIER_PHASES:100\`）；见 \`.agenticdoc/mw-worker-visibility-gate/achieved.md\` §1 | 不适用 | "缺项门禁 + 既有文案逐字不变 + 双向字节回归"验收范式可继承 |
| **跨 key 聚合提示行** \`renderWatchLines(..., extraTaskKeys?)\` 末尾追加恰好一行 \`~ N elsewhere: ...\` | \`pm/ui-bridge.ts:504\`；\`pm-orchestrator.ts:325,550,680\` | 不适用 | — |
| **claim 身份两处同值** \`syncPmStateClaimId\`（索引行权威；插行/替换 + 原子写） | \`shared/pm-state-claim.ts\`；P-011 | 不适用 | 与 P-011"账本判活不得依赖 pm-state 派生身份"一起约束账本身份 |

**与"受限写面"真正相关的邻近件（本任务未点名，必须点名以免 design 重造）**：

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| **工具层写面拦截（最强写面先例）** \`protected-config.ts\`：write/edit 的 path 解析命中保护集 → block；bash 命令文本解析（动词/重定向/内联 python 写）→ block，fail-closed；Python 侧同规则 | \`shared/protected-config.ts:264-268\`（bash 判定）、\`registerProtectedConfigGuard\`（同文件尾部）；Python \`mw_common.is_protected_agent_config\`；\`.agenticdoc/mw-protected-config-guard/mini-spec.md\` | **需改造**（关键参照） | 其边界是**路径集合**；AC-005 要**行集合 ⊆ 冻结常量块行集合**，diff 层强制需新建（可在 \`protected-config\` 的判定/记录形状上扩展，或新增独立校验器） |
| **实现门禁（写代码前需 active key claim 或新鲜 mini-spec）** \`gateDecision\` / \`checkBashWriteTarget\` / \`hasActiveKeyClaim\` / \`findFreshMiniSpec\`；worker 模式下 \`PI_WORKER_TASK\` 走 worker 分支 | \`shared/implementation-gate.ts:686,612,218,240\` | 不适用 | 是"有没有 key"门，不是"允许改哪几行" |
| **per-task 读面 + 工具白名单（GC-2 现成件）** \`read_scope\`/\`deny_globs\` 渲染；worker 侧拦截 + caps；工具白名单表 | \`autopilot/dispatch.py:243\`（\`render_task_md\`）、\`:399\`（dispatch 强制 verifier read_scope）；\`worker/read-scope.ts:47,259\`；\`worker/worker-mode.ts:52\`（\`TOOL_ALLOWLISTS\`）、\`:92\`（\`toolsForType\`）、\`:101\`（\`activeToolsForType\`） | **直接复用** | 受限修复 worker 的 read 面 + 工具面现成；新增 dispatch type 时必须同步 Python REGISTRY 与 TS 表（parity 锁见 §6 邻件） |
| **派发 REGISTRY（type → tools/route/requires_read_scope/conductor_dispatchable）** | \`autopilot/dispatch.py:66\`（\`REGISTRY\`）、\`:139\`（\`tool_set\`）；parity 测试 \`test_autopilot_dispatch.py\`（REGISTRY ↔ TS \`TOOL_ALLOWLISTS\` 逐项相等） | 直接复用 | 受限修复可加 \`xkey-fixer\` 类型（tools+read_scope）；两侧同步否则 parity 测试红 |
| **凭证隔离 / stripped env / 树杀** | \`launcher.py:90\`（\`_stripped_env\`）、\`:223\`（\`_build_env\`）、\`:462\`（\`_build_command\`）；\`mw_common\`/worker-mode 看门狗 | 直接复用 | GC-3 现成 |

**判定**：mw-task-scope-isolation 与 mw-worker-visibility-gate 都**不是写面机制**（前者=窗口可见/可操作面，后者=文档门禁/面板/claim），对 AC-005 **不适用**；可继承的是"注入式归属谓词 + 越权 fail-closed + 不写盘"的行为模板。"受限写面"的可复用件在邻近的 \`protected-config.ts\`（路径集合拦截）与 \`dispatch.py\`/\`worker-mode.ts\`（读面 + 工具白名单），**"行集合边界"无先例，需新建**。

---

### 6. \`autopilot/closure.py\` 与 \`autopilot/config.py\` 现有结构

#### closure.py（7.7 KB，无 conductor 依赖，单向依赖 \`conductor → closure\`）

- 模块职责：done-gate 闭环原语（纯逻辑 + 最小文件 IO）；contract surface 见 docstring \`:20-36\`；**零工程词表字面量**（VC-003 扫描 \`autopilot/*.py\`，docstring \`:28-30\`）。
- 常量：\`FAILURE_LINE_PREFIX\` \`:37\`、\`ACHIEVED_FILE_NAME\` \`:39\`、\`BAD_DRAFT_MARKER_NAME\` \`:40\`、\`BAD_DRAFT_TMP_NAME\` \`:41\`、\`REPROMPT_INSTRUCTION\` \`:48\`。
- 主要 def：\`failure_lines\` \`:65\`、\`has_achieved_failure\` \`:84\`、\`compose_reprompt_prompt\` \`:91\`、\`_marker_path\` \`:101\`、\`read_bad_draft_marker\` \`:105\`、\`write_bad_draft_marker\` \`:123\`、\`delete_bad_draft_marker\` \`:151\`、\`overwrite_authorized\` \`:159\`。
- 可扩展点：① 把 \`overwrite_authorized\` 泛化为 \`authorized_change(marker, current_bytes, predicate)\` 以承载"行集合子集"条件；② 同目录再加 \`xkey-*.json\` sidecar（沿用 \`_marker_path\`/\`read\`/\`write\`/\`delete\` 四件套）；③ \`compose_reprompt_prompt\` 复用于"升级/仅提案"提示词。禁区：新常量不得写死测试名/断言词（VC-003）。

#### config.py（5.9 KB，\`_autopilot/config.json\` 读/校验/写）

- 模块职责：fail-closed 校验（present-but-invalid 抛 \`ConfigError\`，缺失=默认且零 footprint）；mtime+size 缓存供每 tick 零重解析（docstring \`:1-27\`）。
- 主要符号：\`ConfigError\` \`:34\`、\`DEFAULT_CONFIG\` \`:38\`、\`_BOOL_FIELDS\` \`:51\`、\`_INT_RANGES\` \`:52\`、\`_CACHE\` \`:63\`、\`config_path\` \`:66\`、\`default_config\` \`:70\`、\`validate_config\` \`:75\`、\`load_config\` \`:101\`、\`save_config\` \`:115\`、\`cached_load\` \`:129\`、\`invalidate_cache\` \`:152\`。
- 可扩展点：AC-008 开关 = \`DEFAULT_CONFIG\` 加 \`xkey_repair: false\` + \`_BOOL_FIELDS\` 加该键（bool 必须先于 int 校验，见 \`:51\` 注释）+ \`validate_config\` 的未知键 fail-closed 自动覆盖；**必须同步 TS 镜像** \`status-model.ts:82,112,149,199\`（P-015；先例 mw-autopilot-stall-feedback 的 \`advance_stall_ticks\` 双侧同步）。

#### 跨机制原语（账本/锁/哈希，spec design 会用）

| 已有件 | 位置 | 关系 | 改造点 |
|---|---|---|---|
| 文件锁 \`acquire_lock\` / \`release_lock\`（O_CREAT\|O_EXCL，同 TS 协议） | \`mw_common.py:1480,1495\` | 直接复用 | 账本读改写用（Q9） |
| conductor 锁封装 \`lock_file\` / \`acquire_conductor_lock\` / 命名锁 \`gates/roadmap/workers/key-<key>\` | \`conductor.py:92,97\` | 直接复用 | — |
| 队列读写 \`workers_path\` / \`parse_workers_file\` / \`serialize_entry\` | \`mw_common.py:1430,1442,1467\` | 直接复用 | — |
| 哈希：EOL 归一 \`sha256_eol_normalized\` / 字节精确 \`hashlib.sha256\` | \`mw_common.py:2926\` / \`closure.py:135\` | 直接复用 | AC-006 的 old→new sha256 需**先声明用哪种**（建议字节精确为主、EOL 归一另记，避免"仅换行"误判） |
| 证据审计（AC→VC 引用闭包，非证据包） | \`autopilot/audit_evidence.py\`（\`build_dossier:215\`、\`main:266\`） | 不适用 | 它查"证据引用是否闭合"，不产出 old→new sha256/复跑 stdout/红数 |
| 工具链 run meta（watched before/after sha256 + drift + \`cmd.txt\`/\`run.log\`/\`exit.txt\`/\`errors.txt\` 落盘） | \`mw.py:995-1040\`（\`_toolchain_run\`） | **需改造**（最接近的"证据包"形状） | 形状可借：命令 + 原始 stdout + exit + before/after sha256 + drift；但它是 UE toolchain 专用，非通用证据包 |

---

### 7. 未发现（附搜索模式与命中数）

| 未发现项 | 搜索模式 | 范围 | 命中 |
|---|---|---|---|
| 跨 key 红账本 | \`ledger\|账本\` | \`packages/multi-workers/*.py, autopilot/*.py\` | 0 |
| 交接登记机器字段/解析器 | \`cross_key\|crosskey\|handoff\` | 同上 | 0 |
| gate 内 TTL / expiry | \`ttl\|expiry\|expire\|deadline\` | \`gates.py, config.py, conductor.py\` | 4（全为主循环 sleep / advance TimeoutExpired） |
| 仅人可答判别 | \`answered_by\` 语义 | \`gates.py\`（:14,:25,:76,:122,:137,:184,:454） | 仅 claimId，无人类/agent 区分 |
| diff 行集合边界强制 | \`protected-config\`/\`implementation-gate\`/\`read-scope\` 结构 | \`shared/*.ts\`, \`worker/*.ts\` | 路径集合 / claim 门 / 读面，**无行集合** |
| 证据包组装器（old→new sha256 + 复跑 stdout + 红数 before→after） | \`sha256\` + 证据包结构 | \`packages/multi-workers/**\` | 未发现 |
| \`[VERIFY]\` 行机器消费侧 | \`\[VERIFY\]\` | \`packages/multi-workers/*.py, autopilot/*.py\` | 仅 prompt 文案与测试打印，无解析器 |

## 结论 → 决策映射

| # | 结论（对应上文） | 支撑的 spec / 设计决策 |
|---|---|---|
| 1 | §2：mw-crosskey-risk-escalation 是**不同问题**（PM 通知归属），代码复用面≈0，只继承"升级要 owner + 幂等 + 低风险抑制"原则 | spec §2.4 表该行应降级为"设计原则参照"；"升级半环"的**分级判据与落盘形状需新建**（Q8 状态机/去重键） |
| 2 | §3：gate 协议整体直接复用；**仅人可答无先例**；门禁内无 TTL（时间维度靠回路预算 + streak） | AC-004 需新建作答面判别；AC-007/§2.3 的"解冻权只给人"不能靠现有 \`answered_by\`；R-3 的"超时"用回路预算而非 gate TTL；Q9 推到 conductor 单点 |
| 3 | §3 payload：\`question\` 单行、\`context_refs\` 单行列表 → 复合工单承载不下 | AC-003 工单=**独立机器可读文件**（request_id/affected_keys/精确边界/追认入口），gate 仅用 \`context_refs\` 指路；形状参照 FM \`cross-key-repair-request-20260925-n1.md\` 与 \`_closure_dossier_md\`（\`conductor.py:666\`） |
| 4 | §3 kind 是**两侧闭集镜像** | 新增 \`xkey-authorize\` 必须同步 \`gates.py:52\` ↔ \`status-model.ts:467\`（+ TS 解析放行），否则面板枚举红 |
| 5 | §4：\`fail_line\`/判定源/轮次机读可得；**\`(file,test_id)\` 与交接登记不可得**；\`[VERIFY]\` 无消费侧 | **证实 spec R-1**：交付前置=交接登记机器可读化（写侧+读侧双侧测试 P-005）；AC-001 去重键需自建最小解析器，失败按 Q5 降级"仅提案/仅升级"（R-2） |
| 6 | §4：\`_persist_l3_provenance\` append-only + 去重 + 原子写 + 不覆盖历史 可直接复用 | AC-001 账本幂等与并发写（Q9）；去重键换成 \`(file, test_id, 冻结块指纹)\`（Q8） |
| 7 | §1：三条件授权 + 原子写 + per-key 锁 + 自持预算 reprompt + 终态清扫 可直接复用；证据包组装器不存在 | AC-005 边界机械强制沿用同族三条件（授权快照 ∧ 文件 sha 未漂移 ∧ 行集合 ⊆ 声明集）；AC-006"缺一不闭合"复用 \`_done_credentials_present\` 判据范式；证据包组装器**新建**（碎片：\`closure\` sha/原子写、\`_done_transaction\` step1 落盘、\`mw.py\` toolchain run meta 形状） |
| 8 | §5：作用域/可见性两 key 对写面**不适用**；写面可复用件是 \`protected-config.ts\`（路径集合）与 \`dispatch.py\`/\`worker-mode.ts\`（读面+工具白名单+REGISTRY parity） | GC-2 受限 worker 现成（dispatch type + read_scope + 工具表）；AC-005 的**行集合**校验需新建（protected-config 不能直接满足） |
| 9 | §6：\`config.py\` 是 AC-008 开关现成落点，且必须 TS 双侧镜像；\`closure.py\` 可扩展 \`authorized_change\` 泛化与 sidecar 四件套 | AC-008 走 config \`xkey_repair\`（默认 false），不落 env（P-015）；建议把"受控变更判定"收敛到 \`closure.py\` 同族模块（单向依赖、可单测、零工程词表） |
| 10 | §0 比例：直接复用 ≈35–40% / 需改造 ≈40% / 需新建 ≈20–25% | 支撑 spec §5"避免重造"；design 应把新建面精确限定为：账本、仅人可答、行集合边界、工单/证据包形状、交接登记解析 |
