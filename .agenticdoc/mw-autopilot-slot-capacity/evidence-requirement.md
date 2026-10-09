# Evidence Requirement: mw-autopilot-slot-capacity

## 锁定指纹

| 字段 | 值 |
|------|-----|
| spec_path | `.agenticdoc/mw-autopilot-slot-capacity/spec.md` |
| spec_locked_at | 2026-09-26 |
| ac_fingerprint | `b623c94027ae` |
| ac_count | 31 |
| ac_ids | AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-007, AC-008, AC-009, AC-010, AC-011, AC-012, AC-013, AC-014, AC-015, AC-016, AC-017, AC-018, AC-019, AC-020, AC-021, AC-022, AC-023, AC-024, AC-025, AC-026, AC-027, AC-028, AC-029, AC-030, AC-031 |
| vc_count | 49 |
| vc_ids | VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-012, VC-013, VC-014, VC-015, VC-016, VC-017, VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-024, VC-025, VC-026, VC-027, VC-028, VC-029, VC-030, VC-031, VC-032, VC-033, VC-034, VC-035, VC-036, VC-037, VC-038, VC-039, VC-040, VC-041, VC-042, VC-043, VC-044, VC-045, VC-046, VC-047, VC-048, VC-049 |
| generated_at | 2026-09-26T16:44:41 |
| generator | `.tmp/msc-gen-evidence-req.py`（机器生成，逐字锚定 spec AC 行与 design §7/§8） |

## AC 证据需求

## AC-001: `evidence/research/spec-*.md` 至少一份笔记以 `file:line` 锚点给出「key 层上限」「worker 层上限（单 key 内 / 全局）」「serve/launcher 层是否存在并发限制」三者的完整清单（每项：变量名、默认值、生效位置 file:line、可…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-001: caps=3 annotated=3` | 预设节点输出（L0） | 当审阅 spec 与 spec-*.md 时，三个并行度上限各带 file:line 出处且成因标注属于三态之一 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-002: 给出并行度上限的现状成因判定：对每个上限逐一标注"设计约束（附出处 file:line / 文档 / 提交）/ 历史默认 / 无依据"三态之一；不得出现"大概是"这类无出处结论

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-001: caps=3 annotated=3` | 预设节点输出（L0） | 当审阅 spec 与 spec-*.md 时，三个并行度上限各带 file:line 出处且成因标注属于三态之一 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-003: 给出槽位利用率与排队实测（≥2 个真实项目）：key 层打满率（达到上限的时间占比）+ worker 层同时运行数分布（平均/峰值）+ 并发 2 vs 1 的吞吐与失败率对比（中位墙钟、失败率、失败类型分布）+ 样本量与时间窗；每个数字可由文件复算（给出复算命令/脚本片段）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-003: projects>=2` | 预设节点输出（L0） | 当复算并发利用率时，输出打满率与 worker 数分布且样本量写明 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-004: 给出占槽判定规则的代码锚点（按行状态、与 key-status 无关）+ 三类状态（stalled / done / 在飞）的占槽表 + 频率实测（stalled 占槽占比、孤儿行占槽占比）；若频率数据不足以实测，必须给出"无法实测"的诚实声明 + 可验证它的方法与所需数据

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-002: rows_matched=true` | 预设节点输出（L1） | 当复算占槽判定时，非终态行集合与 in_flight_keys 逐 key 相等（与 key-status 无关） | 单次 PASS |
| 路径分类 | 边界 | — | — |

## AC-005: 给出 (c2) idle 看门狗误杀的证据链：14 次（或实测到的全部）idle 判死事件的复算 + 每次死亡时刻的活动特征（是否真的无活动、阈值余量多少）+ 阈值 600s 的出处 + `worker_timeout_min` 无消费者的处置判定（接线或删除，二选一并给证据）［REVISED @ …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-004: idle_evidence=complete` | 预设节点输出（L1） | 当 idle 判死时，事件含 [IDLE_KILL] 与 in-flight 工具名、工具已运行秒数、阈值 | 单次 PASS |
| `[VERIFY] VC-005: alive=true` | 预设节点输出（L1） | 当 bash 在飞且无输出超过 toolIdleMs 时，worker 不被判死（心跳续命） | 单次 PASS |
| `[VERIFY] VC-006: killed=true` | 预设节点输出（L1） | 当 worker 真挂死（无 in-flight 工具且无 token 增量）时，仍被判死 | 单次 PASS |
| 路径分类 | 正常/边界/异常 | — | — |

