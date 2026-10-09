# 分析层证据定位索引：mw-autopilot-slot-capacity（20260926-190335）

**性质**：本文件由 `.tmp/msc-qg-analysis-index.py` 机器生成，**只给证据位置**（候选源 + 首次提及行号 + 提及次数），
**不含** PASS/FAIL 判定 —— 充分性判定按 `evidence-requirement.md` 由 quality-gate worker 独立完成。

**为什么需要它**：本 key 有 31 个 AC / 49 个 VC，其中 **9 个 AC 与 9 个 VC 属于调研/分析层**
（例如「给出上限清单并做独立交叉核对」「不放开 per-key 并发」这类条目），它们的交付物是
`evidence/research/*.md` 调研笔记与 design 的决策记录，**不是**实现卡的 `[VERIFY]` 运行输出。
实现卡回执索引见同目录的 `verify-*-evidence-collection.md`。

## 无实现卡绑定的 AC

### AC-001（spec.md:105）

> | AC-001 | `evidence/research/spec-*.md` 至少一份笔记以 `file:line` 锚点给出「**key 层上限**」「**worker 层上限（单 key 内 / 全局）**」「**serve/launcher 层是否存在并发限制**」三者的完整清单（每项：变量名、默认值、生效位置 file:line、可配置性），且对"worker 层无显式上限"这一类否定结论必须附**反证式范围声明**（读过的代码范围 + 为什么该范围内没有）；另有一份笔记做**独立交叉核对**并报告差异 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-concurrency-anchors-20260926.md` | 8 | 4 |
| `evidence/research/spec-slot-framing-20260926.md` | 5 | 2 |
| `evidence/research/design-deferred-review-state-20260926.md` | 90 | 1 |
| `evidence/research/spec-crosscheck-slot-occupancy-20260926.md` | 5 | 1 |

相关 design 决策行:

- design.md:10 | ac_ids | AC-001 … AC-031（全列见 §8 映射表） |
- design.md:339 Layer: L0   Output: [VERIFY] VC-001: caps=3 annotated=3   Source: AC-001, AC-002
- design.md:444 | AC-001 | 上限清单（key/worker 层）带锚点 | VC-001 | 正常 |

### AC-002（spec.md:106）

> | AC-002 | 给出并行度上限的**现状成因判定**：对每个上限逐一标注"设计约束（附出处 file:line / 文档 / 提交）/ 历史默认 / 无依据"三态之一；不得出现"大概是"这类无出处结论 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-concurrency-anchors-20260926.md` | 16 | 2 |
| `evidence/research/spec-slot-change-space-20260926.md` | 5 | 2 |
| `evidence/research/spec-cap-breach-attribution-20260926.md` | 286 | 1 |

相关 design 决策行:

- design.md:339 Layer: L0   Output: [VERIFY] VC-001: caps=3 annotated=3   Source: AC-001, AC-002
- design.md:362 VC-013: 当阅读结论时，每条回应 (c1)(c2)(c3)(c3′)(d) 并由 AC-002..AC-010 支撑
- design.md:445 | AC-002 | 上限成因三态标注 | VC-001 | 正常 |

### AC-003（spec.md:107）

> | AC-003 | 给出**槽位利用率与排队实测**（≥2 个真实项目）：key 层打满率（达到上限的时间占比）+ **worker 层同时运行数分布**（平均/峰值）+ **并发 2 vs 1 的吞吐与失败率对比**（中位墙钟、失败率、失败类型分布）+ 样本量与时间窗；每个数字可由文件复算（给出复算命令/脚本片段） |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-slot-change-space-20260926.md` | 5 | 3 |
| `evidence/research/spec-slot-utilization-20260926.md` | 20 | 2 |
| `evidence/research/spec-concurrency-anchors-20260926.md` | 223 | 1 |
| `evidence/research/spec-gate-review-material-20260926.md` | 550 | 1 |
| `evidence/research/spec-panel-semantics-divergence-20260926.md` | 404 | 1 |
| `evidence/research/spec-unattended-stage-closure-20260926.md` | 164 | 1 |

相关 design 决策行:

- design.md:343 Layer: L0   Output: [VERIFY] VC-003: projects>=2   Source: AC-003
- design.md:446 | AC-003 | 利用率与排队实测 | VC-003 | 正常 |

### AC-004（spec.md:108）

> | AC-004 | 给出**占槽判定规则**的代码锚点（按行状态、与 key-status 无关）+ 三类状态（stalled / done / 在飞）的占槽表 + **频率实测**（stalled 占槽占比、孤儿行占槽占比）；若频率数据不足以实测，必须给出"无法实测"的诚实声明 + 可验证它的方法与所需数据 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-stalled-slot-release-20260926.md` | 255 | 3 |
| `evidence/research/spec-cap-breach-attribution-20260926.md` | 266 | 2 |
| `evidence/research/spec-slot-change-space-20260926.md` | 20 | 2 |
| `evidence/research/spec-unattended-stage-closure-20260926.md` | 362 | 2 |
| `evidence/research/spec-crosscheck-slot-occupancy-20260926.md` | 126 | 1 |
| `evidence/research/spec-gate-review-material-20260926.md` | 550 | 1 |
| `evidence/research/spec-panel-semantics-divergence-20260926.md` | 405 | 1 |

相关 design 决策行:

- design.md:341 Layer: L1   Output: [VERIFY] VC-002: rows_matched=true   Source: AC-004
- design.md:447 | AC-004 | 占槽判定规则 + 三类状态占槽表 | VC-002 | 边界 |

