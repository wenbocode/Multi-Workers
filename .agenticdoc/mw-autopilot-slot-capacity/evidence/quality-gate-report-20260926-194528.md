## TL;DR

⚠️ **有条件通过（Conditional pass）**: 0 ❌ / 13 ⚠️（7 个根本原因）/ 95 ✅（88.0%），共 108 个问题 —— 合并门禁（merge gate）在用户接…

## Summary

⚠️ **有条件通过（Conditional pass）**: 0 ❌ / 13 ⚠️（7 个根本原因）/ 95 ✅（88.0%），共 108 个问题 —— 合并门禁（merge gate）在用户接受或修复以下问题之前无法完全通过：分析层结论从未组装（三状态成因表，5 行最终结论）、没有针对 `KEY_STATUSES` 的机器跨语言锁、旁路门检测（VC-048）未实现、`dist/` 已过期、混合树归因。完整报告（原样输出，已复制到 `workers/msc-qg-quality-gate/report.md`）：

# 质量门禁报告: mw-autopilot-slot-capacity

**时间**: 2026-09-27T00:00:00+00:00（评审会话无时钟；晚于最后证据戳 2026-09-26T19:03:35）
**触发**: 合入前全量质检（22 张实现卡收口后，独立质量门 worker 手动触发）
**范围**: 全量 —— 31 AC + 49 VC + 20 Coverage Matrix 行 + 8 交叉问题 = **108 问**

## 前置门禁核查（步骤 1，独立复核，不信 PM 转述）

| 检查 | 结果 | 说明 |
|---|---|---|
| spec.md 存在 AC 编号 | ✅ | AC-001..AC-031 连续 31 条，无缺号/重号（spec.md:105-135；正文引用均在 001-031 内） |
| design.md 存在 VC 编号 | ✅ | VC-001..VC-049 连续 49 条（design.md §7） |
| AC→VC 映射覆盖 100% | ✅ | design §8：31/31 AC 均有 ≥1 VC；与 evidence-requirement 的逐 AC 证据需求一致 |
| evidence-requirement.md 存在 | ✅ | 31 AC 判定标准 + 49 VC 逐条在档 |
| ac_fingerprint 一致 | ✅（方法注记） | **前像复核一致**：按生成脚本同款解析规则（`| AC-` 行、第二列）从当前 spec 解出的 id 集合 == evreq 记录的 `ac_ids`（AC-001..AC-031 逐条相同）；生成器 `.tmp/msc-gen-evidence-req.py` 在盘，算法为 `sha1("\n".join(sorted(ids))+"\n")[:12]`，对相同 id 集确定性；`b623c94027ae` 全仓唯一命中（evidence-requirement.md:9）。**诚实声明**：本会话为只读工具（无 shell），字面 sha1 重算未执行；判定依据 = 前像集合相等 + 记录值与 ac_ids 出自同一次机器生成。id 层面无漂移 |
| evidence/baseline/ 非空 | ✅ | baseline-20260926.md（三份 run 原文索引 + 既有红分类 + 环境基线 + 已知限制） |
| 每个 task 非空 ac_refs/vc_refs | ✅ | 22/22 卡均有非空绑定（T-14 为「全部」——非空但非逐条绑定，注记不扣分） |

前置门禁附加注记（均不触发中止）：

1. 研究语料实为 **24 份**（17 份 spec 相 + 7 份 design 相），任务书写的「14+7」与磁盘不符；不影响判定，仅纠正计数。
2. 本 key 任务卡**无 Error Fingerprint 段**（key 专属生成器产物）⇒ workflow 步骤 3 第 4 项检查（无 open 错误）无法机械化执行；替代面 = 每卡回执的 Residual risk 段 + T-14 全量回归（Python 包级 2 failed 均为既有红）。材料性：低，如实记录为结构性缺口。
3. 证据归集文件 `verify-20260926-190302-evidence-collection.md` 的「逐卡原始输出」附录存在**字符级折行污染**（如 T-01 段一字一行）；`[VERIFY]` 行索引与计数不受影响（19/22 卡有逐字 [VERIFY] 行；T-01/T-04/T-14 三卡为原始输出无字面行）。判定一律以各卡回执原文为准。
4. evreq 中 VC-012 期望输出写作 `count=18`（陈旧字面量；实际两侧各 23 = 旧 17 + 新 6，判据是**集合相等**且已过）。
5. T-07 回执的 pytest 输出含**上一 key**（mw-autopilot-verify-cli）的 `[VERIFY] VC-009: …` 审计行（不同编号体系），会污染本 key 证据语料的字面 grep；不影响本报告（本 key 的 VC-009 为分析层、无实现卡）。
6. `test_conductor_kill_respawn` 的「单独跑稳定通过」两次复跑（-m e2e_l2 8 passed / 单用例 1 passed 14.41s）仅记录于 baseline §0（PM 亲跑转述），原始输出未单独落盘于 evidence/runs/——接受（根部全量跑原文在档、模式与 pytest.ini 的 e2e 排除一致）。

## 问题清单与核查结果