## AC-006: 给出 (c1) 无人值守门阻塞面：必须人答的 gate 全清单（每项：谁答、`file:line`、无人值守后果、阻塞范围 key/stage/roadmap）+ stage 收口语义（一个 stalled key 是否让 stage 永久停住，附判定分支原文）+ 每类 gate 的等待时长分布实测…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-007: kinds=6 anchors=6` | 预设节点输出（L0） | 当枚举 6 类门时，每类给阻塞范围 key/stage/roadmap 且带 conductor 锚点 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-007: 给出 (新增需求) gate 审核材料可判定性：每个 gate 类型当前"给人看的东西"清单（字段/文件/面板行 + `file:line`）；判定"必要性"与"影响面"各需要什么输入；哪些必要性可由机器从文件推导（给推导依据与反例），哪些不能；缺口清单与最小补面

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-008: generated=false` | 预设节点输出（L1） | 当渲染任一 pending 门时，每条最小信息项来自机器抽取字段（非 LLM 生成） | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-008: 给出 (d) 的直接证据：单 key 内 worker 派发的串行化点清单（每点：函数 `file:line` + 触发条件 + 硬顺序还是可并行）；并用同项目两组真实运行对比（autopilot/conductor 路径 vs PM 手工派发路径）的同时 worker 数，证明瓶颈位于哪一侧

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-009: per_key_max=1` | 预设节点输出（L1） | 当检查 per-key 派发点时，同一 key 同一 tick 至多一个 in-flight 行 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-009: 给出 ≥3 个候选改动方案（覆盖 (c1)(c2)(c3)(c3′) 与 (d) 各路，且必须含"不改"一项），每项：改动位置（`file:line`/键名）、取值域与校验、首个失败模式（含判据 + 标注是已有史料还是 `[推断]`）、可逆性（如何退回、是否留残留）、GC-1/GC-3/GC-4 校…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-010: options>=3 includes_noop=true` | 预设节点输出（L0） | 当提交方案集时，含"不改"项且每项给取值域、校验与首个失败模式 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-010: 两侧镜像一致性：任何被选中的参数/语义改动必须 Python 与 TS 逐字段一致（P-021，verify 期两侧都跑）；若方案依赖机器层覆盖 int 键，必须先解决"空值即未决定"无 int 哨兵的语义缺口，否则不得采用该路径（否则是静默空操作）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-011: equal=true` | 预设节点输出（L1） | 当比对两侧 key-status 集合时，Python 与 TS 的 enum 逐值相等 | 单次 PASS |
| `[VERIFY] VC-012: equal=true count=23` | 预设节点输出（L1） | 当比对两侧 EVENT_TYPES 时，排序集合相等（含 target-config-rejected）。**注**：期望值为实测值 23（旧 17 + 本 key 新增 6），此处原写 `count=18` 系陈旧字面量，已于 2026-09-26 按 T-02 实测 `[VERIFY] VC-012: equal=true count=23` 更正；判据本身是**集合相等**，计数仅为附带信息 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-011: 最终结论必须由 AC-002..AC-010 的证据链支撑，并逐条回应 (c1)(c2)(c3)(c3′)(d)：说明如何改善夜跑吞吐与 worker 层利用率，或为何不该动；"不改"也必须给证据化理由

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-013: answered=5` | 预设节点输出（L0） | 当阅读结论时，每条回应 (c1)(c2)(c3)(c3′)(d) 并由 AC-002..AC-010 支撑 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-012: 可观测性：面板/`mw doctor` 能区分「key 层槽位」与「worker 层实际运行数（含 `pending` 行）」两个量（口径差异必须消除或显式标注），能指出谁占着槽、哪些行是孤儿/stalled、哪些 gate 在等谁；不新增误报（无 running worker 的项目显示 0 而非…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-014: distinct=true manual_split=true` | 预设节点输出（L1） | 当面板渲染 slots 时，key 层槽位与 worker 层运行数分别可读且口径显式标注 | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-013: 给出逃逸口与现存双写源的证据：三个逃逸口（PM 手工通道无并发判定、行提前终态化、`xkey_repair` 提案通道）逐一定位 `file:line`；其中"行提前终态化"必须给出 ≥1 个实测复算样本（现状：两例，重试与旧进程重叠 89.2s / 6.4s）及对"同文件双写"的影响面；若无法判定…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-015: escapes=3 sample=true` | 预设节点输出（L0） | 当审计逃逸口时，三处各带 file:line 且"行提前终态化"给实测复算样本 | 单次 PASS |
| 路径分类 | 边界 | — | — |

## AC-014: 给出并发安全前置清单：若方案要放开 per-key 并发，必须列出前置项（写面声明→机器可读→重叠拒绝；行终态化时机；锁一致性）并给出每项现状证据与缺位时的首个失败模式。现状反证（RQ-5）：写面纪律只存在于 11/248 个任务书的散文里，`write_scope` / `写面` 在生产代码零命中…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-016: machine_check=true` | 预设节点输出（L0） | 当检查写面声明时，机器可读判据存在（非仅散文）；缺位时首个失败模式写明 | 单次 PASS |
| 路径分类 | 边界 | — | — |