### AC-008（spec.md:112）

> | AC-008 | 给出 **(d) 的直接证据**：单 key 内 worker 派发的**串行化点清单**（每点：函数 `file:line` + 触发条件 + 硬顺序还是可并行）；并用同项目**两组真实运行**对比（autopilot/conductor 路径 vs PM 手工派发路径）的同时 worker 数，证明瓶颈位于哪一侧 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/design-watchdog-and-serial-20260926.md` | 5 | 6 |
| `evidence/research/spec-panel-semantics-divergence-20260926.md` | 32 | 5 |
| `evidence/research/spec-crosscheck-slot-occupancy-20260926.md` | 129 | 1 |
| `evidence/research/spec-unattended-stage-closure-20260926.md` | 375 | 1 |

相关 design 决策行:

- design.md:355 Layer: L1   Output: [VERIFY] VC-009: per_key_max=1   Source: AC-008
- design.md:451 | AC-008 | (d) 串行化点清单 | VC-009 | 正常 |

### AC-009（spec.md:113）

> | AC-009 | 给出 ≥3 个候选改动方案（覆盖 (c1)(c2)(c3)(c3′) 与 (d) 各路，且必须含"不改"一项），每项：改动位置（`file:line`/键名）、取值域与校验、**首个失败模式**（含判据 + 标注是已有史料还是 `[推断]`）、可逆性（如何退回、是否留残留）、GC-1/GC-3/GC-4 校验 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-capacity-constraints-20260926.md` | 128 | 1 |

相关 design 决策行:

- design.md:357 Layer: L0   Output: [VERIFY] VC-010: options>=3 includes_noop=true   Source: AC-009
- design.md:452 | AC-009 | ≥3 候选方案（含不改） | VC-010 | 正常 |

### AC-011（spec.md:115）

> | AC-011 | 最终结论必须由 AC-002..AC-010 的证据链支撑，并**逐条回应 (c1)(c2)(c3)(c3′)(d)**：说明如何改善夜跑吞吐与 worker 层利用率，或为何不该动；"不改"也必须给证据化理由 |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

相关 design 决策行:

- design.md:363 Layer: L0   Output: [VERIFY] VC-013: answered=5   Source: AC-011
- design.md:454 | AC-011 | 结论由证据链支撑 | VC-013 | 正常 |

### AC-014（spec.md:118）

> | AC-014 | 给出**并发安全前置清单**：若方案要放开 per-key 并发，必须列出前置项（写面声明→机器可读→重叠拒绝；行终态化时机；锁一致性）并给出每项**现状证据**与缺位时的**首个失败模式**。现状反证（RQ-5）：写面纪律只存在于 **11/248** 个任务书的散文里，`write_scope` / `写面` 在**生产代码零命中**，`read_scope`/`deny_globs` 只拦读，`implementation-gate` 对 worker 一律放行 ⇒ 机器判定**为零** |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/design-watchdog-and-serial-20260926.md` | 5 | 6 |
| `evidence/research/design-gate-schema-presentation-20260926.md` | 107 | 5 |
| `evidence/research/design-gate-propositions-20260926.md` | 372 | 4 |
| `evidence/research/spec-auto-gate-boundary-20260926.md` | 224 | 3 |
| `evidence/research/spec-gate-defer-safety-20260926.md` | 178 | 3 |
| `evidence/research/spec-gate-review-material-20260926.md` | 648 | 2 |
| `evidence/research/spec-cap-breach-attribution-20260926.md` | 277 | 1 |
| `evidence/research/spec-gate-selfverifiable-20260926.md` | 263 | 1 |

相关 design 决策行:

- design.md:369 Layer: L0   Output: [VERIFY] VC-016: machine_check=true   Source: AC-014
- design.md:457 | AC-014 | 并发安全前置清单 | VC-016 | 边界 |

### AC-015（spec.md:119）

> | AC-015 | 给出无人值守 gate 策略的**反作用清单**（若方案含自动 approve/reject/超时）：逐条给判据 —— (a) auto-approve × `_resume_credits` 无上界 ⇒ 夜间无限换 key / 烧 token；(b) `closed-legacy ∈ _DEP_SATISFIED` 会像 done 一样解锁依赖并放行 stage 收口；(c) 自动决策与 `advance_stall_ticks` 的 `stalled↔running` 振荡（FM 洪泛 6684 门 / 12h 已实证"看起来在跑、什么都没干"）；(d) 注意力掩盖（自动过后人看不见）。每条必须说明"如何检测它发生了" |

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-auto-gate-boundary-20260926.md` | 223 | 2 |
| `evidence/research/spec-auto-gate-guardrails-20260926.md` | 248 | 1 |

相关 design 决策行:

- design.md:371 Layer: L0   Output: [VERIFY] VC-017: effects<=>mitigations   Source: AC-015
- design.md:458 | AC-015 | 自动决策反作用清单 | VC-017 | 异常 |


## 无实现卡绑定的 VC

### VC-001（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-gate-review-material-20260926.md` | 409 | 1 |

### VC-002（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-gate-review-material-20260926.md` | 409 | 1 |

### VC-003（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

### VC-009（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-gate-review-material-20260926.md` | 192 | 2 |

### VC-010（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

### VC-013（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|
| `evidence/research/spec-gate-review-material-20260926.md` | 416 | 1 |

### VC-016（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

### VC-017（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

### VC-048（design.md:0）

> (未找到原文行)

| 候选证据源 | 首次提及行 | 提及次数 |
|---|---|---|