### A. AC 问题（31）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-AC-001 | 上限三层清单 + 反证式范围 + 独立交叉核对 | ✅ 充分 | research/spec-concurrency-anchors-20260926.md:70-253（Q1-Q5 逐项 file:line + §Q2(3) 反证范围声明 :162-171）；spec-crosscheck-slot-occupancy-20260926.md:21-124（独立交叉核对并**报告差异**：裁定 RQ-1 对、RQ-4 stalled 占槽结论错）；msc-rq1 output.md:5-9（[VERIFY] RQ-1 机器行） | — |
| Q-AC-002 | 上限成因三态标注 | ⚠️ 不足 | 素材散在：per-key serial=设计约束（conductor.py:1075/1095 docstring，RQ-1 §Q2(1)）；cap=2=文档化默认（README.md:225 + spec-slot-framing:28「有意的默认」）；worker 层=无显式约束（RQ-1 反证范围）；blame 4c7c07c43（RQ-9:162）。**无任何笔记逐 cap 落「设计约束/历史默认/无依据」表**：RQ-1:16 显式移交、framing:28「成因出处待 RQ-1/RQ-3」、RQ-4:185 自认只给一条论据、RQ-9:286 段实为执行语义非成因 | 收口欠债（见行动计划 #1） |
| Q-AC-003 | 利用率/排队/并发 2v1 实测 | ✅ 充分 | research/spec-slot-utilization-20260926.md:13（中位 656/672s、失败率、Fisher p=0.11）、:219-231（分桶表）、:68-151（复算脚本）、:235-245（数据缺口）；msc-rq3 output.md:27（[VERIFY] RQ-3: projects=2 saturation=62.9%/66.7% max_overlap=3） | 分析层实测 + 复算口径齐 |
| Q-AC-004 | 占槽判定规则 + 三态表 + 频率 + 诚实声明 | ✅ 充分 | RQ-1 §Q1(3)-(4)（行状态判据 + 逐 key-status 占额表）；crosscheck F4 现场实测（非终态行→去重 key）；RQ-3 [VERIFY] stalled_slot_pct=0.00%/0.02%；RQ-1 §Q5（「cap 跳过 tick 数不可直接测量」的诚实声明 + 替代算法） | — |
| Q-AC-005 | (c2) idle 误杀证据链 + 修法 | ✅ 充分 | 证据链：msc-d7 output.md:26（[VERIFY] D7: idle_kills=24 idle_s 601-622 margin 1-22s bash 23/24）+ 阈值出处 worker-mode.ts:157（RQ-1 §Q4）；修法：msc-t04 report §2-§4（5/5 测试 + 3 反证红 + [IDLE_KILL] 字段契约）；worker_timeout_min 接线：msc-t12 report §1（dispatch.py:290/:352-353）；run-ts-suite:132-134（套件内绿） | — |
| Q-AC-006 | (c1) 门阻塞面全清单 | ✅ 充分 | msc-rq8 output.md:59（[VERIFY] RQ-8: human_gates=6 blocking_scope=… unattended_policy=absent max_gate_wait=17.40h）；机器面：msc-t13 report §5-§6（30 passed + 反证 (a)-(d)） | — |
| Q-AC-007 | 审核材料可判定性 | ✅ 充分 | msc-t09 report（源码级 no-LLM 断言：renderMonitorLines/cmdGates/renderGateCards 函数体零 dispatch/model/provider + 12 tests）；msc-rq14 output.md:18（[VERIFY] RQ-14: min_info_items=14 machine_readable=3 … replay_covered=31/34） | — |
| Q-AC-008 | (d) 串行化点 + 双路径对比 | ✅ 充分 | msc-rq5 output.md:46（[VERIFY] RQ-5: serialization_points=7 manual_overlap_max=6 autopilot_overlap_max=1 retry_escape_samples=2(89.2s,6.4s)）；D7 §3.3 | — |
| Q-AC-009 | ≥3 候选方案含「不改」 | ✅ 充分 | research/spec-slot-change-space-20260926.md:96-151（M1-M5 全表：取值域/校验/首个失败模式/可逆性/GC-1/3/4）+ :201（[VERIFY] RQ-4: options=5 … M5:none） | — |
| Q-AC-010 | 两侧镜像逐字段一致 | ⚠️ 不足 | VC-012 ✅：msc-t02 report:35（[VERIFY] VC-012: equal=true count=23 + CF1/CF2 红）。VC-011：两侧**源码相等**（roadmap.py:69-75 vs status-model.ts:344，本评审目测核对，5 值同序），但**无机器 parity 锁**（EVENT_TYPES/语料/GATE_FRONTMATTER_FIELDS 均有跨语言锁，唯独 KEY_STATUSES 无；T-08 回执声称的「machine-checked subset proof」在测试全仓不可定位） | 见行动计划 #2 |
| Q-AC-011 | 最终结论逐条回应 5 路 | ⚠️ 不足 | 各路素材均在：design.md D-001..002（(c1)）、D-016/D-017（(c2)）、D-019（(c3) 归属/孤儿行）、D-020（(c3′)/cap 不改 + RQ-9 证据）、D-018（(d) 不放开）；spec §1.1.1 五路优先级。但**无汇编文档逐条回应 (c1)(c2)(c3)(c3′)(d)**；achieved.md 未写（key 仍 EXECUTE，pm-state.md 各段为空） | 见行动计划 #3 |
| Q-AC-012 | 可观测性两量可区分 | ✅ 充分 | VC-014 达成：monitor.ts:624-636（busyKeys 改走 workerBelongsToKey canonical 谓词，manual 行不再计入 slots）+ msc-t16 report:277（CF-a 红：slotsUsed 0 vs 1）+ msc-t09（层 A 每门 1 行 + age/DRIFT）+ msc-t13 §5（doctor gates 段零写、I7 无误报） | 孤儿行无显式旗标（行龄可见 + doctor I3/I4 告警）；按 VC-014 判据过 |
| Q-AC-013 | 逃逸口 + 双写实测样本 | ✅ 充分 | design-watchdog-and-serial-20260926.md §3.3（三逃逸口逐 file:line + 重叠 89.2s/6.4s 实测）+ RQ-9 机器行（5 条 PM 手工行实测 + 写者归属判据）+ msc-t12 report:99-106 | — |
| Q-AC-014 | 并发安全前置清单 | ⚠️ 不足 | 清单 + 现状证据 + 缺位失败模式**已交付**（D7 §3.2：写面声明→机器可读→重叠拒绝/行终态化时机/锁一致性，逐项 + 11/248 散文反证 + 失败模式）；但「机器可读判据存在（非仅散文）」仅停在设计与载体（schema v2 `write_scope` 字段 + T-07 xkey P3 谓词 blast_radius⊆write_scope），派发面重叠判定未实现（生产 write_scope=0） | 设计选择 D-018「不放开」；需用户显式接受（行动计划 #4） |
| Q-AC-015 | 反作用清单 + 检测方式 | ✅ 充分 | research/spec-auto-gate-guardrails-20260926.md:91-181（F2：四条副作用 × 机制候选 × 可检测信号 × 缺位失败模式，逐格填满）+ :22（[VERIFY] RQ-11）；实现面 T-07 配额/熔断/账本 | — |
| Q-AC-016 | 自动决策边界三态 | ✅ 充分 | msc-t07 report §1（6 门谓词表 + 反例）+ §5（26 passed）+ §6 CF(a)(b)；msc-d1 report:30（[VERIFY] D1: gates=6 tautological=6/6 counterexamples_real=6）；RQ-10 三态判定表（spec-auto-gate-boundary:213-290） | — |
| Q-AC-017 | 副作用防护机制 | ✅ 充分 | msc-t07 §3（夜配额 6/键配额 2 ⇒ per-gate escalate；burst 17/60s、100/1h；熔断 auto-brake.md 持久 + 每 tick 文件重推）+ §6 CF(d) | — |
| Q-AC-018 | 审计与可回滚 | ✅ 充分 | msc-t07 §3（auto-decisions.jsonl 独立 append-only 账本，字段全：decision_id/rule_id/evidence[]/switch/budget）+ §6 CF(e)(f)；msc-t19 report:115（[VERIFY] T-19: off_bytes_identical=true） | 晨间汇总以 ledger + doctor/`mw autopilot gates` 批量回看承载（D-011 范围），无独立 digest 命令 |
| Q-AC-019 | 默认动作显式声明 | ✅ 充分 | msc-t08 report:230-231（[VERIFY] VC-024: kinds=6 missing_fields=0 ttl_hours=48 default_action=escalate-to-human）+ msc-t20 §3 AFTER 表（全 kind missing=[] healthy=True）+ 反证 (a)（要求集放宽 ⇒ 红） | T-18 旁路点已闭（生产 create 调用点穷举 = 2 处均已盖） |
| Q-AC-020 | 实现面 + 守卫不放开 | ✅ 充分 | msc-t10 report §3-§4（11 passed；反证 1：封堵缩回 gates ⇒ timeline 用例红；反证 2：无路径边界 ⇒ `_autopilotX` 误伤红；gates/**+timeline.jsonl+config.json+auto-decisions.jsonl 真实 dispatch 拒绝 + [XKEY_GATE] 留痕） | `_autopilot/xkey/**` 豁免为记录在案的偏差（提案通道必须可写；AC 允许「至少三个文件」） |
| Q-AC-021 | 归属语义统一 | ✅ 充分 | msc-t12 report:101-102（[VERIFY] VC-027: distinguishable=true / VC-028: fallback=path misjudged_conductor=false）+ §5 双反证；msc-t16 report:97-127（equivalence=30/30 mismatches=0 + 三反证红） | — |
| Q-AC-022 | 守卫缺陷 D1-D3 | ✅ 充分 | msc-t01 report §2-§4（8 passed；正则回退 `\d{4}` ⇒ gate-10000 红；删 reject 守卫 ⇒ 二次改写红；删单调判据 ⇒ closed 回退红——三反证齐）；D3：msc-t02 report:35 | — |
| Q-AC-023 | 统计口径 + 洪防 | ✅ 充分 | msc-t05 report §3(c)（双消费幂等：字段写 1 次/事件 1 次/字节相同）+ RQ-10 洪泛陷阱量化（6694 事件=10 门）+ D3 复合键 | — |
| Q-AC-024 | 影子模式门槛 | ✅ 充分 | msc-t07 §6 CF(c)（影子跑两次：门文件与 roadmap 字节相同、无 gate-answered、恰 1 行账本）+ msc-t21 report:119-122（[VERIFY] T-21: shadow_row… nights_after=0 ⇒ live 被门槛挡） | — |
| Q-AC-025 | 命题三分 + 恒真自检 | ✅ 充分 | msc-t07 §1（重写后命题 + 反例表）+ §6 CF(a)（恒真 fixture ⇒ rule_falsifiable=False ⇒ escalate）+ msc-d1:30 | — |
| Q-AC-026 | 最小信息契约 + 三层呈现 | ✅ 充分 | msc-t09 report（1+13N 行数测试、唯一哨兵逐字、DRIFT、≤110 列、4 反证全红复绿、40 名镜像逐字比对）+ msc-t03（27 tests，老文件兼容 + fail-closed）+ msc-t13 §4-§5（Python 镜像 30 tests） | — |
| Q-AC-027 | 延后复核（收口前置） | ✅ 充分 | msc-t08 report:218-229（[VERIFY] VC-039/040/041/042/043 逐字）+ §6 CF(a)(d)；生产接线：msc-t19 report:113-116 | — |
| Q-AC-028 | 消费记录持久化 + 单调性 | ✅ 充分 | msc-t05 §3(a)（删 timeline ⇒ 新读取器仍判已消费，旧红）+ (b)（id 复用复合键）+ msc-t01 D4 + msc-t08:228-229 | — |
| Q-AC-029 | 取证源优先级 + 对账 | ✅ 充分 | msc-t06 report §[VERIFY]（20 passed + 三变异红：drift-blind/default-bound/correction-blind 各打红；E2 锚点逐字 sha256 校验）+ msc-t07 §3（对账拦新 stage-close，历史只 warn） | 对账 gated on `auto_gate_mode != off`（opt-in 范式，回执风险 #2 已声明） |
| Q-AC-030 | 不可伪造审计字段 | ✅ 充分 | msc-t07 §6 CF(f)（live 决策后篡改 answered_by/answered_at ⇒ auto_authority_fields 不变且不含 answered_by）+ msc-t10 §3（工具通道伪造被拒留痕） | — |
| Q-AC-031 | 门有效性审计 | ⚠️ 不足 | VC-049 ✅：msc-t13 §6(d)（roadmap_validation.problems 可见 + suggest 行 + `test_roadmap_invalid_is_visible`）。VC-048 ⚠️：绕门散文授权的机器判定**未实现**（packages/multi-workers 全仓 `cross-key-repair-request` 0 命中、无测试、无卡绑定）；研究级判据与实测样本在 design-gate-propositions §6.2 P4 + G11（:373/:409/:515） | 见行动计划 #5 |

### B. VC 问题（49）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-VC-001 | 三上限锚点 + 成因三态标注 | ⚠️ 不足 | 锚点 + 反证范围 ✅（RQ-1 [VERIFY] 机器行 + §Q2(3)）；「三态之一」标注未成表（同 Q-AC-002） | — |
| Q-VC-002 | 非终态行集合 == in_flight_keys 逐 key | ✅ 充分 | msc-rq1 output.md:7（[VERIFY] RQ-1: in_flight=non-terminal rows, pending_counts=true, stalled_row_keeps_slot=true）+ crosscheck F4 现场实测（行数→去重 key 对照表） | 分析层复算 |
| Q-VC-003 | 打满率 + worker 分布 + 样本量 | ✅ 充分 | msc-rq3 output.md:27（[VERIFY] RQ-3）+ spec-slot-utilization:153-231 | 任务书称「无字面命中」实为内容在 RQ-3 |
| Q-VC-004 | [IDLE_KILL] 证据完整 | ✅ 充分 | msc-t04 report §4（字段契约 + 真实样本行）+ §2（5/5） | 回执无字面 [VERIFY] 行；原始输出在档 |
| Q-VC-005 | bash 心跳续命 | ✅ 充分 | msc-t04 §3(a)（删心跳 ⇒ VC-005 用例红，复绿） | — |
| Q-VC-006 | 真挂死仍判死 | ✅ 充分 | msc-t04 §3(b)(c)（放宽分类/删证据发射 ⇒ 红） | — |
| Q-VC-007 | 6 类门阻塞范围 + 锚点 | ✅ 充分 | msc-rq8 output.md:59 + msc-t13 §5 | — |
| Q-VC-008 | 机器抽取非 LLM 生成 | ✅ 充分 | msc-t09（源码级断言 + 哨兵字面量 + 禁 hedge 词测试） | — |
| Q-VC-009 | 每 key 每 tick ≤1 在飞 | ✅ 充分 | msc-rq5 output.md:46 + RQ-1 §Q2(1)（三重结构保证） | 分析层 |
| Q-VC-010 | 方案集含不改 | ✅ 充分 | msc-rq4 output.md:201（[VERIFY] RQ-4: options=5 M5:none） | 同 VC-003 注 |
| Q-VC-011 | KEY_STATUSES 两侧逐值相等 | ⚠️ 不足 | 源码目测相等（roadmap.py:69-75 == status-model.ts:344，5 值同序——本评审核对）；**无机器 parity 测试**（coding-agent/test 与 multi-workers/test 全仓无跨语言 KEY_STATUSES 断言）；T-08 回执:254 声称的 subset proof 找不到落点 | 见行动计划 #2 |
| Q-VC-012 | EVENT_TYPES 集合相等 | ✅ 充分 | msc-t02 report:35（[VERIFY] VC-012: equal=true count=23）+ §4 CF1/CF2 红 | evreq 期望 count=18 为陈旧字面量 |
| Q-VC-013 | 结论回应 5 路 | ⚠️ 不足 | 同 Q-AC-011 | — |
| Q-VC-014 | slots 两量分别可读 + 口径标注 | ✅ 充分 | monitor.ts:624-636 + msc-t16:277（CF-a 红）+ msc-t09 层 A | — |
| Q-VC-015 | 三逃逸口锚点 + 复算样本 | ✅ 充分 | D7 §3.3 + RQ-9 机器行 + msc-t12:99 | — |
| Q-VC-016 | 写面机器可读判据 | ⚠️ 不足 | 前置清单/现状/失败模式已交付（D7 §3.2）；机器判定本身 = 0（RQ-5: same_key_write_surface_check=none） | 设计选择 D-018；见行动计划 #4 |
| Q-VC-017 | 反作用↔机制成对 | ✅ 充分 | spec-auto-gate-guardrails:91-181（F2 四条全配对）+ [VERIFY] RQ-11 | 任务书称「无字面命中」实为内容在 RQ-11 |
| Q-VC-018 | case1 集合 = 四判据命中 | ✅ 充分 | msc-t07 §1/§3（budget-exhausted + stalled FN 窄集 + xkey S4 + goal-change 起门面）+ 26 tests | — |
| Q-VC-019 | 配额上界 ⇒ escalate | ✅ 充分 | msc-t07 §3（夜 6/键 2 ⇒ per-gate escalate）+ 26 tests | — |
| Q-VC-020 | 熔断落盘重启仍熔断 | ✅ 充分 | msc-t07 §6 CF(d)（新 ConductorState/Timeline 仍 tripped；内存态实现红） | — |
| Q-VC-021 | 账本行字段完整 | ✅ 充分 | msc-t07 §3 字段清单 + 26 tests | — |
| Q-VC-022 | off = 今天行为 | ✅ 充分 | msc-t19:115（[VERIFY] off_bytes_identical=true）+ msc-t07 §3 + 83 passed 回归 | — |
| Q-VC-023 | 撤销 = answered − revoked | ✅ 充分 | msc-t07 §6 CF(e)（revoke first ⇒ 集合剩 second；answered-only 读者红） | — |
| Q-VC-024 | 声明缺失 ⇒ 告警 | ✅ 充分 | msc-t08:230-231 + msc-t13 §6(a)（I2 + exit 1）+ msc-t20 §3-§4（反证 (a) 红） | — |
| Q-VC-025 | 工具通道写被拒 + 留痕 | ✅ 充分 | msc-t10 §3（真实 dispatch：write/edit 对 timeline/config/auto-decisions/gates 全 isError + trace.log [XKEY_GATE]） | — |
| Q-VC-026 | 关闭时 agent 写权限不变 | ✅ 充分 | msc-t10 §5（gates 封堵无回归；未放开任何新权限） | — |
| Q-VC-027 | origin 可机器区分 | ✅ 充分 | msc-t12:101 + msc-t16:97-127 | — |
| Q-VC-028 | 旧行 path 兜底不误判 | ✅ 充分 | msc-t12:102 + msc-t16（legacy/no-origin 30 组用例） | — |
| Q-VC-029 | 5 位 gate id 命中 | ✅ 充分 | msc-t01 §2-§4（8 passed；回退 `\d{4}` ⇒ `assert set()=={'gate-10000'}` 红）+ 全量套件绿（run-python-full-suite 短摘要仅 3 个既有红） | 回执无字面 [VERIFY] 行 |
| Q-VC-030 | reject 重放不二次改写 | ✅ 充分 | msc-t01（删守卫 ⇒ 重放 fixture 出现第二次改写红） | 同上 |
| Q-VC-031 | 复合键不串代 | ✅ 充分 | msc-t05 §3(b)（同 id 新 created_at ⇒ 新实现空集/答案生效；旧 id-only 红） | — |
| Q-VC-032 | 去重 + 洪防 | ✅ 充分 | msc-t05 §3(c) + RQ-10 洪泛口径（6694 事件只来自 10 门） | — |
| Q-VC-033 | 影子零状态差 | ✅ 充分 | msc-t07 §6 CF(c) + msc-t21:119 | — |
| Q-VC-034 | 样本不足 live 不可开 | ✅ 充分 | msc-t21:121（shadow_decisions/nights 计数）+ msc-t07 §3（shadow gate ≥5 夜 ∧ ≥20 条 ∧ 每规则反例） | — |
| Q-VC-035 | 恒真自检拒绝 | ✅ 充分 | msc-t07 §6 CF(a) | — |
| Q-VC-036 | 6/6 可证伪 + disk witness | ✅ 充分 | msc-t07 §1 表 + msc-d1:30（counterexamples_real=6） | — |
| Q-VC-037 | 行数 == 1+13N | ✅ 充分 | msc-t09（N=1→14 / N=3→40 用例 + 反证） | — |
| Q-VC-038 | 唯一哨兵 + 仅 pending 报 missing | ✅ 充分 | msc-t09（哨兵逐字 + answered 门不报）+ msc-t03（老文件兼容） | — |
| Q-VC-039 | 待复核阻收口 | ✅ 充分 | msc-t08:218/221（enum=1 dep_satisfied=0 dispatched=0 unknown_value_fail_closed=true；blocked=true counterfactual_dossier=1）+ CF(d) | fixture 级端到端（L2 判据按测试形态达成） |
| Q-VC-040 | 批量复核 | ✅ 充分 | msc-t08:222-223 | — |
| Q-VC-041 | 48h 升级状态不变 | ✅ 充分 | msc-t08:224-225 | — |
| Q-VC-042 | 回退拒绝 + 去重 | ✅ 充分 | msc-t08:228 + msc-t01 D4（refused=1 dedup=true） | — |
| Q-VC-043 | 重放 stage 不回退 | ✅ 充分 | msc-t08:229 + msc-t05 §3(a) | — |
| Q-VC-044 | correction below ⇒ 非 done+closed | ✅ 充分 | msc-t06 §(c)（correction-blind 变异红；E2 锚点逐字）+ msc-t07 §3（对账拦新 stage-close） | 默认 off 时对账 inert（opt-in，已声明） |
| Q-VC-045 | 漂移检出 | ✅ 充分 | msc-t06 §(a)（drift-blind 变异红）+ msc-t08:232 | — |
| Q-VC-046 | 权威字段 conductor 派生 | ✅ 充分 | msc-t07 §6 CF(f) | — |
| Q-VC-047 | 伪造经工具通道被拒 | ✅ 充分 | msc-t10 §3-§4 | — |
| Q-VC-048 | 绕门 ⇒ 判未授权 | ⚠️ 不足 | 研究级判据 + 实测样本在（design-gate-propositions:373 P4〔FM 手写 decision 行实测〕、:409、G11 :515「只读扫描 + fail-closed 视为未授权」）；**无实现**（packages/multi-workers `cross-key-repair-request` 0 命中）、**无测试**、**无卡绑定**（T-13 仅绑 VC-049） | 见行动计划 #5 |
| Q-VC-049 | roadmap 校验被调用且可见 | ✅ 充分 | msc-t13 §6(d)（roadmap_validation.problems + suggest 行；`test_roadmap_invalid_is_visible`） | conductor 不强制（回执风险 #2 已声明） |

### C. Coverage Matrix 问题（20）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-COV-F1 | 上限事实与成因（正常/边界/异常） | ⚠️ 不足 | 异常路径「数据不足声明」✅（RQ-1 数据缺口 6 项）；正常路径「三态标注齐全」未成表（同 Q-AC-002） | — |
| Q-COV-F2 | 占槽（done 残留/孤儿行） | ✅ 充分 | RQ-1 §Q1(4)-(5) + RQ-4 §5（挂死行 90min 静默窗）+ crosscheck F4 | — |
| Q-COV-F3 | idle 看门狗三态 | ✅ 充分 | msc-t04 §2-§4（心跳续命/无工具分支二次确认/真挂死仍杀） | — |
| Q-COV-F4 | 门命题 4 判据 | ✅ 充分 | msc-t07 §1 + msc-d1:30 | — |
| Q-COV-F5 | 消费记录三态 | ✅ 充分 | msc-t05 §3(a)(b)(c)（轮转丢失/id 重用/双消费） | — |
| Q-COV-F6 | D1-D4 + gate-10000/reject 重放/stage 回退 | ✅ 充分 | msc-t01 §2-§4 + msc-t02 + msc-t08:226-229 | — |
| Q-COV-F7 | 三分处置各归位 | ✅ 充分 | msc-t07 §1/§3（政策面永 case3、恒真拒绝） | — |
| Q-COV-F8 | 待复核（触发/兜底/不解锁） | ✅ 充分 | msc-t08:218-229 + msc-t19:113-116 | — |
| Q-COV-F9 | 合法重开无 done 出口 | ✅ 充分 | msc-t08:226（done_exit=rejected closed_legacy_exit=rejected） | — |
| Q-COV-F10 | 快照两时点/changed[]/漂移拦收口 | ✅ 充分 | msc-t06 §(a) + msc-t07 §3 | — |
| Q-COV-F11 | data 字段完整/影子/丢字段 | ✅ 充分 | msc-t07 §3 + §6 CF(c) | — |
| Q-COV-F12 | 开关 off/shadow/非法值 | ✅ 充分 | msc-t07 §3 + msc-t03（_ENUM_FIELDS fail-closed :124-131）+ msc-t19:115 | — |
| Q-COV-F13 | 熔断重启仍熔断 | ✅ 充分 | msc-t07 §6 CF(d) | — |
| Q-COV-F14 | 回滚 answered−revoked | ✅ 充分 | msc-t07 §6 CF(e) | — |
| Q-COV-F15 | schema v2（可选/老文件/老代码读新） | ✅ 充分 | msc-t03 §2-§3（27 tests；GateFormatError fail-closed；_REQUIRED_FIELDS 不动） | — |
| Q-COV-F16 | 呈现（逐字/截断/禁 LLM） | ✅ 充分 | msc-t09（4 反证全红复绿） | — |
| Q-COV-F17 | `_autopilot/**` 封堵/带外/伪造留痕 | ✅ 充分 | msc-t10 §4（三反证） | 残余风险（同 uid 带外写入）已显式声明 |
| Q-COV-F18 | 归属（origin/兜底/前缀假信号） | ✅ 充分 | msc-t12 §5 + msc-t16（6 条假信号行用例） | — |
| Q-COV-F19 | timeout: 接线/缺省维持 | ✅ 充分 | msc-t12:105-106（counterfactual-b: absent_when_unconfigured=true；dispatch: origin=conductor timeout=45 row_verified=true） | — |
| Q-COV-F20 | 跨语言 parity | ✅ 充分 | msc-t11 §2-§4（语料 53→55 双侧同 sha、13→14 断言、negative lock CF 红）+ msc-t02 | KEY_STATUSES 锁缺失单列为 Q-VC-011 |

### D. 交叉问题（8，评审自提）

| 问题 ID | 描述 | 状态 | 证据引用 | 备注 |
|---|---|---|---|---|
| Q-X1 | 自动决策账本 × 守卫封堵 × 权威字段交互（AC-018×020×030） | ✅ 充分 | msc-t10 §3（auto-decisions.jsonl 拒绝留痕）+ msc-t07 §6 CF(f) | — |
| Q-X2 | 波次顺序约束（D-003：第 0 波 D3+D1 → 第 1 波 载体+D2+D4 → 第 2 波 自动决策 → 第 3 波 延后复核）是否被遵守 | ✅ 充分 | msc-t07 §0（声明 T-01/02/03/05/06 已落未回退）；msc-t08 依赖 T-05 载体与 T-01 D4；msc-t19 依赖 T-07/T-08 | 推断自回执交叉引用；无时间线级独立证明（可接受） |
| Q-X3 | 混合工作树归属（mw-vision-role 与本 key 重叠：dispatch.py、test_autopilot_dispatch.py、worker-store.ts、两 CHANGELOG） | ⚠️ 不足 | baseline-20260926.md §4.1（证据在混树上采集，物理不可剥离；分类与归属逐条记录） | 见行动计划 #6 |
| Q-X4 | dist 未重建 ⇒ 产物层同波约束未满足 | ⚠️ 不足 | baseline §4.2 + msc-t14 §6（sourcemap_drift stale 22/472）；multi-workers/dist/extensions/agent-team-loop.js:21030 仍为 4 值 KEY_STATUSES（无 pending-review）——D-021 同波约束仅在源码层满足 | 见行动计划 #7 |
| Q-X5 | PM 执行期三处修正后的最终一致性（T-19 陈旧 `auto_decision_rows=0`；T-20 卡面 `healthy=False` 夸大；T-18 发明 reason_code 字面量） | ✅ 充分 | msc-t22 report:25-36（旧值未断言 ⇒ 修为实测 defer_rows=1；全量 `-q -s` 语料重采，仅 4 行变化且无第二处假数值）+ msc-t20 §3（AFTER 表全 kind missing=[]/healthy=True；goal-change reason_code=None，越集值由写侧守卫删除 + config 事件留痕） | 最终产物一致；卡面文字与回执冲突处以回执为准 |
| Q-X6 | 凭证隔离约束未被破坏（spec §2.3） | ✅ 充分 | 无凭证路径改动落地（D-020 不改 cap、D-018 不放开并发）；RQ-2 §2（剥全部 + 注入单 key 语义现状未动） | 约束面无改动 ⇒ 无需新 Q |
| Q-X7 | int 键机器层语义缺口未被采用（AC-010 后半） | ✅ 充分 | `auto_gate_mode` 为 str 闭集且不入 EFFECTIVE_KEYS：msc-t11 §1 + msc-t15 §3（负断言 + CF：塞入 ⇒ 红）+ msc-t17 CF-2 | — |
| Q-X8 | kill switch 粒度 = 只停自动决策（AC-018） | ✅ 充分 | msc-t07 §3（off = 无账本/无 sidecar/无事件/无屏障）+ msc-t19:115 + VC-022 | — |

## 汇总

- **总问题数**: 108
- **通过（充分）**: 95（88.0%）
- **有条件通过（不足）**: 13（验证欠债 13 项，归并为 **7 个根因**）
- **未通过（无证据）**: 0

**质检结论**: ⚠️ **有条件通过（欠债 13 项 / 7 根因）**。无 ❌；但按「全量质检（合入前）= 无 ❌ 且无 ⚠️（或所有 ⚠️ 经用户确认接受）」的通过标准，**当前不能直接合入**——需先补齐行动计划或由用户显式接受全部 ⚠️。13 项 ⚠️ 中：实质缺口 5 个根因（成因三态表未成文、KEY_STATUSES 无机器 parity 锁、最终结论未汇编、写面机器判据未落地（设计选择）、绕门检测未实现）；环境性 2 个（混树归属、dist 陈旧）；其余为同根因的 AC/VC/COV 汇总行。

## 未通过问题行动计划

| 问题 | 根因 | 所需动作 | 负责 Task |
|---|---|---|---|
| Q-VC-001 / Q-AC-002 / Q-COV-F1 | 成因三态判定在 RQ-1→RQ-2/RQ-4→RQ-9 间传递后无人收口（素材齐、表未成） | 在收口文档（achieved.md 或 PM 结论段）逐 cap 落三态标注：per-key serial=设计约束（conductor.py:1075/1095）；key cap=2=文档化默认（README.md:225、framing:28）；worker 层=无显式约束（RQ-1 反证范围 :162-171；blame 4c7c07c43，RQ-9:162）；serve 层=单线程监督循环（mw.py:353-374） | PM 收口（achieved.md），无需代码卡 |
| Q-VC-011 / Q-AC-010 | KEY_STATUSES 无跨语言机器锁（EVENT_TYPES/语料/GATE_FRONTMATTER_FIELDS 均有锁，唯 enum 无；T-08 回执声称的 subset proof 不可定位） | 新增 parity 测试：镜像 `autopilot-event-parity.test.ts` 的 python-dump 模式，断言 `roadmap.KEY_STATUSES` 与 TS `KEY_STATUSES` 逐值同序（并锁 `_DEP_SATISFIED` 镜像面） | 新 mini 卡（T-08 后续） |
| Q-VC-013 / Q-AC-011 | key 未收口：五路最终结论未汇编（achieved.md 未写，pm-state.md 各段为空） | achieved.md 按 goal.md 判定方式逐 AC 落证据 + (c1)(c2)(c3)(c3′)(d) 五路结论表（引用 AC-002..AC-010 证据链） | PM 收口 |
| Q-VC-016 / Q-AC-014 | 设计选择 D-018「本 key 只做可观测与判据，不放开」⇒ 写面机器判据仅设计与载体落地（schema v2 `write_scope` + T-07 xkey P3 谓词），派发面重叠拒绝未实现（生产 write_scope=0） | 用户显式接受「不放开」范围；把 D7 §3.2 四条前置写入后续 key 的入口条件（若将来放开，需 `writes:` 声明 + 重叠拒绝卡） | 用户确认 / 后续 key 入口条件 |
| Q-VC-048 / Q-AC-031 | 无卡绑定（T-13 只绑 VC-049）；绕门散文授权的机器判定未实现 | doctor gates 增只读扫描 `_autopilot/evidence/cross-key-repair-request-*.md` 的 `decision:` 行 ⇒ I 类 issue + fail-closed「视为未授权」（判据已由 D1 §6.2 P4/G11 给出，含 FM 实测样本） | 新卡（建议 T-23） |
| Q-X3 | 混合工作树（mw-vision-role 重叠写面），证据不可物理剥离 | 本 key 合入后对重叠面（dispatch/attribution/worker-store/CHANGELOG 相关套件）做一次净树重跑；或用户显式接受 baseline §4.1 归属声明 | PM |
| Q-X4 | dist 未重建（无用户指令）：产物层 KEY_STATUSES 仍旧 4 值，D-021 同波约束在产物层未满足 | 合入/发布前 `mw build` 重建 + A1b staleness 判据复绿（sourcemap_drift 归零） | PM / release |

## 二次印证结论

重读 spec.md 与 design.md 后的二次扫描：

1. **约束覆盖（检查 1）**：§2.2 性能（吞吐衡量 + 首个失败模式可观测）由 Q-AC-003/Q-AC-009 覆盖；§2.3 安全（gate 目录封堵）由 Q-AC-020/Q-COV-F17 覆盖；**凭证隔离无直接 Q**——本 key 未改任何凭证路径（D-020 不改 cap、D-018 不放开并发），约束面为空操作，如实说明而非补造问题（Q-X6 记录）；§2.1 平台与 §2.4 集成依赖由环境基线与 AC-012/AC-021 覆盖。
2. **Function Flow 节点映射（检查 2）**：自动决策主链与收口/待复核两图全部节点均有对应 Q——tick/mode→VC-022；shadow→VC-033；live+熔断/配额→VC-019/020；「值层 meets ∧ 绑定层 bound」→VC-044/045；写账本→VC-021；consumed_at→VC-043；可撤销→VC-023；批量复核/48h→VC-040/041；合法重开→VC-042；异常出口五类（GateFormatError→VC-038 + T-03 fail-closed 用例；未知 key-status→VC-039 的 unknown_value_fail_closed；证据不一致→VC-044；熔断→VC-020；单调性拒绝→VC-042）。无遗漏节点。
3. **Coverage Matrix 异常路径行（检查 3）**：20 行全部有 Q-COV；仅 F1（正常路径「三态标注齐全」）⚠️，其余 ✅。
4. **空 vc_refs（检查 4）**：22/22 卡非空（T-14 为「全部」式绑定，非空但非逐条——注记不判 ⚠️）。
5. **结构性与语料注记**（如实记录，不另立 ❌）：(a) 卡片无 Error Fingerprint 段 ⇒ 步骤 3「无 open 错误」检查不可机械化，以回执 Residual risk + T-14 全量回归替代；(b) 证据归集文件的原始输出附录字符折行污染（[VERIFY] 索引不受影响，回执为权威源）；(c) evreq VC-012 `count=18` 陈旧字面量；(d) T-07 回执混入上一 key 的 `[VERIFY] VC-009` 审计行（语料污染，不影响判定）；(e) 研究语料 24 份（任务书写 14+7）；(f) T-10 对 `_autopilot/xkey/**` 的豁免为对 design D-013「`_autopilot/**`」的记录在案偏差（满足 AC-020「至少三个文件」下限，理由 = xkey 提案通道必须可写）。
6. **诚实期望项复核**：任务书点名的 6 个「无字面 ID 命中」项按关键词追查后：VC-003 ✅（内容在 RQ-3）、VC-010 ✅（RQ-4）、VC-017 ✅（RQ-11）、AC-011 ⚠️、VC-016 ⚠️、VC-048 ⚠️——未平滑处理，⚠️ 三项均入行动计划。三处 PM 执行期修正（T-19/T-20/T-18）经 Q-X5 复核，**最终产物一致**。

**总评**：实现层证据链（21 张实现卡的运行证据 + 3 份全量 run + 基线）质量高——反证（还原缺陷 ⇒ 变红）在 T-01/T-02/T-04/T-05/T-06/T-07/T-08/T-09/T-10/T-11/T-12/T-15/T-16/T-17/T-20/T-21 均为实跑且非空洞；缺口集中在**分析层收口物未成文**（成因三态表、五路最终结论）与**两处未落地的设计判据**（KEY_STATUSES 机器锁、绕门检测），以及两项环境性欠债（混树、dist）。补齐行动计划 7 项（或用户显式接受）后即可过合入门。 Tools used: find, grep, ls, read, worker_file (103 calls).

## Changed Files



## Verification Steps

See task output for details.

## Exit Reason

Agent settled after 103 tool call(s).