## AC-015: 给出无人值守 gate 策略的反作用清单（若方案含自动 approve/reject/超时）：逐条给判据 —— (a) auto-approve × `_resume_credits` 无上界 ⇒ 夜间无限换 key / 烧 token；(b) `closed-legacy ∈ _DEP_SATIS…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-017: effects<=>mitigations` | 预设节点输出（L0） | 当枚举自动决策反作用时，每条附配套机制或显式"本 key 不处理" | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-016: 给出自动决策边界与判据（支撑 C 的"部分"二字）：逐 gate 类型一张表 —— 它在决定什么、机器能否从磁盘文件判（给可读字段与 `file:line`）、历史答案分布（approve/reject 比例与样本量）、答错的代价（可逆性、是否解锁依赖/stage 收口）；结论落在三态之一：可自动 …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-018: case1=[budget-exhausted,stalled(FN-subset),xkey-S4]` | 预设节点输出（L0） | 当判定门可自动性时，命中 4 判据的门集合 == case 1 集合（其余归 case 2/3） | 单次 PASS |
| 路径分类 | 正常 | — | — |

## AC-017: 给出副作用防护机制：对每条已知副作用逐条配套机制 —— (a) `_resume_credits` 无上界 ⇒ 需要什么预算/配额；(b) `closed-legacy ∈ _DEP_SATISFIED` 解锁依赖与 stage 收口 ⇒ 自动决策如何避免静默解锁；(c) `stalled↔runn…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-019: capped=true` | 预设节点输出（L1） | 当每夜自动决策达到配额上界时，后续门一律不自动且写 escalate | 单次 PASS |
| `[VERIFY] VC-020: breaker_persisted=true` | 预设节点输出（L1） | 当门量出现 burst（超过阈值）时，熔断触发且状态落盘（重启后仍熔断） | 单次 PASS |
| 路径分类 | 边界/异常 | — | — |

## AC-018: 给出审计与可回滚方案：每次自动决策必须写 timeline（事件名 + 字段契约，必须含 `answered_by=auto` 之类机器可判的来源；现状 `answered_by` 是自由文本、`gate-answered` 的 detail 不含它）+ 在面板/`mw doctor` 可见（现状：…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-021: fields=complete` | 预设节点输出（L1） | 当写入自动决策时，账本每行含 decision_id/rule_id/evidence[]/switch/budget | 单次 PASS |
| `[VERIFY] VC-022: others_running=true auto_actions=0` | 预设节点输出（L1） | 当把 auto_gate_mode 置 off 时，autopilot 其余功能不受影响且无自动动作 | 单次 PASS |
| `[VERIFY] VC-023: revoked_only_one=true` | 预设节点输出（L1） | 当撤销一条自动决策时，消费集合 = answered − revoked 且门回到 pending | 单次 PASS |
| 路径分类 | 正常/异常 | — | — |

## AC-019: 给出无人值守默认动作的显式声明：每条 gate 必须有声明式的默认动作（自动过 / 停并报告 / 升级给人 / 拒绝），缺省不得是隐式永久滞留；并给出"声明缺失"时的机器判定与告警方式（P-014 家族：机器可判、逐字锚定）

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-024: alert=true` | 预设节点输出（L1） | 当某类门无声明式默认动作时，机器判定为告警而非隐式永久滞留 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-020: 自动决策的实现面与安全属性：明确它落在 conductor（Python）侧（`file:line`），并证明不放开 agent/worker 对 gate 目录的写权限（`xkey-gate-guard.ts` 的封堵保持有效，含验证方式）；给出"自动决策开关关闭后行为与今天一致"的判据（对齐 x…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-025: blocked=true trace=true` | 预设节点输出（L1） | 当尝试经 agent 工具通道写 gate 目录或 _autopilot/** 时，写入被拒并留痕 | 单次 PASS |
| `[VERIFY] VC-026: agent_write=denied` | 预设节点输出（L1） | 当自动决策关闭时，agent 对 gate 目录的写权限与今天一致（未放开） | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-021: 给出归属语义缺口的修法面与判据：(a) PM 手工行复用 `ap-` 前缀会同时（i）占用 conductor 的 key 层配额、（ii）让面板计数错位 ⇒ 给出机器可判的归属方案（writer 列 / 前缀命名空间隔离 / 行携带 origin）及两侧一致性；(b) 面板与 conductor …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-027: distinguishable=true` | 预设节点输出（L1） | 当读取行归属时，conductor 派发行与 PM 手工行可机器区分（origin 列） | 单次 PASS |
| `[VERIFY] VC-028: fallback=path` | 预设节点输出（L1） | 当历史行无 origin 时，按 path 兜底且不误判为 conductor 行 | 单次 PASS |
| 路径分类 | 正常/边界 | — | — |

## AC-022: 给出门消费守卫缺陷的判据与修法面（自动决策的硬前置）：D1 `_consumed_gate_ids` 的 `gate-\d{4}` 正则在 `gate-10000+` 静默失效（FM 已到 `gate-6687`，洪泛速率 585.8 门/h）；D2 `_apply_stalled_rejectio…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-029: gate-10000 matched=true` | 预设节点输出（L1） | 当 gate id 为 5 位时，已消费集合仍能命中（正则修复） | 单次 PASS |
| `[VERIFY] VC-030: rewrites=1` | 预设节点输出（L1） | 当已消费的 reject 门再次出现时，key-status 不被二次改写 | 单次 PASS |
| `[VERIFY] VC-031: reuse_safe=true` | 预设节点输出（L1） | 当同一门被两个消费者读取时，消费判定按 (id, created_at) 复合键，不串代 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-023: 给出自动化输入统计的口径与陷阱：任何"历史答案分布"必须按唯一 gate 文件/id 去重，并显式处理洪泛与重放（RQ-10 实测陷阱：FM 的 6694 条 `gate-answered` 事件只来自 10 个门——gate-0002 重放 5588 次 + gate-0003 1098 次，另有…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-032: dedup=file_id flood_handled=true` | 预设节点输出（L0） | 当统计历史答案分布时，按唯一门文件/id 去重且处理洪泛与重放（不产出幻觉比例） | 单次 PASS |
| 路径分类 | 边界 | — | — |

## AC-024: 给出影子模式的门类清单与判据（承接 AC-016 的 0 样本缺口）：`budget-exhausted` / `xkey-authorize` / `goal-halt` / `type-rejected` / `target-config-rejected` 生产样本为 0，reject 路径样…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-033: state_delta=0` | 预设节点输出（L1） | 当 shadow 模式运行时，账本新增影子行而 gate 文件与 key-status 零改动 | 单次 PASS |
| `[VERIFY] VC-034: gate_blocked=true` | 预设节点输出（L1） | 当影子样本不足门槛时，live 不可开启（≥5 夜 ∧ ≥20 条 ∧ 每规则 ≥1 反例） | 单次 PASS |
| 路径分类 | 正常/异常 | — | — |

## AC-025: 给出逐 gate 类型的处置模式三分判定（本 key 核心设计输入），并先解决"命题选层"：RQ-12 的三分是 可自举 = `budget-exhausted`（仅命题面，生产 0 样本）/ 部分可自举 = `stage-confirm` / `stage-close` / `stalled` /…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-035: tautology_rejected=true` | 预设节点输出（L0） | 当某门的新命题可被构造为真时，该门不得进入 case 1（恒真自检） | 单次 PASS |
| `[VERIFY] VC-036: falsifiable=6/6` | 预设节点输出（L0） | 当门进入 case 1 时，其事实面命题含"可以为假"的反例与 disk witness | 单次 PASS |
| 路径分类 | 正常/异常 | — | — |

## AC-026: 给出gate 审核材料的最小信息契约（供窗口渲染与人审）：RQ-14 已给出 14 项最小信息集（F1 身份与时效〔含同 scope 历史已答门〕/ F2 命题 / F3 选项后果与可逆性 / F4 目标一致性 / F5 触发原因类与计数 / F6 证据指针 / F7 证据存在性与新鲜度 / F8 …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-037: lines=1+13N` | 预设节点输出（L1） | 当渲染门卡片时，行数 == 1+13N 且每逻辑行 1 物理行 | 单次 PASS |
| `[VERIFY] VC-038: sentinel=true missing_scope=pending` | 预设节点输出（L1） | 当某字段缺失时，渲染唯一哨兵 `unknown (no field)` 且仅 pending 门报 missing | 单次 PASS |
| 路径分类 | 正常/边界 | — | — |

## AC-027: 给出非阻塞延后复核机制，并指明它按字面不可实现的部分：RQ-13 已证 `stalled` / `budget-exhausted` 让 key 保持非终态，而 `_stage_closure` 终态集只认 `("done","closed-legacy")`（`conductor.py:629-6…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-039: blocked=true` | 预设节点输出（L2） | 当待复核 key 存在时，stage-close 门不建、不自动收口 | 单次 PASS |
| `[VERIFY] VC-040: batched=true` | 预设节点输出（L1） | 当 stage 内其它 key 全终态时，同 tick 触发全部待复核 key 的批量复核 | 单次 PASS |
| `[VERIFY] VC-041: escalated=true state_unchanged=true` | 预设节点输出（L1） | 当待复核超过 48h 时，写 review-escalated 且状态不变 | 单次 PASS |
| 路径分类 | 正常/边界/异常 | — | — |

## AC-028: 给出消费记录持久化与 stage 状态单调性的修法面（硬前置，已有生产实例）：JC 在 2026-09-26T04:37 把 09-11 已答的 `gate-0001` 重放，stage 1 由 `closed` 退回 `running` 并生成新 stage-close 门；根因 = 消费记录由 …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-042: refused=1 dedup=true` | 预设节点输出（L1） | 当 stage 状态将被写回退时，写入被拒且写一条去重的 stage-reopen-refused | 单次 PASS |
| `[VERIFY] VC-043: stage=closed new_gates=0` | 预设节点输出（L1） | 当重放已答门（JC gate-0008 式 fixture）时，stage 保持 closed 且无新门 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-029: 给出取证源优先级与一致性对账（自举验证的硬前置）：`l3-verdict.txt` 与现行 resolver 复算有 6/22 个 key 不一致（FM `gui-shell-spike` 陈旧、FM `gui-contract-mock-tests` 机器假阴、E2 两个 key 被 correc…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-044: inconsistent=0` | 预设节点输出（L1） | 当 correction 声明 corrected_value=below 时，该 key 不得同时是 roadmap done 且 stage closed | 单次 PASS |
| `[VERIFY] VC-045: drift_detected=true` | 预设节点输出（L1） | 当证据在应答后被改写时，changed[] 非空且按快照 sha256 检出 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-030: 给出不可由被审方伪造的审计字段设计（护栏的地基）：实测 `answered_at` / `answered_by` 应答者可写（E2 `gate-0007` 早 4.1h、FM `gate-0002/0003` 晚 104s）；`reason` 文本随 conductor 版本有 3 种格式（JC …

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-046: derived=true` | 预设节点输出（L1） | 当审计自动决策时，权威字段全部由 conductor 派生（不读 answered_by/answered_at） | 单次 PASS |
| `[VERIFY] VC-047: forgery_blocked=true` | 预设节点输出（L1） | 当被审方改写 timeline/账本/开关文件时，经工具通道被拒并留拒绝记录 | 单次 PASS |
| 路径分类 | 异常 | — | — |

## AC-031: 给出门有效性审计（防止"门形同虚设"）：(a) 生产上唯一的跨 key 授权实际走散文 `cross-key-repair-request-*.md` + 手写 `decision:` 行，绕过了 `xkey-authorize` 门；(b) `roadmap.validate_roadmap` 未…

| 证据来源 | 证据类型 | 期望内容 | 充分性判定 |
|---------|---------|---------|----------|
| `[VERIFY] VC-048: unauthorized=true` | 预设节点输出（L1） | 当跨 key 授权经散文通道发生时，机器判定为未授权（导门即未授权） | 单次 PASS |
| `[VERIFY] VC-049: validated=true` | 预设节点输出（L1） | 当 roadmap 不合法时，校验被调用且问题可见（现状 validate_roadmap 未被调用） | 单次 PASS |
| 路径分类 | 异常 | — | — |

## 质检门禁使用说明

本文件由 `/quality-gate` 读取，对每个 AC/VC 逐条核查证据充分性：
- 每条 VC 必须在 verify 期有对应的真实执行输出（`[VERIFY]` 行），不得以"应当满足"替代。
- 每条 AC 的所有 VC 均需充分；任一条不充分即该 AC 未过。
- **反证要求**：凡声称"修复了某缺陷"的 VC，必须附"还原缺陷 ⇒ 该 VC 变红"的反证输出（P-016 家族）。
- **两侧镜像**：涉及跨语言的 VC（VC-011/VC-012/VC-037/VC-038 等）必须在 Python 与 TS 两侧都执行（P-021）。
- **口径纪律**：引用历史实测数字时必须回到原始 timeline/文件复算（P-022 家族）。

